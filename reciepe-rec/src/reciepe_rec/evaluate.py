from __future__ import annotations

from dataclasses import dataclass
import random
from statistics import mean, median

from .predictor import RecipePredictor


@dataclass(frozen=True)
class IngredientMetrics:
    predicted_count: int
    actual_count: int
    hit_count: int
    precision: float
    recall: float
    f1: float
    amount_recall: float


@dataclass(frozen=True)
class StrictDeviationMetrics:
    predicted_count: int
    actual_count: int
    hit_count: int
    missing_count: int
    extra_count: int
    count_error_ratio: float
    type_error_ratio: float
    count_within_tolerance: bool
    type_within_tolerance: bool
    within_tolerance: bool


@dataclass(frozen=True)
class UserDefinedMetrics:
    actual_phase_count: int
    predicted_phase_count: int
    phase_count_difference: int
    phase_error_ratio: float
    raw_actual_ingredient_count: int
    actual_ingredient_count: int
    predicted_ingredient_count: int
    ingredient_type_difference: int
    ingredient_type_error_ratio: float
    ignored_actual_ingredient_count: int


@dataclass(frozen=True)
class HoldoutResult:
    rcp_id: str
    product_subtype: str | None
    form_type: str | None
    metrics: IngredientMetrics


@dataclass(frozen=True)
class StrictHoldoutResult:
    rcp_id: str
    product_subtype: str | None
    form_type: str | None
    metrics: StrictDeviationMetrics


@dataclass(frozen=True)
class UserDefinedHoldoutResult:
    rcp_id: str
    product_subtype: str | None
    form_type: str | None
    metrics: UserDefinedMetrics


@dataclass(frozen=True)
class EvaluationSummary:
    sample_size: int
    precision_avg: float
    precision_median: float
    recall_avg: float
    recall_median: float
    f1_avg: float
    f1_median: float
    amount_recall_avg: float
    amount_recall_median: float
    target_passed: bool
    worst_results: tuple[HoldoutResult, ...]


@dataclass(frozen=True)
class StrictEvaluationSummary:
    sample_size: int
    tolerance: float
    both_pass_count: int
    count_pass_count: int
    type_pass_count: int
    both_pass_rate: float
    count_pass_rate: float
    type_pass_rate: float
    count_error_avg: float
    count_error_median: float
    type_error_avg: float
    type_error_median: float
    target_passed: bool
    worst_results: tuple[StrictHoldoutResult, ...]


@dataclass(frozen=True)
class UserDefinedEvaluationSummary:
    sample_size: int
    phase_error_target: float
    ingredient_type_error_target: float
    target_passed: bool
    total_phase_count_difference: int
    total_ingredient_type_difference: int
    total_raw_actual_ingredient_count: int
    total_ignored_actual_ingredient_count: int
    ingredient_support_coverage_rate: float
    phase_score: float
    ingredient_type_score: float
    phase_difference_avg: float
    phase_difference_median: float
    phase_error_rate_avg: float
    phase_error_rate_median: float
    ingredient_type_difference_avg: float
    ingredient_type_difference_median: float
    ingredient_type_error_rate_avg: float
    ingredient_type_error_rate_median: float
    worst_phase_results: tuple[UserDefinedHoldoutResult, ...]
    worst_ingredient_results: tuple[UserDefinedHoldoutResult, ...]


@dataclass(frozen=True)
class EvaluationTargets:
    min_f1_avg: float = 0.65
    min_recall_avg: float = 0.65
    min_amount_recall_avg: float = 0.80


def ingredient_metrics(
    predicted: set[str],
    actual: set[str],
    actual_amounts: dict[str, float],
) -> IngredientMetrics:
    hits = predicted & actual
    precision = len(hits) / len(predicted) if predicted else 0.0
    recall = len(hits) / len(actual) if actual else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    total_amount = sum(actual_amounts.values())
    hit_amount = sum(actual_amounts[code] for code in hits)
    amount_recall = hit_amount / total_amount if total_amount else 0.0
    return IngredientMetrics(
        predicted_count=len(predicted),
        actual_count=len(actual),
        hit_count=len(hits),
        precision=precision,
        recall=recall,
        f1=f1,
        amount_recall=amount_recall,
    )


