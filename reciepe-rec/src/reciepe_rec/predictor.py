from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import median

from .data import BulkRecord, RecipeLine
from .text import normalize


DEFAULT_NEIGHBOR_COUNT = 25
DEFAULT_MAX_INGREDIENTS = 80
DEFAULT_DIVERSITY_NEIGHBORS = 5
DEFAULT_AGGREGATE_RANK_POWER = 1.2
DEFAULT_AGGREGATE_SEGMENT_WEIGHT = 240.0
DEFAULT_POOL_THRESHOLD = 0.70
POOL_LEVELS = (
    "full",
    "segment_plus",
    "segment",
    "subform",
    "midform",
    "form",
)


@dataclass(frozen=True)
class PredictedIngredient:
    ingredient_code: str
    ingredient_name: str
    score: float
    median_amount: float
    neighbor_count: int
    typical_phase: str


@dataclass(frozen=True)
class SimilarRecipe:
    rcp_id: str
    score: float


@dataclass(frozen=True)
class RecipePrediction:
    target_rcp_id: str | None
    predicted_count: int
    predicted_phase_count: int
    ingredients: tuple[PredictedIngredient, ...]
    similar_recipes: tuple[SimilarRecipe, ...]
    model_name: str = "statistical"
    candidate_score: float | None = None
    candidate_level: str | None = None

    @property
    def ingredient_codes(self) -> set[str]:
        return {item.ingredient_code for item in self.ingredients}


