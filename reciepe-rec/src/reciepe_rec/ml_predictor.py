from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, fields
import threading
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import KFold

from .data import BulkRecord, RecipeLine
from .predictor import (
    DEFAULT_NEIGHBOR_COUNT,
    POOL_LEVELS,
    PredictedIngredient,
    RecipePrediction,
    RecipePredictor,
    SimilarRecipe,
)
from .text import normalize


MODEL_NAME = "catboost-candidate-selector-v1"
SEED = 20260724
EVALUATION_MIN_SUPPORT = 21
PASS_THRESHOLD = 0.10
RAW_FIELDS = tuple(
    field.name for field in fields(BulkRecord) if field.name != "rcp_id"
)
CAT_COLUMNS = (*RAW_FIELDS, "chosen_level", "set_signature")
MODEL_CONFIGURATION = {
    "depth": 8,
    "iterations": 400,
    "learning_rate": 0.03,
    "l2_leaf_reg": 10,
}


def _catboost_classifier():
    try:
        from catboost import CatBoostClassifier
    except ImportError as exc:  # pragma: no cover - depends on runtime packaging
        raise RuntimeError(
            "The CatBoost model requires the 'catboost' package. "
            "Install the project dependencies or run with --model statistical."
        ) from exc
    return CatBoostClassifier


def categorical(value: object | None) -> str:
    text = normalize(value)
    return text if text else "__missing__"


def passes(predicted: set[str], actual: set[str]) -> bool:
    red = actual - predicted
    yellow = predicted - actual
    red_rate = len(red) / len(actual) if actual else 0.0
    yellow_rate = len(yellow) / len(predicted) if predicted else 0.0
    return red_rate < PASS_THRESHOLD and yellow_rate < PASS_THRESHOLD


def _similarity(left: BulkRecord, right: BulkRecord) -> float:
    score = 0.0
    for name, weight in (
        ("product_subtype", 80.0),
        ("form_type", 55.0),
        ("product_midgroup", 28.0),
        ("product_group", 8.0),
        ("functional", 12.0),
        ("bulk_type", 8.0),
        ("functional_uv", 5.0),
        ("ph", 2.0),
    ):
        left_value = normalize(getattr(left, name))
        if left_value and left_value == normalize(getattr(right, name)):
            score += weight
    return score


def _candidate_sets(
    pool_ids: list[str],
    actual_by_id: dict[str, set[str]],
    eligible: set[str],
) -> list[set[str]]:
    actual_sets = [actual_by_id[recipe_id] & eligible for recipe_id in pool_ids]
    candidates = {frozenset(codes) for codes in actual_sets if codes}
    if not actual_sets:
        return []

    counts = Counter(code for codes in actual_sets for code in codes)
    weighted: dict[str, float] = defaultdict(float)
    denominator = 0.0
    for codes in actual_sets:
        if not codes:
            continue
        weight = 1.0 / len(codes)
        denominator += weight
        for code in codes:
            weighted[code] += weight

    for threshold in np.arange(0.10, 0.951, 0.025):
        candidates.add(
            frozenset(
                code
                for code, count in counts.items()
                if count / len(actual_sets) >= threshold
            )
        )
        candidates.add(
            frozenset(
                code
                for code, weight in weighted.items()
                if denominator and weight / denominator >= threshold
            )
        )
    return [
        set(codes)
        for codes in sorted(
            (codes for codes in candidates if codes),
            key=lambda codes: (len(codes), tuple(sorted(codes))),
        )
    ]


@dataclass(frozen=True)
class CandidateBundle:
    frame: pd.DataFrame
    candidates: tuple[set[str], ...]
    chosen_level: str
    pool_ids: tuple[str, ...]
    code_support: dict[str, float]