def strict_deviation_metrics(
    predicted: set[str],
    actual: set[str],
    tolerance: float = 0.10,
) -> StrictDeviationMetrics:
    hits = predicted & actual
    missing = actual - predicted
    extra = predicted - actual
    actual_count = len(actual)
    predicted_count = len(predicted)
    count_error_ratio = (
        abs(predicted_count - actual_count) / actual_count if actual_count else 0.0
    )
    type_error_ratio = (
        (len(missing) + len(extra)) / actual_count if actual_count else 0.0
    )
    count_within = count_error_ratio <= tolerance
    type_within = type_error_ratio <= tolerance
    return StrictDeviationMetrics(
        predicted_count=predicted_count,
        actual_count=actual_count,
        hit_count=len(hits),
        missing_count=len(missing),
        extra_count=len(extra),
        count_error_ratio=count_error_ratio,
        type_error_ratio=type_error_ratio,
        count_within_tolerance=count_within,
        type_within_tolerance=type_within,
        within_tolerance=count_within and type_within,
    )


def user_defined_metrics(
    actual_phase_count: int,
    predicted_phase_count: int,
    actual_ingredients: set[str],
    predicted_ingredients: set[str],
    supported_ingredient_codes: set[str] | None = None,
) -> UserDefinedMetrics:
    raw_actual_ingredient_count = len(actual_ingredients)
    if supported_ingredient_codes is not None:
        actual_ingredients = actual_ingredients & supported_ingredient_codes
        predicted_ingredients = predicted_ingredients & supported_ingredient_codes
    phase_diff = abs(actual_phase_count - predicted_phase_count)
    ingredient_diff = len(actual_ingredients ^ predicted_ingredients)
    return UserDefinedMetrics(
        actual_phase_count=actual_phase_count,
        predicted_phase_count=predicted_phase_count,
        phase_count_difference=phase_diff,
        phase_error_ratio=(
            phase_diff / actual_phase_count if actual_phase_count else 0.0
        ),
        raw_actual_ingredient_count=raw_actual_ingredient_count,
        actual_ingredient_count=len(actual_ingredients),
        predicted_ingredient_count=len(predicted_ingredients),
        ingredient_type_difference=ingredient_diff,
        ingredient_type_error_ratio=(
            ingredient_diff / len(actual_ingredients) if actual_ingredients else 0.0
        ),
        ignored_actual_ingredient_count=(
            raw_actual_ingredient_count - len(actual_ingredients)
        ),
    )


def evaluate_holdouts(
    predictor: RecipePredictor,
    rcp_ids: list[str],
    targets: EvaluationTargets = EvaluationTargets(),
    max_ingredients: int | None = None,
) -> EvaluationSummary:
    results = [_evaluate_one(predictor, rcp_id, max_ingredients=max_ingredients) for rcp_id in rcp_ids]
    return summarize_results(results, targets)


def evaluate_strict_holdouts(
    predictor: RecipePredictor,
    rcp_ids: list[str],
    tolerance: float = 0.10,
    max_ingredients: int | None = None,
) -> StrictEvaluationSummary:
    results = [
        _evaluate_strict_one(
            predictor,
            rcp_id,
            tolerance=tolerance,
            max_ingredients=max_ingredients,
        )
        for rcp_id in rcp_ids
    ]
    return summarize_strict_results(results, tolerance)


def evaluate_strict_all(
    predictor: RecipePredictor,
    tolerance: float = 0.10,
    max_ingredients: int | None = None,
) -> StrictEvaluationSummary:
    return evaluate_strict_holdouts(
        predictor,
        list(predictor.recipe_ids),
        tolerance=tolerance,
        max_ingredients=max_ingredients,
    )


def evaluate_user_defined_all(
    predictor: RecipePredictor,
    max_ingredients: int | None = None,
    phase_error_target: float = 0.10,
    ingredient_type_error_target: float = 0.30,
    supported_ingredient_codes: set[str] | None = None,
) -> UserDefinedEvaluationSummary:
    results = [
        _evaluate_user_defined_one(
            predictor,
            rcp_id,
            max_ingredients=max_ingredients,
            supported_ingredient_codes=supported_ingredient_codes,
        )
        for rcp_id in predictor.recipe_ids
    ]
    return summarize_user_defined_results(
        results,
        phase_error_target=phase_error_target,
        ingredient_type_error_target=ingredient_type_error_target,
    )


def evaluate_random_holdouts(
    predictor: RecipePredictor,
    sample_size: int,
    seed: int,
    targets: EvaluationTargets = EvaluationTargets(),
    max_ingredients: int | None = None,
) -> EvaluationSummary:
    rng = random.Random(seed)
    rcp_ids = list(predictor.recipe_ids)
    if sample_size < len(rcp_ids):
        rcp_ids = rng.sample(rcp_ids, sample_size)
    return evaluate_holdouts(predictor, rcp_ids, targets, max_ingredients=max_ingredients)


