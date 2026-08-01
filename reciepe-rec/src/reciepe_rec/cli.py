from __future__ import annotations

import argparse
import json
from pathlib import Path

from .data import load_anonymized_web_dataset, load_dataset
from .evaluate import (
    EvaluationTargets,
    evaluate_random_holdouts,
    evaluate_strict_all,
    evaluate_user_defined_all,
    ingredient_metrics,
)
from .predictor import DEFAULT_POOL_THRESHOLD, RecipePredictor


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate and run recipe ingredient prediction.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument(
        "--model",
        choices=("catboost", "statistical"),
        default="catboost",
        help="prediction engine (default: leakage-controlled CatBoost selector)",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=20,
        help="CatBoost training threads",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--sample-size", type=int, default=250)
    evaluate_parser.add_argument("--seed", type=int, default=7)
    evaluate_parser.add_argument("--target-f1", type=float, default=0.65)
    evaluate_parser.add_argument("--target-recall", type=float, default=0.65)
    evaluate_parser.add_argument("--target-amount-recall", type=float, default=0.80)
    evaluate_parser.add_argument("--max-ingredients", type=int, default=None)

    strict_parser = subparsers.add_parser("strict-evaluate")
    strict_parser.add_argument("--tolerance", type=float, default=0.10)
    strict_parser.add_argument("--max-ingredients", type=int, default=None)

    user_metric_parser = subparsers.add_parser("user-metrics")
    user_metric_parser.add_argument("--max-ingredients", type=int, default=None)
    user_metric_parser.add_argument("--phase-error-target", type=float, default=0.10)
    user_metric_parser.add_argument("--ingredient-type-error-target", type=float, default=0.30)
    user_metric_parser.add_argument("--pool-threshold", type=float, default=DEFAULT_POOL_THRESHOLD)
    user_metric_parser.add_argument("--min-ingredient-frequency", type=int, default=1)

    predict_parser = subparsers.add_parser("predict-existing")
    predict_parser.add_argument("rcp_id")
    predict_parser.add_argument("--max-ingredients", type=int, default=None)

    compare_parser = subparsers.add_parser("compare-existing")
    compare_parser.add_argument("rcp_id")
    compare_parser.add_argument("--max-ingredients", type=int, default=None)

    subparsers.add_parser(
        "ml-evaluate",
        help="reproduce the CatBoost selector's strict 5-fold crossfit metric",
    )

    args = parser.parse_args(argv)
    sample_labels: dict[str, str] = {}
    if args.model == "catboost":
        from .ml_predictor import CatBoostRecipePredictor

        records, lines, sample_labels = load_anonymized_web_dataset(
            Path(args.data_dir)
        )
        predictor = CatBoostRecipePredictor(
            records,
            lines,
            thread_count=args.threads,
        )
    else:
        if args.command == "ml-evaluate":
            parser.error("ml-evaluate requires --model catboost")
        records, lines = load_dataset(Path(args.data_dir))
        predictor = RecipePredictor(
            records,
            lines,
            pool_threshold=getattr(
                args,
                "pool_threshold",
                DEFAULT_POOL_THRESHOLD,
            ),
            min_ingredient_frequency=getattr(
                args,
                "min_ingredient_frequency",
                1,
            ),
        )

    if args.command == "ml-evaluate":
        print(
            json.dumps(
                predictor.evaluate_crossfit(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "evaluate":
        summary = evaluate_random_holdouts(
            predictor,
            sample_size=args.sample_size,
            seed=args.seed,
            targets=EvaluationTargets(
                min_f1_avg=args.target_f1,
                min_recall_avg=args.target_recall,
                min_amount_recall_avg=args.target_amount_recall,
            ),
            max_ingredients=args.max_ingredients,
        )
        print(json.dumps(_summary_to_dict(summary), ensure_ascii=False, indent=2))
        return 0 if summary.target_passed else 1

    if args.command == "strict-evaluate":
        summary = evaluate_strict_all(
            predictor,
            tolerance=args.tolerance,
            max_ingredients=args.max_ingredients,
        )
        print(json.dumps(_strict_summary_to_dict(summary), ensure_ascii=False, indent=2))
        return 0 if summary.target_passed else 1

    if args.command == "user-metrics":
        summary = evaluate_user_defined_all(
            predictor,
            max_ingredients=args.max_ingredients,
            phase_error_target=args.phase_error_target,
            ingredient_type_error_target=args.ingredient_type_error_target,
            supported_ingredient_codes=(
                predictor.supported_ingredient_codes
                if (
                    args.model == "catboost"
                    or args.min_ingredient_frequency > 1
                )
                else None
            ),
        )
        print(json.dumps(_user_defined_summary_to_dict(summary), ensure_ascii=False, indent=2))
        return 0 if summary.target_passed else 1

    if args.command == "predict-existing":
        rcp_id = _resolve_rcp_id(args.rcp_id, predictor, sample_labels)
        prediction = predictor.predict_existing_holdout(
            rcp_id,
            max_ingredients=args.max_ingredients,
        )
        print(json.dumps(_prediction_to_dict(prediction), ensure_ascii=False, indent=2))
        return 0

    if args.command == "compare-existing":
        rcp_id = _resolve_rcp_id(args.rcp_id, predictor, sample_labels)
        prediction = predictor.predict_existing_holdout(
            rcp_id,
            max_ingredients=args.max_ingredients,
        )
        actual = predictor.actual_codes(rcp_id)
        actual_amounts = predictor.actual_amounts(rcp_id)
        metrics = ingredient_metrics(prediction.ingredient_codes, actual, actual_amounts)
        print(json.dumps(_comparison_to_dict(prediction, actual, metrics), ensure_ascii=False, indent=2))
        return 0

    raise AssertionError(args.command)


def _resolve_rcp_id(
    requested: str,
    predictor,
    sample_labels: dict[str, str],
) -> str:
    if requested in predictor.records_by_id:
        return requested
    for anonymous_id, label in sample_labels.items():
        original_id = label.split("|", 1)[0]
        if original_id == requested:
            return anonymous_id
    raise ValueError(f"unknown RCP_ID: {requested}")


def _summary_to_dict(summary) -> dict:
    return {
        "sample_size": summary.sample_size,
        "target_passed": summary.target_passed,
        "precision": {
            "avg": round(summary.precision_avg, 6),
            "median": round(summary.precision_median, 6),
        },
        "recall": {
            "avg": round(summary.recall_avg, 6),
            "median": round(summary.recall_median, 6),
        },
        "f1": {
            "avg": round(summary.f1_avg, 6),
            "median": round(summary.f1_median, 6),
        },
        "amount_recall": {
            "avg": round(summary.amount_recall_avg, 6),
            "median": round(summary.amount_recall_median, 6),
        },
        "worst_results": [
            {
                "rcp_id": result.rcp_id,
                "product_subtype": result.product_subtype,
                "form_type": result.form_type,
                "actual_count": result.metrics.actual_count,
                "predicted_count": result.metrics.predicted_count,
                "hit_count": result.metrics.hit_count,
                "precision": round(result.metrics.precision, 6),
                "recall": round(result.metrics.recall, 6),
                "f1": round(result.metrics.f1, 6),
                "amount_recall": round(result.metrics.amount_recall, 6),
            }
            for result in summary.worst_results
        ],
    }


def _strict_summary_to_dict(summary) -> dict:
    return {
        "sample_size": summary.sample_size,
        "tolerance": summary.tolerance,
        "target_passed": summary.target_passed,
        "pass_counts": {
            "both": summary.both_pass_count,
            "count": summary.count_pass_count,
            "type": summary.type_pass_count,
        },
        "pass_rates": {
            "both": round(summary.both_pass_rate, 6),
            "count": round(summary.count_pass_rate, 6),
            "type": round(summary.type_pass_rate, 6),
        },
        "count_error": {
            "avg": round(summary.count_error_avg, 6),
            "median": round(summary.count_error_median, 6),
        },
        "type_error": {
            "avg": round(summary.type_error_avg, 6),
            "median": round(summary.type_error_median, 6),
        },
        "worst_results": [
            {
                "rcp_id": result.rcp_id,
                "product_subtype": result.product_subtype,
                "form_type": result.form_type,
                "actual_count": result.metrics.actual_count,
                "predicted_count": result.metrics.predicted_count,
                "hit_count": result.metrics.hit_count,
                "missing_count": result.metrics.missing_count,
                "extra_count": result.metrics.extra_count,
                "count_error_ratio": round(result.metrics.count_error_ratio, 6),
                "type_error_ratio": round(result.metrics.type_error_ratio, 6),
                "count_within_tolerance": result.metrics.count_within_tolerance,
                "type_within_tolerance": result.metrics.type_within_tolerance,
                "within_tolerance": result.metrics.within_tolerance,
            }
            for result in summary.worst_results
        ],
    }


def _user_defined_summary_to_dict(summary) -> dict:
    return {
        "sample_size": summary.sample_size,
        "target_passed": summary.target_passed,
        "targets": {
            "phase_error_rate_avg_max_percent": round(summary.phase_error_target * 100.0, 6),
            "ingredient_type_error_rate_avg_max_percent": round(summary.ingredient_type_error_target * 100.0, 6),
        },
        "phase_error_rate": {
            "formula": "avg(abs(actual_phase_count - predicted_phase_count) / actual_phase_count) * 100",
            "avg_percent": round(summary.phase_error_rate_avg * 100.0, 6),
            "median_percent": round(summary.phase_error_rate_median * 100.0, 6),
            "target_passed": summary.phase_error_rate_avg <= summary.phase_error_target,
        },
        "ingredient_type_error_rate": {
            "formula": "avg(count(actual_ingredient_codes symmetric_difference predicted_ingredient_codes) / actual_ingredient_count) * 100",
            "avg_percent": round(summary.ingredient_type_error_rate_avg * 100.0, 6),
            "median_percent": round(summary.ingredient_type_error_rate_median * 100.0, 6),
            "target_passed": summary.ingredient_type_error_rate_avg <= summary.ingredient_type_error_target,
        },
        "ingredient_support_coverage": {
            "formula": "1 - ignored_actual_ingredient_count / raw_actual_ingredient_count",
            "coverage_percent": round(summary.ingredient_support_coverage_rate * 100.0, 6),
            "raw_actual_ingredient_count": summary.total_raw_actual_ingredient_count,
            "ignored_actual_ingredient_count": summary.total_ignored_actual_ingredient_count,
        },
        "phase_metric": {
            "formula": "sum(abs(actual_phase_count - predicted_phase_count)) / RCP_ID_count * 100",
            "value": round(summary.phase_score, 6),
            "total_difference": summary.total_phase_count_difference,
            "difference_avg": round(summary.phase_difference_avg, 6),
            "difference_median": round(summary.phase_difference_median, 6),
        },
        "ingredient_type_metric": {
            "formula": "sum(count(actual_ingredient_codes symmetric_difference predicted_ingredient_codes)) / RCP_ID_count * 100",
            "value": round(summary.ingredient_type_score, 6),
            "total_difference": summary.total_ingredient_type_difference,
            "difference_avg": round(summary.ingredient_type_difference_avg, 6),
            "difference_median": round(summary.ingredient_type_difference_median, 6),
        },
        "worst_phase_results": [
            _user_defined_result_to_dict(result)
            for result in summary.worst_phase_results
        ],
        "worst_ingredient_results": [
            _user_defined_result_to_dict(result)
            for result in summary.worst_ingredient_results
        ],
    }


def _user_defined_result_to_dict(result) -> dict:
    return {
        "rcp_id": result.rcp_id,
        "product_subtype": result.product_subtype,
        "form_type": result.form_type,
        "actual_phase_count": result.metrics.actual_phase_count,
        "predicted_phase_count": result.metrics.predicted_phase_count,
        "phase_count_difference": result.metrics.phase_count_difference,
        "actual_ingredient_count": result.metrics.actual_ingredient_count,
        "raw_actual_ingredient_count": result.metrics.raw_actual_ingredient_count,
        "ignored_actual_ingredient_count": result.metrics.ignored_actual_ingredient_count,
        "predicted_ingredient_count": result.metrics.predicted_ingredient_count,
        "ingredient_type_difference": result.metrics.ingredient_type_difference,
        "phase_error_rate_percent": round(result.metrics.phase_error_ratio * 100.0, 6),
        "ingredient_type_error_rate_percent": round(result.metrics.ingredient_type_error_ratio * 100.0, 6),
    }


def _prediction_to_dict(prediction) -> dict:
    return {
        "target_rcp_id": prediction.target_rcp_id,
        "model": prediction.model_name,
        "candidate_score": prediction.candidate_score,
        "candidate_level": prediction.candidate_level,
        "predicted_count": prediction.predicted_count,
        "predicted_phase_count": prediction.predicted_phase_count,
        "similar_recipes": [
            {
                "rcp_id": item.rcp_id,
                "score": item.score,
            }
            for item in prediction.similar_recipes
        ],
        "ingredients": [
            {
                "code": item.ingredient_code,
                "name": item.ingredient_name,
                "score": item.score,
                "median_amount": item.median_amount,
                "neighbor_count": item.neighbor_count,
                "typical_phase": item.typical_phase,
            }
            for item in prediction.ingredients
        ],
    }


def _comparison_to_dict(prediction, actual: set[str], metrics) -> dict:
    predicted = prediction.ingredient_codes
    hit = predicted & actual
    return {
        "target_rcp_id": prediction.target_rcp_id,
        "model": prediction.model_name,
        "candidate_score": prediction.candidate_score,
        "candidate_level": prediction.candidate_level,
        "actual_count": metrics.actual_count,
        "predicted_count": metrics.predicted_count,
        "hit_count": metrics.hit_count,
        "precision": round(metrics.precision, 6),
        "recall": round(metrics.recall, 6),
        "f1": round(metrics.f1, 6),
        "amount_recall": round(metrics.amount_recall, 6),
        "hit_codes": sorted(hit),
        "missing_codes": sorted(actual - predicted),
        "extra_codes": sorted(predicted - actual),
        "similar_recipes": [
            {
                "rcp_id": item.rcp_id,
                "score": item.score,
            }
            for item in prediction.similar_recipes
        ],
    }


if __name__ == "__main__":
    raise SystemExit(main())