class CandidateContext:
    def __init__(
        self,
        context_ids: list[str],
        records_by_id: dict[str, BulkRecord],
        actual_by_id: dict[str, set[str]],
        eligible: set[str],
    ) -> None:
        self.context_ids = tuple(context_ids)
        self.records_by_id = records_by_id
        self.actual_by_id = actual_by_id
        self.eligible = eligible
        helper = RecipePredictor(
            [records_by_id[recipe_id] for recipe_id in context_ids],
            [],
        )
        self._pool_key = helper._pool_key
        self._indices: dict[str, dict[tuple[str, ...], list[str]]] = {
            level: defaultdict(list) for level in POOL_LEVELS
        }
        for recipe_id in context_ids:
            record = records_by_id[recipe_id]
            for level in POOL_LEVELS:
                self._indices[level][
                    self._pool_key(record, level)
                ].append(recipe_id)

    def build(
        self,
        record: BulkRecord,
        excluded_rcp_id: str | None,
    ) -> CandidateBundle:
        level_ids = {
            level: tuple(
                recipe_id
                for recipe_id in self._indices[level].get(
                    self._pool_key(record, level),
                    (),
                )
                if recipe_id != excluded_rcp_id
            )
            for level in POOL_LEVELS
        }
        chosen_level = next(
            (level for level in POOL_LEVELS if level_ids[level]),
            "global",
        )
        pool_ids = (
            level_ids[chosen_level]
            if chosen_level != "global"
            else tuple(
                recipe_id
                for recipe_id in self.context_ids
                if recipe_id != excluded_rcp_id
            )
        )
        pool_sets = [
            self.actual_by_id[recipe_id] & self.eligible
            for recipe_id in pool_ids
        ]
        code_counts = Counter(code for codes in pool_sets for code in codes)
        candidates = _candidate_sets(
            list(pool_ids),
            self.actual_by_id,
            self.eligible,
        )
        if not candidates:
            raise RuntimeError("candidate generation produced no ingredient sets")

        raw_record = {
            name: categorical(getattr(record, name))
            for name in RAW_FIELDS
        }
        source_by_set: dict[frozenset[str], list[str]] = defaultdict(list)
        for source_id in pool_ids:
            source_by_set[
                frozenset(self.actual_by_id[source_id] & self.eligible)
            ].append(source_id)

        rows: list[dict[str, object]] = []
        for candidate in candidates:
            green_counts = [len(candidate & codes) for codes in pool_sets]
            red_counts = [len(codes - candidate) for codes in pool_sets]
            yellow_counts = [len(candidate - codes) for codes in pool_sets]
            red_rates = [
                red / len(codes) if codes else 0.0
                for red, codes in zip(red_counts, pool_sets)
            ]
            yellow_rates = [
                yellow / len(candidate) if candidate else 0.0
                for yellow in yellow_counts
            ]
            supports = [
                code_counts[code] / max(len(pool_sets), 1)
                for code in candidate
            ]
            sources = source_by_set.get(frozenset(candidate), [])
            rows.append(
                {
                    **raw_record,
                    "chosen_level": chosen_level,
                    "set_signature": "|".join(sorted(candidate)),
                    "pool_size": float(len(pool_ids)),
                    "candidate_options": float(len(candidates)),
                    "set_size": float(len(candidate)),
                    "exact_set_support": float(len(sources)),
                    "exact_set_ratio": len(sources) / max(len(pool_ids), 1),
                    "pool_pass_rate": (
                        sum(passes(candidate, codes) for codes in pool_sets)
                        / max(len(pool_sets), 1)
                    ),
                    "green_mean": (
                        float(np.mean(green_counts)) if green_counts else 0.0
                    ),
                    "red_mean": (
                        float(np.mean(red_counts)) if red_counts else 0.0
                    ),
                    "yellow_mean": (
                        float(np.mean(yellow_counts)) if yellow_counts else 0.0
                    ),
                    "red_rate_mean": (
                        float(np.mean(red_rates)) if red_rates else 0.0
                    ),
                    "yellow_rate_mean": (
                        float(np.mean(yellow_rates)) if yellow_rates else 0.0
                    ),
                    "red_rate_max": (
                        float(np.max(red_rates)) if red_rates else 0.0
                    ),
                    "yellow_rate_max": (
                        float(np.max(yellow_rates)) if yellow_rates else 0.0
                    ),
                    "code_support_mean": (
                        float(np.mean(supports)) if supports else 0.0
                    ),
                    "code_support_min": (
                        float(np.min(supports)) if supports else 0.0
                    ),
                    "code_support_max": (
                        float(np.max(supports)) if supports else 0.0
                    ),
                    "source_similarity_max": max(
                        (
                            _similarity(record, self.records_by_id[source_id])
                            for source_id in sources
                        ),
                        default=0.0,
                    ),
                }
            )
        return CandidateBundle(
            frame=pd.DataFrame(rows),
            candidates=tuple(candidates),
            chosen_level=chosen_level,
            pool_ids=pool_ids,
            code_support={
                code: count / max(len(pool_sets), 1)
                for code, count in code_counts.items()
            },
        )

    def training_frame(
        self,
        target_ids: list[str],
    ) -> tuple[pd.DataFrame, np.ndarray]:
        frames: list[pd.DataFrame] = []
        labels: list[int] = []
        for target_id in target_ids:
            bundle = self.build(
                self.records_by_id[target_id],
                excluded_rcp_id=target_id,
            )
            target_actual = self.actual_by_id[target_id] & self.eligible
            frames.append(bundle.frame)
            labels.extend(
                int(passes(candidate, target_actual))
                for candidate in bundle.candidates
            )
        return (
            pd.concat(frames, ignore_index=True),
            np.asarray(labels, dtype=np.int8),
        )