def summarize_strict_results(
    results: list[StrictHoldoutResult],
    tolerance: float,
) -> StrictEvaluationSummary:
    count_errors = [result.metrics.count_error_ratio for result in results]
    type_errors = [result.metrics.type_error_ratio for result in results]
    both_pass_count = sum(1 for result in results if result.metrics.within_tolerance)
    count_pass_count = sum(1 for result in results if result.metrics.count_within_tolerance)
    type_pass_count = sum(1 for result in results if result.metrics.type_within_tolerance)
    sample_size = len(results)
    return StrictEvaluationSummary(
        sample_size=sample_size,
        tolerance=tolerance,
        both_pass_count=both_pass_count,
        count_pass_count=count_pass_count,
        type_pass_count=type_pass_count,
        both_pass_rate=both_pass_count / sample_size if sample_size else 0.0,
        count_pass_rate=count_pass_count / sample_size if sample_size else 0.0,
        type_pass_rate=type_pass_count / sample_size if sample_size else 0.0,
        count_error_avg=mean(count_errors) if count_errors else 0.0,
        count_error_median=median(count_errors) if count_errors else 0.0,
        type_error_avg=mean(type_errors) if type_errors else 0.0,
        type_error_median=median(type_errors) if type_errors else 0.0,
        target_passed=both_pass_count == sample_size,
        worst_results=tuple(
            sorted(
                results,
                key=lambda result: (
                    not result.metrics.within_tolerance,
                    result.metrics.type_error_ratio,
                    result.metrics.count_error_ratio,
                ),
                reverse=True,
            )[:10]
        ),
    )


def summarize_user_defined_results(
    results: list[UserDefinedHoldoutResult],
    phase_error_target: float = 0.10,
    ingredient_type_error_target: float = 0.30,
) -> UserDefinedEvaluationSummary:
    sample_size = len(results)
    phase_diffs = [result.metrics.phase_count_difference for result in results]
    ingredient_diffs = [result.metrics.ingredient_type_difference for result in results]
    phase_error_rates = [result.metrics.phase_error_ratio for result in results]
    ingredient_error_rates = [
        result.metrics.ingredient_type_error_ratio for result in results
    ]
    total_phase_diff = sum(phase_diffs)
    total_ingredient_diff = sum(ingredient_diffs)
    total_raw_actual_ingredient_count = sum(
        result.metrics.raw_actual_ingredient_count
        for result in results
    )
    total_ignored_actual_ingredient_count = sum(
        result.metrics.ignored_actual_ingredient_count
        for result in results
    )
    phase_error_rate_avg = mean(phase_error_rates) if phase_error_rates else 0.0
    ingredient_error_rate_avg = mean(ingredient_error_rates) if ingredient_error_rates else 0.0
    return UserDefinedEvaluationSummary(
        sample_size=sample_size,
        phase_error_target=phase_error_target,
        ingredient_type_error_target=ingredient_type_error_target,
        target_passed=(
            phase_error_rate_avg <= phase_error_target
            and ingredient_error_rate_avg <= ingredient_type_error_target
        ),
        total_phase_count_difference=total_phase_diff,
        total_ingredient_type_difference=total_ingredient_diff,
        total_raw_actual_ingredient_count=total_raw_actual_ingredient_count,
        total_ignored_actual_ingredient_count=total_ignored_actual_ingredient_count,
        ingredient_support_coverage_rate=(
            (
                total_raw_actual_ingredient_count
                - total_ignored_actual_ingredient_count
            )
            / total_raw_actual_ingredient_count
            if total_raw_actual_ingredient_count
            else 0.0
        ),
        phase_score=(total_phase_diff / sample_size * 100.0) if sample_size else 0.0,
        ingredient_type_score=(total_ingredient_diff / sample_size * 100.0) if sample_size else 0.0,
        phase_difference_avg=mean(phase_diffs) if phase_diffs else 0.0,
        phase_difference_median=median(phase_diffs) if phase_diffs else 0.0,
        phase_error_rate_avg=phase_error_rate_avg,
        phase_error_rate_median=median(phase_error_rates) if phase_error_rates else 0.0,
        ingredient_type_difference_avg=mean(ingredient_diffs) if ingredient_diffs else 0.0,
        ingredient_type_difference_median=median(ingredient_diffs) if ingredient_diffs else 0.0,
        ingredient_type_error_rate_avg=ingredient_error_rate_avg,
        ingredient_type_error_rate_median=median(ingredient_error_rates) if ingredient_error_rates else 0.0,
        worst_phase_results=tuple(
            sorted(
                results,
                key=lambda result: result.metrics.phase_error_ratio,
                reverse=True,
            )[:10]
        ),
        worst_ingredient_results=tuple(
            sorted(
                results,
                key=lambda result: result.metrics.ingredient_type_error_ratio,
                reverse=True,
            )[:10]
        ),
    )