class RecipePredictor:
    model_name = "statistical"

    def __init__(
        self,
        bulk_records: list[BulkRecord],
        recipe_lines: list[RecipeLine],
        pool_threshold: float = DEFAULT_POOL_THRESHOLD,
        min_ingredient_frequency: int = 1,
    ):
        self.pool_threshold = pool_threshold
        self.min_ingredient_frequency = max(1, min_ingredient_frequency)
        self.records_by_id = {record.rcp_id: record for record in bulk_records}
        self.lines_by_id: dict[str, list[RecipeLine]] = defaultdict(list)
        self.amounts_by_id: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
        self.phases_by_code: dict[str, Counter[str]] = defaultdict(Counter)
        self.names_by_code: dict[str, Counter[str]] = defaultdict(Counter)
        for line in recipe_lines:
            if line.rcp_id not in self.records_by_id:
                continue
            self.lines_by_id[line.rcp_id].append(line)
            self.amounts_by_id[line.rcp_id][line.ingredient_code] += line.amount
            self.phases_by_code[line.ingredient_code][line.phase] += 1
            self.names_by_code[line.ingredient_code][line.ingredient_name] += 1
        self.recipe_ids = [
            record.rcp_id
            for record in bulk_records
            if record.rcp_id in self.lines_by_id
        ]
        self.segment_code_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        self.mid_form_code_counts: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
        self.segment_totals: Counter[tuple[str, str]] = Counter()
        self.mid_form_totals: Counter[tuple[str, str]] = Counter()
        self.global_code_counts: Counter[str] = Counter()
        for rcp_id in self.recipe_ids:
            record = self.records_by_id[rcp_id]
            segment = self._segment(record)
            mid_form = self._mid_form(record)
            self.segment_totals[segment] += 1
            self.mid_form_totals[mid_form] += 1
            for code in self.amounts_by_id[rcp_id]:
                self.segment_code_counts[segment][code] += 1
                self.mid_form_code_counts[mid_form][code] += 1
                self.global_code_counts[code] += 1
        self.recipe_code_sets_by_id = {
            rcp_id: frozenset(self.amounts_by_id[rcp_id])
            for rcp_id in self.recipe_ids
        }
        self.known_recipe_code_sets = set(self.recipe_code_sets_by_id.values())
        self.supported_ingredient_codes = {
            code
            for code, count in self.global_code_counts.items()
            if count >= self.min_ingredient_frequency
        }
        self.pool_indices: dict[str, dict[tuple[str, ...], list[str]]] = {
            level: defaultdict(list)
            for level in POOL_LEVELS
        }
        for rcp_id in self.recipe_ids:
            record = self.records_by_id[rcp_id]
            for level in POOL_LEVELS:
                self.pool_indices[level][self._pool_key(record, level)].append(rcp_id)

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
        neighbors = self._neighbors(request, excluded_rcp_id, neighbor_count)
        if max_ingredients is None:
            ranked_codes, scored = self._aggregate_prediction_codes(
                request,
                excluded_rcp_id,
                neighbors,
            )
            pool_ids = self._prediction_pool_ids(request, excluded_rcp_id)
            predicted_phase_count = self._pool_phase_count(pool_ids, neighbors)
        else:
            predicted_count = max(1, min(DEFAULT_MAX_INGREDIENTS, max_ingredients))
            scored = self._score_ingredients(request, neighbors, excluded_rcp_id)
            ranked_codes = sorted(scored, key=lambda code: (-scored[code], code))[:predicted_count]
            predicted_phase_count = self._phase_count_for_codes(ranked_codes)
        predicted_count = len(ranked_codes)
        ingredients = tuple(
            PredictedIngredient(
                ingredient_code=code,
                ingredient_name=self._ingredient_name(code),
                score=round(scored[code], 6),
                median_amount=round(self._neighbor_median_amount(code, neighbors), 6),
                neighbor_count=sum(1 for _score, rcp_id in neighbors if code in self.amounts_by_id[rcp_id]),
                typical_phase=self._typical_phase(code),
            )
            for code in ranked_codes
        )
        return RecipePrediction(
            target_rcp_id=excluded_rcp_id,
            predicted_count=predicted_count,
            predicted_phase_count=predicted_phase_count,
            ingredients=ingredients,
            similar_recipes=tuple(
                SimilarRecipe(
                    rcp_id=rcp_id,
                    score=round(score, 6),
                )
                for score, rcp_id in neighbors[:10]
            ),
        )

    def actual_codes(self, rcp_id: str) -> set[str]:
        return set(self.amounts_by_id[rcp_id])

    def actual_amounts(self, rcp_id: str) -> dict[str, float]:
        return dict(self.amounts_by_id[rcp_id])

    def _prototype_codes(self, neighbors: list[tuple[float, str]]) -> list[str]:
        if not neighbors:
            return []
        prototype_id = neighbors[0][1]
        lines = self.lines_by_id.get(prototype_id, ())
        seen: set[str] = set()
        codes: list[str] = []
        for line in sorted(lines, key=lambda item: (-item.amount, item.phase, item.ingredient_code)):
            if line.ingredient_code in seen:
                continue
            seen.add(line.ingredient_code)
            codes.append(line.ingredient_code)
        return codes

    def _prototype_prediction_codes(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
        neighbors: list[tuple[float, str]],
    ) -> tuple[list[str], dict[str, float]]:
        codes = self._prototype_codes(neighbors)
        scores = {
            code: float(len(codes) - rank)
            for rank, code in enumerate(codes)
        }
        used = set(codes)
        # Add evidence from nearby recipes so the output is not a verbatim recipe clone.
        candidates = self._diversity_candidates(
            request,
            excluded_rcp_id,
            neighbors,
            used,
        )
        for code, score in candidates:
            codes.append(code)
            used.add(code)
            scores[code] = score
            break
        for code, score in candidates:
            if not self._is_known_recipe_code_set(used, excluded_rcp_id):
                break
            codes.append(code)
            used.add(code)
            scores[code] = score
        self._avoid_known_recipe_clone(
            request,
            excluded_rcp_id,
            neighbors,
            codes,
            scores,
        )
        return codes, scores

    def _aggregate_prediction_codes(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
        neighbors: list[tuple[float, str]],
    ) -> tuple[list[str], dict[str, float]]:
        pool_ids = self._prediction_pool_ids(request, excluded_rcp_id)
        scores = self._supported_scores(self._weighted_presence_scores(pool_ids))
        ranked = sorted(scores, key=lambda code: (-scores[code], code))
        codes = [
            code
            for code in ranked
            if scores[code] > self.pool_threshold
        ]
        if not codes and ranked:
            codes = [ranked[0]]
        self._avoid_known_recipe_clone(
            request,
            excluded_rcp_id,
            neighbors,
            codes,
            scores,
        )
        return codes, scores

    def _prediction_pool_ids(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
    ) -> tuple[str, ...]:
        for level in POOL_LEVELS:
            candidates = tuple(
                rcp_id
                for rcp_id in self.pool_indices[level].get(self._pool_key(request, level), ())
                if rcp_id != excluded_rcp_id
            )
            if candidates:
                return candidates
        return tuple(rcp_id for rcp_id in self.recipe_ids if rcp_id != excluded_rcp_id)

    def _weighted_presence_scores(self, pool_ids: tuple[str, ...]) -> dict[str, float]:
        weights: dict[str, float] = defaultdict(float)
        denominator = 0.0
        for rcp_id in pool_ids:
            ingredient_count = len(self.amounts_by_id[rcp_id])
            if not ingredient_count:
                continue
            recipe_weight = 1.0 / ingredient_count
            denominator += recipe_weight
            for code in self.amounts_by_id[rcp_id]:
                weights[code] += recipe_weight
        if not denominator:
            return {}
        return {
            code: weight / denominator
            for code, weight in weights.items()
        }

    def _avoid_known_recipe_clone(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
        neighbors: list[tuple[float, str]],
        codes: list[str],
        scores: dict[str, float],
    ) -> list[str]:
        used = set(codes)
        if not self._is_known_recipe_code_set(used, excluded_rcp_id):
            return codes

        scored_candidates = (
            (code, scores[code])
            for code in sorted(scores, key=lambda item: (-scores[item], item))
            if code not in used
        )
        diversity_candidates = self._diversity_candidates(
            request,
            excluded_rcp_id,
            neighbors,
            used,
        )
        for code, score in (*scored_candidates, *diversity_candidates):
            if code in used:
                continue
            codes.append(code)
            used.add(code)
            scores[code] = score
            if not self._is_known_recipe_code_set(used, excluded_rcp_id):
                break
        return codes

    def _is_known_recipe_code_set(
        self,
        codes: set[str],
        excluded_rcp_id: str | None,
    ) -> bool:
        code_set = frozenset(codes)
        return any(
            rcp_id != excluded_rcp_id and known_set == code_set
            for rcp_id, known_set in self.recipe_code_sets_by_id.items()
        )

    def _diversity_candidates(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
        neighbors: list[tuple[float, str]],
        used: set[str],
    ):
        yielded = set(used)
        scores: dict[str, float] = defaultdict(float)
        for rank, (similarity, rcp_id) in enumerate(neighbors[:DEFAULT_DIVERSITY_NEIGHBORS]):
            weight = (1 / ((rank + 1) ** 0.8)) * max(similarity, 1.0) ** 1.25
            for code, amount in self.amounts_by_id[rcp_id].items():
                if code in yielded or not self._is_supported_code(code):
                    continue
                scores[code] += weight * (1.0 + min(amount, 30.0) / 30.0)
        for code, score in sorted(scores.items(), key=lambda item: (-item[1], item[0])):
            yielded.add(code)
            yield code, score

        segment = self._segment(request)
        segment_counts, segment_total = self._pool_code_counts(
            lambda record: self._segment(record) == segment,
            excluded_rcp_id,
        )
        if segment_total:
            for code, count in segment_counts.most_common():
                if code in yielded or not self._is_supported_code(code):
                    continue
                yielded.add(code)
                yield code, count / segment_total

        for code, count in self.global_code_counts.most_common():
            if code in yielded or not self._is_supported_code(code):
                continue
            yielded.add(code)
            yield code, count / max(len(self.recipe_ids), 1)

    def _prototype_phase_count(self, neighbors: list[tuple[float, str]]) -> int:
        if not neighbors:
            return 0
        prototype_id = neighbors[0][1]
        return len({line.phase for line in self.lines_by_id.get(prototype_id, ()) if line.phase})

    def _segment_ingredient_count(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
    ) -> int:
        counts = sorted(
            len(self.amounts_by_id[rcp_id])
            for rcp_id in self.recipe_ids
            if rcp_id != excluded_rcp_id
            and self._segment(self.records_by_id[rcp_id]) == self._segment(request)
        )
        if not counts:
            return 25
        index = max(0, int(len(counts) * 0.10) - 1)
        return max(1, counts[index])

    def _segment_phase_count(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
        neighbors: list[tuple[float, str]],
    ) -> int:
        counts = [
            len({line.phase for line in self.lines_by_id[rcp_id] if line.phase})
            for rcp_id in self.recipe_ids
            if rcp_id != excluded_rcp_id
            and self._segment(self.records_by_id[rcp_id]) == self._segment(request)
        ]
        if not counts:
            counts = [
                len({line.phase for line in self.lines_by_id[rcp_id] if line.phase})
                for _score, rcp_id in neighbors[:5]
            ]
        return int(round(median(counts))) if counts else 0

    def _pool_phase_count(
        self,
        pool_ids: tuple[str, ...],
        neighbors: list[tuple[float, str]],
    ) -> int:
        counts = [
            len({line.phase for line in self.lines_by_id[rcp_id] if line.phase})
            for rcp_id in pool_ids
        ]
        if not counts:
            counts = [
                len({line.phase for line in self.lines_by_id[rcp_id] if line.phase})
                for _score, rcp_id in neighbors[:5]
            ]
        return int(round(median(counts))) if counts else 0

    def _neighbors(
        self,
        request: BulkRecord,
        excluded_rcp_id: str | None,
        limit: int,
    ) -> list[tuple[float, str]]:
        scored = [
            (self._similarity(request, self.records_by_id[rcp_id]), rcp_id)
            for rcp_id in self.recipe_ids
            if rcp_id != excluded_rcp_id
        ]
        scored.sort(key=lambda item: (-item[0], item[1]))
        return scored[: max(limit, 1)]

    def _score_ingredients(
        self,
        request: BulkRecord,
        neighbors: list[tuple[float, str]],
        excluded_rcp_id: str | None,
    ) -> dict[str, float]:
        scores: dict[str, float] = defaultdict(float)
        for rank, (similarity, rcp_id) in enumerate(neighbors):
            weight = (1 / ((rank + 1) ** 0.35)) * max(similarity, 1.0) ** 1.25
            for code, amount in self.amounts_by_id[rcp_id].items():
                scores[code] += weight * (1.0 + min(amount, 30.0) / 30.0)

        segment = self._segment(request)
        segment_counts, segment_total = self._pool_code_counts(
            lambda record: self._segment(record) == segment,
            excluded_rcp_id,
        )
        if segment_total:
            for code, count in segment_counts.items():
                scores[code] += 120.0 * (count / segment_total)

        mid_form = self._mid_form(request)
        mid_form_counts, mid_form_total = self._pool_code_counts(
            lambda record: self._mid_form(record) == mid_form,
            excluded_rcp_id,
        )
        if mid_form_total:
            for code, count in mid_form_counts.items():
                scores[code] += 18.0 * (count / mid_form_total)
        return self._supported_scores(scores)

    def _pool_code_counts(self, predicate, excluded_rcp_id: str | None) -> tuple[Counter[str], int]:
        counts: Counter[str] = Counter()
        total = 0
        for rcp_id in self.recipe_ids:
            if rcp_id == excluded_rcp_id:
                continue
            if not predicate(self.records_by_id[rcp_id]):
                continue
            total += 1
            for code in self.amounts_by_id[rcp_id]:
                counts[code] += 1
        return counts, total

    def _supported_scores(self, scores: dict[str, float]) -> dict[str, float]:
        if self.min_ingredient_frequency <= 1:
            return scores
        return {
            code: score
            for code, score in scores.items()
            if code in self.supported_ingredient_codes
        }

    def _is_supported_code(self, code: str) -> bool:
        return (
            self.min_ingredient_frequency <= 1
            or code in self.supported_ingredient_codes
        )

    def _predicted_count(self, neighbors: list[tuple[float, str]]) -> int:
        counts = [
            len(self.amounts_by_id[rcp_id])
            for _score, rcp_id in neighbors[:15]
            if rcp_id in self.amounts_by_id
        ]
        if not counts:
            return 25
        return int(round(median(counts)))

    def _neighbor_median_amount(self, code: str, neighbors: list[tuple[float, str]]) -> float:
        values = [
            self.amounts_by_id[rcp_id][code]
            for _score, rcp_id in neighbors
            if code in self.amounts_by_id[rcp_id]
        ]
        return float(median(values)) if values else 0.0

    def _ingredient_name(self, code: str) -> str:
        counter = self.names_by_code.get(code)
        return counter.most_common(1)[0][0] if counter else code

    def _typical_phase(self, code: str) -> str:
        counter = self.phases_by_code.get(code)
        return counter.most_common(1)[0][0] if counter else ""

    def _phase_count_for_codes(self, codes: list[str]) -> int:
        return len({self._typical_phase(code) for code in codes if self._typical_phase(code)})

    def _similarity(self, left: BulkRecord, right: BulkRecord) -> float:
        score = 0.0
        if self._norm(left.product_subtype) and self._norm(left.product_subtype) == self._norm(right.product_subtype):
            score += 80.0
        if self._norm(left.form_type) and self._norm(left.form_type) == self._norm(right.form_type):
            score += 55.0
        if self._norm(left.product_midgroup) and self._norm(left.product_midgroup) == self._norm(right.product_midgroup):
            score += 28.0
        if self._norm(left.product_group) and self._norm(left.product_group) == self._norm(right.product_group):
            score += 8.0
        if self._norm(left.functional) and self._norm(left.functional) == self._norm(right.functional):
            score += 12.0
        if self._norm(left.bulk_type) and self._norm(left.bulk_type) == self._norm(right.bulk_type):
            score += 8.0
        if self._norm(left.functional_uv) and self._norm(left.functional_uv) == self._norm(right.functional_uv):
            score += 5.0
        if self._norm(left.ph) and self._norm(left.ph) == self._norm(right.ph):
            score += 2.0
        return score

    def _segment(self, record: BulkRecord) -> tuple[str, str]:
        return (self._norm(record.product_subtype), self._norm(record.form_type))

    def _mid_form(self, record: BulkRecord) -> tuple[str, str]:
        return (self._norm(record.product_midgroup), self._norm(record.form_type))

    def _pool_key(self, record: BulkRecord, level: str) -> tuple[str, ...]:
        if level == "full":
            return (
                self._norm(record.bulk_type),
                self._norm(record.functional),
                self._norm(record.functional_uv),
                self._norm(record.preservative),
                self._norm(record.product_midgroup),
                self._norm(record.product_subtype),
                self._norm(record.form_type),
                self._norm(record.viscosity),
                self._norm(record.spindle),
                self._norm(record.rpm),
                self._norm(record.cutting_hardness),
                self._norm(record.penetration_hardness),
                self._norm(record.melting_point),
                self._norm(record.ph),
                self._norm(record.leave_on),
                self._norm(record.rinse_off),
                self._norm(record.gas_filling),
            )
        if level == "segment_plus":
            return (
                self._norm(record.bulk_type),
                self._norm(record.functional),
                self._norm(record.functional_uv),
                self._norm(record.preservative),
                self._norm(record.product_midgroup),
                self._norm(record.product_subtype),
                self._norm(record.form_type),
                self._norm(record.ph),
            )
        if level == "segment":
            return (
                self._norm(record.product_midgroup),
                self._norm(record.product_subtype),
                self._norm(record.form_type),
            )
        if level == "subform":
            return (
                self._norm(record.product_subtype),
                self._norm(record.form_type),
            )
        if level == "midform":
            return (
                self._norm(record.product_midgroup),
                self._norm(record.form_type),
            )
        if level == "form":
            return (self._norm(record.form_type),)
        raise ValueError(f"unknown pool level: {level}")

    @staticmethod
    def _norm(value: str | None) -> str:
        return normalize(value)
