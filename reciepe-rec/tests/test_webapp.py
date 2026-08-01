import json

import pytest

from reciepe_rec.data import BulkRecord, RecipeLine
from reciepe_rec.webapp import INDEX_HTML, RecipeWebService


def _record(
    rcp_id: str,
    subtype: str = "립틴트",
    form: str = "O/W",
) -> BulkRecord:
    return BulkRecord(
        rcp_id=rcp_id,
        bulk_type="카11",
        functional="없음",
        functional_uv="해당없음",
        preservative="1",
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


def test_web_service_rejects_forbidden_prediction_fields():
    service = RecipeWebService([_record("N1")], [RecipeLine("N1", "A", "COMMON", "공통", 1.0)])

    with pytest.raises(ValueError, match="forbidden"):
        service.predict_custom(
            {
                "bulk_type": "카11",
                "product_name": "금지된 제품명",
            }
        )


def test_sample_comparison_excludes_target_recipe_lines_from_prediction():
    records = [_record("T"), _record("N1")]
    lines = [
        RecipeLine("T", "A", "SECRET", "타깃 전용 원료", 1.0),
        RecipeLine("N1", "A", "COMMON", "공통 원료", 1.0),
    ]
    service = RecipeWebService(records, lines, pool_threshold=0.5)

    result = service.compare_sample("T")
    predicted_codes = {item["code"] for item in result["prediction"]["ingredients"]}

    assert "SECRET" not in predicted_codes
    assert result["comparison"]["raw_actual_ingredient_count"] == 1


def test_web_service_response_does_not_expose_forbidden_identity_fields():
    records = [_record("T"), _record("N1")]
    lines = [
        RecipeLine("T", "A", "SECRET", "타깃 전용 원료", 1.0),
        RecipeLine("N1", "A", "COMMON", "공통 원료", 1.0),
    ]
    service = RecipeWebService(records, lines, pool_threshold=0.5)

    payload = json.dumps(service.compare_sample("T"), ensure_ascii=False)

    assert "product_name" not in payload
    assert "제품명" not in payload
    assert "등록일" not in payload
    assert "RCP_ID" not in payload
    assert "rcp_id" not in payload


def test_sample_label_can_show_original_identity_without_reaching_predictor():
    records = [
        _record("T"),
        _record("N1"),
    ]
    lines = [
        RecipeLine("T", "A", "SECRET", "타깃 전용 원료", 1.0),
        RecipeLine("N1", "A", "COMMON", "공통 원료", 1.0),
    ]
    service = RecipeWebService(
        records,
        lines,
        pool_threshold=0.5,
        sample_labels={
            "T": "REAL-T|타깃 제품",
            "N1": "REAL-N1|이웃 제품",
        },
    )

    options = service.options()

    assert options["samples"][0]["label"] == "REAL-T|타깃 제품"
    assert not hasattr(service.records_by_sample["T"], "product_name")
    assert not hasattr(service._default_predictor.records_by_id["T"], "product_name")


def test_sample_comparison_includes_actual_recipe_and_sorts_prediction_by_phase():
    records = [_record("T"), _record("N1")]
    lines = [
        RecipeLine("T", "B", "MIDDLE", "중간 실제", 2.0),
        RecipeLine("T", "A", "FIRST", "첫 실제", 1.0),
        RecipeLine("N1", "C", "A_BOTTOM", "뒤 예측", 3.0),
        RecipeLine("N1", "A", "Z_TOP", "앞 예측", 4.0),
    ]
    service = RecipeWebService(
        records,
        lines,
        pool_threshold=0.5,
        min_ingredient_frequency=1,
    )

    result = service.compare_sample("T")

    assert [item["code"] for item in result["prediction"]["ingredients"]] == [
        "Z_TOP",
        "A_BOTTOM",
    ]
    assert result["actual_recipe"]["phase_count"] == 2
    assert [item["code"] for item in result["actual_recipe"]["ingredients"]] == [
        "FIRST",
        "MIDDLE",
    ]


def test_sample_comparison_marks_ingredient_frequency_buckets():
    records = [_record("T"), _record("N1")]
    lines = [
        RecipeLine("T", "A", "TARGET_ONLY", "타깃 전용", 1.0),
        RecipeLine("N1", "A", "PREDICTED", "예측 원료", 2.0),
    ]
    service = RecipeWebService(
        records,
        lines,
        pool_threshold=0.5,
        min_ingredient_frequency=1,
    )

    result = service.compare_sample("T")

    predicted = result["prediction"]["ingredients"][0]
    actual = result["actual_recipe"]["ingredients"][0]
    assert predicted["frequency_count"] == 1
    assert predicted["frequency_bucket"] == "lt10"
    assert predicted["frequency_bucket_label"] == "10회 미만"
    assert actual["frequency_count"] == 0
    assert actual["frequency_bucket"] == "lt10"


def test_options_include_frequency_buckets():
    service = RecipeWebService([_record("N1")], [RecipeLine("N1", "A", "COMMON", "공통", 1.0)])

    options = service.options()
    labels = [bucket["label"] for bucket in options["frequency_buckets"]]

    assert labels == [
        "10회 미만",
        "11-20회",
        "21-40회",
        "41-60회",
        "61-100회",
        "101회 이상",
    ]
    assert options["defaults"]["model"] == "statistical"


def test_ui_shows_sample_bulk_predict_button_and_result_panel():
    assert "샘플 예시" in INDEX_HTML
    assert "예측" in INDEX_HTML
    assert "예측 결과" in INDEX_HTML
    assert "실제 레시피" in INDEX_HTML
    assert 'id="predictButton"' in INDEX_HTML
    assert 'id="resultBody"' in INDEX_HTML
    assert "/api/compare" in INDEX_HTML
    assert "희귀 원료 표시" in INDEX_HTML
    assert "Anonymous Sample" not in INDEX_HTML
    assert "Threshold" not in INDEX_HTML
    assert "Min Freq" not in INDEX_HTML
    assert "Compare Sample" not in INDEX_HTML
    assert "Predict Custom" not in INDEX_HTML
    assert "Load Fields" not in INDEX_HTML
    assert "Clear" not in INDEX_HTML
    assert "prediction.model" in INDEX_HTML


def test_result_panel_uses_wide_horizontal_layout():
    assert "grid-template-columns: minmax(300px, 400px) minmax(760px, 1fr);" in INDEX_HTML
    assert "max-width: none;" in INDEX_HTML
    assert "width: 100%;" in INDEX_HTML
    assert "grid-template-columns: minmax(360px, 1fr) minmax(360px, 1fr);" in INDEX_HTML
    assert "table-layout: auto;" in INDEX_HTML


def test_actual_recipe_rows_are_colored_by_prediction_hit_status():
    assert ".actual-hit" in INDEX_HTML
    assert ".actual-miss" in INDEX_HTML
    assert "hit_codes" in INDEX_HTML
    assert "actual-hit" in INDEX_HTML
    assert "actual-miss" in INDEX_HTML


def test_predicted_recipe_rows_are_colored_by_actual_hit_status():
    assert ".predicted-hit" in INDEX_HTML
    assert ".predicted-extra" in INDEX_HTML
    assert "predicted-hit" in INDEX_HTML
    assert "predicted-extra" in INDEX_HTML


def test_frequency_bucket_checkboxes_apply_black_highlight():
    assert "frequency_buckets" in INDEX_HTML
    assert 'id="frequencyBuckets"' in INDEX_HTML
    assert ".rare-highlight" in INDEX_HTML
    assert "selectedFrequencyBuckets" in INDEX_HTML
    assert "frequency_bucket" in INDEX_HTML