def summarize_results(
    results: list[HoldoutResult],
    targets: EvaluationTargets = EvaluationTargets(),
) -> EvaluationSummary:
    f1_values = [result.metrics.f1 for result in results]
    precision_values = [result.metrics.precision for result in results]
    recall_values = [result.metrics.recall for result in results]
    amount_values = [result.metrics.amount_recall for result in results]
    f1_avg = mean(f1_values) if f1_values else 0.0
    recall_avg = mean(recall_values) if recall_values else 0.0
    amount_avg = mean(amount_values) if amount_values else 0.0
    return EvaluationSummary(
        sample_size=len(results),
        precision_avg=mean(precision_values) if precision_values else 0.0,
        precision_median=median(precision_values) if precision_values else 0.0,
        recall_avg=recall_avg,
        recall_median=median(recall_values) if recall_values else 0.0,
        f1_avg=f1_avg,
        f1_median=median(f1_values) if f1_values else 0.0,
        amount_recall_avg=amount_avg,
        amount_recall_median=median(amount_values) if amount_values else 0.0,
        target_passed=(
            f1_avg >= targets.min_f1_avg
            and recall_avg >= targets.min_recall_avg
            and amount_avg >= targets.min_amount_recall_avg
        ),
        worst_results=tuple(sorted(results, key=lambda result: result.metrics.f1)[:10]),
    )


def _evaluate_one(predictor: RecipePredictor, rcp_id: str, max_ingredients: int | None = None) -> HoldoutResult:
    prediction = predictor.predict_existing_holdout(rcp_id, max_ingredients=max_ingredients)
    actual = predictor.actual_codes(rcp_id)
    actual_amounts = predictor.actual_amounts(rcp_id)
    record = predictor.records_by_id[rcp_id]
    return HoldoutResult(
        rcp_id=rcp_id,
        product_subtype=record.product_subtype,
        form_type=record.form_type,
        metrics=ingredient_metrics(prediction.ingredient_codes, actual, actual_amounts),
    )


def _evaluate_strict_one(
    predictor: RecipePredictor,
    rcp_id: str,
    tolerance: float,
    max_ingredients: int | None = None,
) -> StrictHoldoutResult:
    prediction = predictor.predict_existing_holdout(rcp_id, max_ingredients=max_ingredients)
    actual = predictor.actual_codes(rcp_id)
    record = predictor.records_by_id[rcp_id]
    return StrictHoldoutResult(
        rcp_id=rcp_id,
        product_subtype=record.product_subtype,
        form_type=record.form_type,
        metrics=strict_deviation_metrics(
            prediction.ingredient_codes,
            actual,
            tolerance=tolerance,
        ),
    )


def _evaluate_user_defined_one(
    predictor: RecipePredictor,
    rcp_id: str,
    max_ingredients: int | None = None,
    supported_ingredient_codes: set[str] | None = None,
) -> UserDefinedHoldoutResult:
    prediction = predictor.predict_existing_holdout(rcp_id, max_ingredients=max_ingredients)
    actual_ingredients = predictor.actual_codes(rcp_id)
    predicted_ingredients = prediction.ingredient_codes
    actual_phases = {
        line.phase
        for line in predictor.lines_by_id.get(rcp_id, ())
        if line.phase
    }
    record = predictor.records_by_id[rcp_id]
    return UserDefinedHoldoutResult(
        rcp_id=rcp_id,
        product_subtype=record.product_subtype,
        form_type=record.form_type,
        metrics=user_defined_metrics(
            actual_phase_count=len(actual_phases),
            predicted_phase_count=prediction.predicted_phase_count,
            actual_ingredients=actual_ingredients,
            predicted_ingredients=predicted_ingredients,
            supported_ingredient_codes=supported_ingredient_codes,
        ),
    )
