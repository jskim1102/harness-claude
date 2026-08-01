from dataclasses import fields

from reciepe_rec.data import BulkRecord, RecipeLine
from reciepe_rec.evaluate import (
    UserDefinedHoldoutResult,
    ingredient_metrics,
    strict_deviation_metrics,
    summarize_user_defined_results,
    user_defined_metrics,
)
from reciepe_rec.predictor import RecipePredictor


def _record(
    rcp_id: str,
    subtype: str = "립틴트",
    form: str = "O/W",
    preservative: str = "1",
) -> BulkRecord:
    return BulkRecord(
        rcp_id=rcp_id,
        bulk_type="카11",
        functional="없음",
        functional_uv="해당없음",
        preservative=preservative,
        stability=None,
        product_group="메이크업",
        product_midgroup="립",
        product_subtype=subtype,
        form_type=form,
        viscosity=None,
        spindle=None,
        rpm=None,
        cutting_hardness=None,
        penetration_hardness=None,
        melting_point=None,
        ph="N/A",
        leave_on="O",
        rinse_off="X",
        gas_filling="X",
    )


def test_predictor_bulk_record_has_no_forbidden_product_name_field():
    assert "product_name" not in {field.name for field in fields(BulkRecord)}


def test_predictor_prioritizes_ingredients_from_similar_recipes():
    records = [
        _record("T"),
        _record("N1"),
        _record("N2"),
        _record("O1", subtype="파운데이션-쿠션", form="W/Si"),
    ]
    lines = [
        RecipeLine("T", "A", "WATER", "정제수", 40.0),
        RecipeLine("T", "B", "COLOR", "색소", 3.0),
        RecipeLine("N1", "A", "WATER", "정제수", 40.0),
        RecipeLine("N1", "B", "COLOR", "색소", 3.0),
        RecipeLine("N2", "A", "WATER", "정제수", 42.0),
        RecipeLine("N2", "B", "COLOR", "색소", 2.5),
        RecipeLine("O1", "A", "SILICONE", "실리콘", 20.0),
    ]

    predictor = RecipePredictor(records, lines)
    prediction = predictor.predict_existing_holdout("T", max_ingredients=2)

    assert [item.ingredient_code for item in prediction.ingredients] == ["WATER", "COLOR"]


def test_default_prediction_does_not_return_a_verbatim_known_recipe_set():
    records = [
        _record("T"),
        _record("N1"),
        _record("N2"),
        _record("N3"),
    ]
    lines = [
        RecipeLine("T", "A", "WATER", "정제수", 40.0),
        RecipeLine("T", "B", "COLOR", "색소", 3.0),
        RecipeLine("N1", "A", "WATER", "정제수", 40.0),
        RecipeLine("N1", "B", "COLOR", "색소", 3.0),
        RecipeLine("N2", "A", "WATER", "정제수", 41.0),
        RecipeLine("N2", "B", "COLOR", "색소", 2.5),
        RecipeLine("N2", "C", "OIL", "오일", 5.0),
        RecipeLine("N3", "A", "WATER", "정제수", 42.0),
        RecipeLine("N3", "B", "COLOR", "색소", 2.0),
        RecipeLine("N3", "D", "WAX", "왁스", 4.0),
    ]

    predictor = RecipePredictor(records, lines)
    prediction = predictor.predict_existing_holdout("T")

    assert prediction.similar_recipes[0].rcp_id == "N1"
    assert frozenset(prediction.ingredient_codes) not in predictor.known_recipe_code_sets


def test_similarity_ignores_forbidden_identifier_fields():
    predictor = RecipePredictor([], [])
    left = _record("RCP-FAMILY-001")
    same_allowed_fields = _record("RCP-FAMILY-002")
    different_forbidden_fields = _record("UNRELATED-ID")

    assert predictor._similarity(left, same_allowed_fields) == predictor._similarity(
        left,
        different_forbidden_fields,
    )


def test_target_recipe_lines_do_not_change_prediction_output():
    records = [
        _record("T"),
        _record("N1"),
        _record("N2"),
    ]
    training_lines = [
        RecipeLine("N1", "A", "A", "원료 A", 40.0),
        RecipeLine("N1", "B", "B", "원료 B", 20.0),
        RecipeLine("N2", "A", "A", "원료 A", 40.0),
        RecipeLine("N2", "B", "B", "원료 B", 20.0),
        RecipeLine("N2", "C", "C", "원료 C", 10.0),
        RecipeLine("N2", "D", "D", "원료 D", 5.0),
    ]
    target_lines = [
        RecipeLine("T", "A", "A", "원료 A", 40.0),
        RecipeLine("T", "B", "B", "원료 B", 20.0),
        RecipeLine("T", "C", "C", "원료 C", 10.0),
    ]
    with_target_recipe = RecipePredictor(records, training_lines + target_lines)
    without_target_recipe = RecipePredictor(records, training_lines)

    with_target = with_target_recipe.predict_existing_holdout("T").ingredient_codes
    without_target = without_target_recipe.predict(
        without_target_recipe.records_by_id["T"],
        excluded_rcp_id="T",
    ).ingredient_codes

    assert with_target == without_target