class CatBoostRecipePredictor(RecipePredictor):
    """Leakage-controlled CatBoost candidate selector used by CLI and Web.

    Known recipes are predicted with the model of the fold in which the
    recipe was held out. New custom inputs use a scorer fitted on all known
    recipes. Both paths generate candidate sets from the current data in
    memory, and always exclude the requested known recipe from its pool.
    """

    model_name = MODEL_NAME

    def __init__(
        self,
        bulk_records: list[BulkRecord],
        recipe_lines: list[RecipeLine],
        *,
        thread_count: int = 20,
    ) -> None:
        _catboost_classifier()
        super().__init__(
            bulk_records,
            recipe_lines,
            min_ingredient_frequency=EVALUATION_MIN_SUPPORT,
        )
        self.thread_count = max(1, thread_count)
        self.actual_by_id = {
            recipe_id: set(self.amounts_by_id[recipe_id])
            for recipe_id in self.recipe_ids
        }
        self.eligible = set(self.supported_ingredient_codes)
        self.recipe_ids = sorted(self.actual_by_id)
        self._full_context = CandidateContext(
            self.recipe_ids,
            self.records_by_id,
            self.actual_by_id,
            self.eligible,
        )
        self._models: dict[int | str, Any] = {}
        self._model_lock = threading.RLock()
        self._train_ids_by_fold: dict[int, list[str]] = {}
        self._fold_by_id: dict[str, int] = {}
        for fold, (train_index, validation_index) in enumerate(
            KFold(5, shuffle=True, random_state=SEED).split(self.recipe_ids),
            start=1,
        ):
            self._train_ids_by_fold[fold] = [
                self.recipe_ids[index] for index in train_index
            ]
            for index in validation_index:
                self._fold_by_id[self.recipe_ids[index]] = fold

    @property
    def model_status(self) -> dict[str, object]:
        return {
            "name": self.model_name,
            "evaluation_min_support": EVALUATION_MIN_SUPPORT,
            "eligible_ingredient_count": len(self.eligible),
            "trained_folds": sorted(
                key for key in self._models if isinstance(key, int)
            ),
            "full_model_trained": "full" in self._models,
        }

    def _fit(self, key: int | str):
        with self._model_lock:
            cached = self._models.get(key)
            if cached is not None:
                return cached

            if key == "full":
                train_ids = self.recipe_ids
                seed = SEED + 10_000
            else:
                fold = int(key)
                train_ids = self._train_ids_by_fold[fold]
                seed = SEED + fold + 300
            context = CandidateContext(
                train_ids,
                self.records_by_id,
                self.actual_by_id,
                self.eligible,
            )
            frame, labels = context.training_frame(train_ids)
            classifier = _catboost_classifier()
            model = classifier(
                loss_function="Logloss",
                random_seed=seed,
                thread_count=self.thread_count,
                allow_writing_files=False,
                verbose=False,
                **MODEL_CONFIGURATION,
            )
            model.fit(
                frame,
                labels,
                cat_features=list(CAT_COLUMNS),
            )
            self._models[key] = model
            return model

    def predict_existing_holdout(
        self,
        target_rcp_id: str,
        max_ingredients: int | None = None,
        neighbor_count: int = DEFAULT_NEIGHBOR_COUNT,
    ) -> RecipePrediction:
        if target_rcp_id not in self.records_by_id:
            raise ValueError(f"unknown RCP_ID: {target_rcp_id}")
        return self.predict(
            self.records_by_id[target_rcp_id],
            excluded_rcp_id=target_rcp_id,
            max_ingredients=max_ingredients,
            neighbor_count=neighbor_count,
        )

    def predict(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None = None,
        max_ingredients: int | None = None,
        neighbor_count: int = DEFAULT_NEIGHBOR_COUNT,
    ) -> RecipePrediction:
        if (
            excluded_rcp_id is not None
            and excluded_rcp_id not in self._fold_by_id
        ):
            raise ValueError(f"unknown RCP_ID: {excluded_rcp_id}")
        model_key: int | str = (
            self._fold_by_id[excluded_rcp_id]
            if excluded_rcp_id is not None
            else "full"
        )
        model = self._fit(model_key)
        bundle = self._full_context.build(request, excluded_rcp_id)
        scores = model.predict_proba(bundle.frame)[:, 1]
        selected_position = max(
            range(len(bundle.candidates)),
            key=lambda position: (
                float(scores[position]),
                -len(bundle.candidates[position]),
                "|".join(sorted(bundle.candidates[position])),
            ),
        )
        selected = set(bundle.candidates[selected_position])
        if max_ingredients is not None:
            selected = set(
                sorted(
                    selected,
                    key=lambda code: (
                        -bundle.code_support.get(code, 0.0),
                        code,
                    ),
                )[: max(1, max_ingredients)]
            )

        neighbors = self._neighbors(
            request,
            excluded_rcp_id,
            neighbor_count,
        )
        ranked_codes = sorted(
            selected,
            key=lambda code: (-bundle.code_support.get(code, 0.0), code),
        )
        ingredients = tuple(
            PredictedIngredient(
                ingredient_code=code,
                ingredient_name=self._ingredient_name(code),
                score=round(bundle.code_support.get(code, 0.0), 6),
                median_amount=round(
                    self._neighbor_median_amount(code, neighbors),
                    6,
                ),
                neighbor_count=sum(
                    1
                    for _score, recipe_id in neighbors
                    if code in self.amounts_by_id[recipe_id]
                ),
                typical_phase=self._typical_phase(code),
            )
            for code in ranked_codes
        )
        return RecipePrediction(
            target_rcp_id=excluded_rcp_id,
            predicted_count=len(ingredients),
            predicted_phase_count=self._pool_phase_count(
                bundle.pool_ids,
                neighbors,
            ),
            ingredients=ingredients,
            similar_recipes=tuple(
                SimilarRecipe(
                    rcp_id=recipe_id,
                    score=round(score, 6),
                )
                for score, recipe_id in neighbors[:10]
            ),
            model_name=self.model_name,
            candidate_score=round(float(scores[selected_position]), 6),
            candidate_level=bundle.chosen_level,
        )

    def evaluate_crossfit(self) -> dict[str, object]:
        passed = 0
        red_total = 0
        yellow_total = 0
        for recipe_id in self.recipe_ids:
            prediction = self.predict_existing_holdout(recipe_id)
            actual = self.actual_by_id[recipe_id] & self.eligible
            predicted = prediction.ingredient_codes
            red_total += len(actual - predicted)
            yellow_total += len(predicted - actual)
            passed += int(passes(predicted, actual))
        return {
            "model": self.model_name,
            "protocol": "5-fold target crossfit with leave-one-target-out candidates",
            "sample_size": len(self.recipe_ids),
            "eligible_ingredient_count": len(self.eligible),
            "passed": passed,
            "pass_rate": passed / max(len(self.recipe_ids), 1),
            "red_count": red_total,
            "yellow_count": yellow_total,
        }