def test_allowed_preservative_field_changes_prediction_pool():
    records = [
        _record("T", preservative="1"),
        _record("N1", preservative="1"),
        _record("N2", preservative="1"),
        _record("O1", preservative="3"),
    ]
    lines = [
        RecipeLine("N1", "A", "A", "원료 A", 30.0),
        RecipeLine("N1", "B", "B", "원료 B", 20.0),
        RecipeLine("N1", "C", "C", "원료 C", 1.0),
        RecipeLine("N2", "A", "A", "원료 A", 30.0),
        RecipeLine("N2", "B", "B", "원료 B", 20.0),
        RecipeLine("N2", "D", "D", "원료 D", 1.0),
        RecipeLine("O1", "A", "X", "다른 원료 X", 30.0),
        RecipeLine("O1", "B", "Y", "다른 원료 Y", 20.0),
    ]

    prediction = RecipePredictor(records, lines).predict_existing_holdout("T")

    assert {"A", "B"} <= prediction.ingredient_codes
    assert "X" not in prediction.ingredient_codes
    assert "Y" not in prediction.ingredient_codes


def test_predictor_can_ignore_rare_training_ingredients():
    records = [
        _record("T"),
        _record("N1"),
        _record("N2"),
        _record("N3"),
    ]
    lines = [
        RecipeLine("N1", "A", "COMMON", "공통 원료", 30.0),
        RecipeLine("N1", "B", "RARE", "희귀 원료", 1.0),
        RecipeLine("N2", "A", "COMMON", "공통 원료", 30.0),
        RecipeLine("N3", "A", "COMMON", "공통 원료", 30.0),
    ]

    prediction = RecipePredictor(
        records,
        lines,
        min_ingredient_frequency=2,
    ).predict_existing_holdout("T")

    assert "COMMON" in prediction.ingredient_codes
    assert "RARE" not in prediction.ingredient_codes


def test_ingredient_metrics_compare_predicted_and_actual_sets():
    metrics = ingredient_metrics(
        predicted={"A", "B", "C"},
        actual={"A", "C", "D", "E"},
        actual_amounts={"A": 40.0, "C": 10.0, "D": 20.0, "E": 30.0},
    )

    assert metrics.hit_count == 2
    assert metrics.precision == 2 / 3
    assert metrics.recall == 0.5
    assert round(metrics.f1, 6) == round(4 / 7, 6)
    assert metrics.amount_recall == 0.5


def test_strict_deviation_metrics_require_count_and_type_within_ten_percent():
    metrics = strict_deviation_metrics(
        predicted={"A", "B", "X"},
        actual={"A", "B", "C"},
    )

    assert metrics.predicted_count == 3
    assert metrics.actual_count == 3
    assert metrics.missing_count == 1
    assert metrics.extra_count == 1
    assert metrics.count_error_ratio == 0.0
    assert metrics.type_error_ratio == 2 / 3
    assert metrics.count_within_tolerance is True
    assert metrics.type_within_tolerance is False
    assert metrics.within_tolerance is False


def test_user_defined_metrics_follow_phase_count_and_symmetric_ingredient_difference():
    metrics = user_defined_metrics(
        actual_phase_count=4,
        predicted_phase_count=3,
        actual_ingredients={"A", "B", "C"},
        predicted_ingredients={"A", "C", "X", "Y"},
    )

    assert metrics.phase_count_difference == 1
    assert metrics.phase_error_ratio == 0.25
    assert metrics.ingredient_type_difference == 3
    assert metrics.ingredient_type_error_ratio == 1.0


def test_user_defined_metrics_can_score_only_supported_ingredients():
    metrics = user_defined_metrics(
        actual_phase_count=4,
        predicted_phase_count=4,
        actual_ingredients={"COMMON", "RARE"},
        predicted_ingredients={"COMMON", "EXTRA_RARE"},
        supported_ingredient_codes={"COMMON"},
    )

    assert metrics.actual_ingredient_count == 1
    assert metrics.predicted_ingredient_count == 1
    assert metrics.ignored_actual_ingredient_count == 1
    assert metrics.ingredient_type_difference == 0
    assert metrics.ingredient_type_error_ratio == 0.0


def test_user_defined_summary_reports_target_error_rates():
    good = user_defined_metrics(
        actual_phase_count=10,
        predicted_phase_count=9,
        actual_ingredients={"A", "B", "C", "D"},
        predicted_ingredients={"A", "B", "C", "X"},
    )
    better = user_defined_metrics(
        actual_phase_count=5,
        predicted_phase_count=5,
        actual_ingredients={"A", "B"},
        predicted_ingredients={"A", "B"},
    )
    summary = summarize_user_defined_results(
        [
            UserDefinedHoldoutResult("R1", "sub", "form", good),
            UserDefinedHoldoutResult("R2", "sub", "form", better),
        ],
        phase_error_target=0.10,
        ingredient_type_error_target=0.30,
    )

    assert summary.phase_error_rate_avg == 0.05
    assert summary.ingredient_type_error_rate_avg == 0.25
    assert summary.target_passed is True
