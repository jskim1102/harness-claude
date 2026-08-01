from __future__ import annotations

import argparse
from dataclasses import dataclass
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .data import BulkRecord, RecipeLine, load_anonymized_web_dataset
from .evaluate import user_defined_metrics
from .predictor import RecipePrediction, RecipePredictor


DEFAULT_WEB_POOL_THRESHOLD = 0.58
DEFAULT_WEB_MIN_INGREDIENT_FREQUENCY = 60

ALLOWED_BULK_FIELDS = (
    "bulk_type",
    "functional",
    "functional_uv",
    "preservative",
    "stability",
    "product_group",
    "product_midgroup",
    "product_subtype",
    "form_type",
    "viscosity",
    "spindle",
    "rpm",
    "cutting_hardness",
    "penetration_hardness",
    "melting_point",
    "ph",
    "leave_on",
    "rinse_off",
    "gas_filling",
)

FREQUENCY_BUCKETS = (
    {"id": "lt10", "label": "10회 미만", "min": 0, "max": 9},
    {"id": "11_20", "label": "11-20회", "min": 11, "max": 20},
    {"id": "21_40", "label": "21-40회", "min": 21, "max": 40},
    {"id": "41_60", "label": "41-60회", "min": 41, "max": 60},
    {"id": "61_100", "label": "61-100회", "min": 61, "max": 100},
    {"id": "101_plus", "label": "101회 이상", "min": 101, "max": None},
)

FIELD_LABELS = {
    "bulk_type": "벌크유형",
    "functional": "기능성",
    "functional_uv": "유/무기",
    "preservative": "방부력",
    "stability": "안정도",
    "product_group": "대그룹",
    "product_midgroup": "중그룹",
    "product_subtype": "소그룹",
    "form_type": "제형",
    "viscosity": "점도",
    "spindle": "Spindle",
    "rpm": "rpm",
    "cutting_hardness": "절단경도",
    "penetration_hardness": "침입경도",
    "melting_point": "융점",
    "ph": "pH",
    "leave_on": "Leave-on",
    "rinse_off": "Rinse-off",
    "gas_filling": "가스충진",
}

FORBIDDEN_PAYLOAD_FIELDS = {
    "rcp_id",
    "rcp-id",
    "rcpid",
    "rcp",
    "RCP_ID",
    "RCP_ID(벌크품번)",
    "product_name",
    "제품명",
    "registration_date",
    "registered_at",
    "등록일",
    "등록일자",
}


@dataclass(frozen=True)
class WebSettings:
    pool_threshold: float = DEFAULT_WEB_POOL_THRESHOLD
    min_ingredient_frequency: int = DEFAULT_WEB_MIN_INGREDIENT_FREQUENCY


class RecipeWebService:
    def __init__(
        self,
        records: list[BulkRecord],
        lines: list[RecipeLine],
        pool_threshold: float = DEFAULT_WEB_POOL_THRESHOLD,
        min_ingredient_frequency: int = DEFAULT_WEB_MIN_INGREDIENT_FREQUENCY,
        sample_labels: dict[str, str] | None = None,
        model: str = "statistical",
        thread_count: int = 20,
    ):
        if model not in {"catboost", "statistical"}:
            raise ValueError(f"unknown model: {model}")
        self.model = model
        labels = sample_labels or {}
        self.sample_labels = {
            record.rcp_id: labels.get(record.rcp_id, record.rcp_id)
            for record in records
        }
        self.records = records
        self.lines = lines
        self.records_by_sample = {record.rcp_id: record for record in self.records}
        self.default_settings = WebSettings(
            pool_threshold=pool_threshold,
            min_ingredient_frequency=min_ingredient_frequency,
        )
        if self.model == "catboost":
            from .ml_predictor import CatBoostRecipePredictor

            self._default_predictor = CatBoostRecipePredictor(
                self.records,
                self.lines,
                thread_count=thread_count,
            )
        else:
            self._default_predictor = self._build_predictor(
                None,
                self.default_settings,
            )

    def options(self) -> dict[str, Any]:
        return {
            "fields": [
                {
                    "name": field,
                    "label": FIELD_LABELS[field],
                    "values": self._field_values(field),
                }
                for field in ALLOWED_BULK_FIELDS
            ],
            "samples": [
                {
                    "sample": record.rcp_id,
                    "label": self.sample_labels[record.rcp_id],
                    "product_midgroup": record.product_midgroup,
                    "product_subtype": record.product_subtype,
                    "form_type": record.form_type,
                    "bulk": self._record_bulk(record),
                }
                for record in self.records
            ],
            "defaults": {
                "model": self._default_predictor.model_name,
                "pool_threshold": (
                    self.default_settings.pool_threshold
                    if self.model == "statistical"
                    else None
                ),
                "min_ingredient_frequency": (
                    self.default_settings.min_ingredient_frequency
                    if self.model == "statistical"
                    else 21
                ),
            },
            "frequency_buckets": list(FREQUENCY_BUCKETS),
        }

    def predict_custom(
        self,
        bulk: dict[str, Any],
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._reject_forbidden_fields(bulk)
        resolved = self._settings(settings)
        request = BulkRecord(
            rcp_id="REQUEST",
            **{
                field: self._optional_string(bulk.get(field))
                for field in ALLOWED_BULK_FIELDS
            },
        )
        predictor = (
            self._default_predictor
            if (
                self.model == "catboost"
                or resolved == self.default_settings
            )
            else self._build_predictor(None, resolved)
        )
        prediction = predictor.predict(request)
        return {
            "prediction": self._prediction_to_response(prediction, predictor, resolved),
        }

    def compare_sample(
        self,
        sample: str,
        settings: dict[str, Any] | None = None,
        bulk: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        record = self.records_by_sample.get(sample)
        if record is None:
            raise ValueError("unknown sample")
        request = record
        if bulk is not None:
            self._reject_forbidden_fields(bulk)
            request = BulkRecord(
                rcp_id=sample,
                **{
                    field: self._optional_string(bulk.get(field))
                    for field in ALLOWED_BULK_FIELDS
                },
            )
        resolved = self._settings(settings)
        predictor = self._build_predictor(sample, resolved)
        prediction = predictor.predict(request, excluded_rcp_id=sample)
        actual_codes = {
            line.ingredient_code
            for line in self.lines
            if line.rcp_id == sample
        }
        actual_phases = {
            line.phase
            for line in self.lines
            if line.rcp_id == sample and line.phase
        }
        supported_codes = (
            predictor.supported_ingredient_codes
            if (
                self.model == "catboost"
                or resolved.min_ingredient_frequency > 1
            )
            else None
        )
        metrics = user_defined_metrics(
            actual_phase_count=len(actual_phases),
            predicted_phase_count=prediction.predicted_phase_count,
            actual_ingredients=actual_codes,
            predicted_ingredients=prediction.ingredient_codes,
            supported_ingredient_codes=supported_codes,
        )
        supported_actual = (
            actual_codes & supported_codes
            if supported_codes is not None
            else set(actual_codes)
        )
        supported_predicted = (
            prediction.ingredient_codes & supported_codes
            if supported_codes is not None
            else set(prediction.ingredient_codes)
        )
        return {
            "sample": sample,
            "bulk": self._record_bulk(request),
            "prediction": self._prediction_to_response(prediction, predictor, resolved),
            "actual_recipe": self._actual_recipe_to_response(sample, predictor),
            "comparison": {
                "actual_phase_count": metrics.actual_phase_count,
                "predicted_phase_count": metrics.predicted_phase_count,
                "phase_error_percent": round(metrics.phase_error_ratio * 100.0, 6),
                "raw_actual_ingredient_count": metrics.raw_actual_ingredient_count,
                "actual_ingredient_count": metrics.actual_ingredient_count,
                "ignored_actual_ingredient_count": metrics.ignored_actual_ingredient_count,
                "predicted_ingredient_count": metrics.predicted_ingredient_count,
                "ingredient_type_difference": metrics.ingredient_type_difference,
                "ingredient_type_error_percent": round(
                    metrics.ingredient_type_error_ratio * 100.0,
                    6,
                ),
                "missing_codes": sorted(supported_actual - supported_predicted),
                "extra_codes": sorted(supported_predicted - supported_actual),
                "hit_codes": sorted(supported_actual & supported_predicted),
            },
        }

    def _build_predictor(
        self,
        excluded_sample: str | None,
        settings: WebSettings,
    ) -> RecipePredictor:
        if self.model == "catboost":
            return self._default_predictor
        lines = (
            [line for line in self.lines if line.rcp_id != excluded_sample]
            if excluded_sample is not None
            else self.lines
        )
        return RecipePredictor(
            self.records,
            lines,
            pool_threshold=settings.pool_threshold,
            min_ingredient_frequency=settings.min_ingredient_frequency,
        )

    def _settings(self, payload: dict[str, Any] | None) -> WebSettings:
        if payload is None:
            return self.default_settings
        self._reject_forbidden_fields(payload)
        threshold = float(payload.get("pool_threshold", self.default_settings.pool_threshold))
        frequency = int(
            payload.get(
                "min_ingredient_frequency",
                self.default_settings.min_ingredient_frequency,
            )
        )
        if threshold <= 0 or threshold >= 1:
            raise ValueError("pool_threshold must be between 0 and 1")
        if frequency < 1:
            raise ValueError("min_ingredient_frequency must be positive")
        return WebSettings(
            pool_threshold=threshold,
            min_ingredient_frequency=frequency,
        )

    def _prediction_to_response(
        self,
        prediction: RecipePrediction,
        predictor: RecipePredictor,
        settings: WebSettings,
    ) -> dict[str, Any]:
        return {
            "predicted_count": prediction.predicted_count,
            "predicted_phase_count": prediction.predicted_phase_count,
            "model": prediction.model_name,
            "candidate_score": prediction.candidate_score,
            "candidate_level": prediction.candidate_level,
            "settings": {
                "pool_threshold": (
                    settings.pool_threshold
                    if self.model == "statistical"
                    else None
                ),
                "min_ingredient_frequency": (
                    settings.min_ingredient_frequency
                    if self.model == "statistical"
                    else 21
                ),
                "supported_ingredient_count": len(predictor.supported_ingredient_codes),
            },
            "ingredients": [
                {
                    "code": item.ingredient_code,
                    "label": item.ingredient_name,
                    "score": item.score,
                    "median_amount": item.median_amount,
                    "neighbor_count": item.neighbor_count,
                    "typical_phase": item.typical_phase,
                    **self._frequency_to_response(
                        predictor.global_code_counts.get(item.ingredient_code, 0),
                    ),
                }
                for item in sorted(
                    prediction.ingredients,
                    key=lambda item: self._ingredient_sort_key(
                        item.typical_phase,
                        item.ingredient_code,
                    ),
                )
            ],
        }

    def _actual_recipe_to_response(
        self,
        sample: str,
        predictor: RecipePredictor,
    ) -> dict[str, Any]:
        lines = [
            line
            for line in self.lines
            if line.rcp_id == sample
        ]
        phases = {
            line.phase
            for line in lines
            if line.phase
        }
        return {
            "phase_count": len(phases),
            "ingredient_count": len({line.ingredient_code for line in lines}),
            "ingredients": [
                {
                    "phase": line.phase,
                    "code": line.ingredient_code,
                    "label": line.ingredient_name,
                    "amount": round(line.amount, 6),
                    **self._frequency_to_response(
                        predictor.global_code_counts.get(line.ingredient_code, 0),
                    ),
                }
                for line in sorted(
                    lines,
                    key=lambda line: self._ingredient_sort_key(
                        line.phase,
                        line.ingredient_code,
                    ),
                )
            ],
        }

    @staticmethod
    def _frequency_to_response(count: int) -> dict[str, Any]:
        bucket = RecipeWebService._frequency_bucket(count)
        return {
            "frequency_count": count,
            "frequency_bucket": bucket["id"] if bucket else None,
            "frequency_bucket_label": bucket["label"] if bucket else f"{count}회",
        }

    @staticmethod
    def _frequency_bucket(count: int) -> dict[str, Any] | None:
        for bucket in FREQUENCY_BUCKETS:
            maximum = bucket["max"]
            if count >= bucket["min"] and (maximum is None or count <= maximum):
                return bucket
        return None

    def _field_values(self, field: str) -> list[str]:
        return sorted(
            {
                value
                for record in self.records
                if (value := getattr(record, field)) not in (None, "")
            }
        )

    @staticmethod
    def _record_bulk(record: BulkRecord) -> dict[str, str | None]:
        return {
            field: getattr(record, field)
            for field in ALLOWED_BULK_FIELDS
        }

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _reject_forbidden_fields(cls, payload: dict[str, Any]) -> None:
        for key, value in payload.items():
            if key in FORBIDDEN_PAYLOAD_FIELDS:
                raise ValueError(f"forbidden field: {key}")
            if isinstance(value, dict):
                cls._reject_forbidden_fields(value)

    @staticmethod
    def _ingredient_sort_key(phase: str | None, code: str) -> tuple[str, str]:
        return (phase or "\uffff", code)


def make_handler(service: RecipeWebService):
    class RecipeRequestHandler(BaseHTTPRequestHandler):
        server_version = "RecipeRecWeb/0.1"

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path == "/":
                self._send_html(INDEX_HTML)
                return
            if path == "/api/options":
                self._send_json(service.options())
                return
            if path == "/api/health":
                status = getattr(
                    service._default_predictor,
                    "model_status",
                    {"name": "statistical"},
                )
                self._send_json({"ok": True, "model": status})
                return
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            try:
                payload = self._read_json()
                if path == "/api/predict":
                    self._send_json(
                        service.predict_custom(
                            payload.get("bulk", {}),
                            payload.get("settings"),
                        )
                    )
                    return
                if path == "/api/compare":
                    self._send_json(
                        service.compare_sample(
                            str(payload.get("sample", "")),
                            payload.get("settings"),
                            payload.get("bulk"),
                        )
                    )
                    return
                self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            except json.JSONDecodeError:
                self._send_json({"error": "invalid json"}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else "{}"
            value = json.loads(body)
            if not isinstance(value, dict):
                raise ValueError("json object required")
            return value

        def _send_json(
            self,
            payload: dict[str, Any],
            status: HTTPStatus = HTTPStatus.OK,
        ) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, payload: str) -> None:
            body = payload.encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return RecipeRequestHandler


def run_server(
    data_dir: Path,
    host: str,
    port: int,
    pool_threshold: float,
    min_ingredient_frequency: int,
    model: str = "catboost",
    thread_count: int = 20,
) -> None:
    records, lines, sample_labels = load_anonymized_web_dataset(data_dir)
    service = RecipeWebService(
        records,
        lines,
        pool_threshold=pool_threshold,
        min_ingredient_frequency=min_ingredient_frequency,
        sample_labels=sample_labels,
        model=model,
        thread_count=thread_count,
    )
    server = ThreadingHTTPServer((host, port), make_handler(service))
    print(f"Serving recipe predictor at http://{host}:{port}")
    server.serve_forever()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the recipe predictor web UI.")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--model",
        choices=("catboost", "statistical"),
        default="catboost",
    )
    parser.add_argument("--threads", type=int, default=20)
    parser.add_argument("--pool-threshold", type=float, default=DEFAULT_WEB_POOL_THRESHOLD)
    parser.add_argument(
        "--min-ingredient-frequency",
        type=int,
        default=DEFAULT_WEB_MIN_INGREDIENT_FREQUENCY,
    )
    args = parser.parse_args(argv)
    run_server(
        data_dir=Path(args.data_dir),
        host=args.host,
        port=args.port,
        pool_threshold=args.pool_threshold,
        min_ingredient_frequency=args.min_ingredient_frequency,
        model=args.model,
        thread_count=args.threads,
    )
    return 0


INDEX_HTML = """<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Recipe Predictor</title>
  <style>
    :root {
      --bg: #f6f7f9;
      --panel: #ffffff;
      --ink: #1f2937;
      --muted: #667085;
      --line: #d9dee7;
      --accent: #116466;
      --accent-2: #c2410c;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--bg);
      color: var(--ink);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }
    header {
      height: 58px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0 22px;
      border-bottom: 1px solid var(--line);
      background: #ffffff;
    }
    h1 { font-size: 18px; margin: 0; letter-spacing: 0; }
    main {
      display: grid;
      grid-template-columns: minmax(300px, 400px) minmax(760px, 1fr);
      gap: 16px;
      padding: 16px;
      width: 100%;
      max-width: none;
      margin: 0 auto;
    }
    section {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      min-width: 0;
    }
    .panel-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }
    h2 { font-size: 14px; margin: 0; }
    .body { padding: 16px; }
    .actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 14px;
    }
    button {
      min-height: 36px;
      border: 1px solid var(--accent);
      border-radius: 6px;
      padding: 8px 14px;
      background: var(--accent);
      color: #fff;
      font: inherit;
      font-weight: 650;
      cursor: pointer;
    }
    button:disabled {
      cursor: wait;
      opacity: 0.62;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }
    .rare-panel {
      margin: 12px 0;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 8px;
    }
    .rare-title {
      margin-bottom: 8px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    .rare-options {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }
    .rare-options label {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .rare-options input {
      width: auto;
      min-height: 0;
    }
    label { display: grid; gap: 5px; color: var(--muted); font-size: 12px; }
    input, select {
      width: 100%;
      min-height: 34px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 7px 9px;
      background: #fff;
      color: var(--ink);
      font: inherit;
    }
    .status { color: var(--muted); font-size: 12px; }
    .error { color: var(--accent-2); font-weight: 650; }
    .empty {
      color: var(--muted);
      min-height: 120px;
      display: grid;
      place-items: center;
      text-align: center;
    }
    .metrics {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 14px;
    }
    .result-columns {
      display: grid;
      grid-template-columns: minmax(360px, 1fr) minmax(360px, 1fr);
      gap: 14px;
      align-items: start;
    }
    .result-title {
      margin: 0 0 8px;
      font-size: 13px;
    }
    .metric {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 10px;
    }
    .metric span {
      display: block;
      color: var(--muted);
      font-size: 12px;
    }
    .metric strong {
      display: block;
      margin-top: 4px;
      font-size: 18px;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      table-layout: auto;
    }
    th, td {
      border-bottom: 1px solid var(--line);
      padding: 8px 6px;
      text-align: left;
      vertical-align: top;
      word-break: break-word;
    }
    th {
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }
    td.num, th.num { text-align: right; }
    .actual-hit td {
      color: #0f7a3b;
      font-weight: 650;
    }
    .actual-miss td {
      color: #b42318;
      font-weight: 650;
    }
    .predicted-hit td {
      color: #0f7a3b;
      font-weight: 650;
    }
    .predicted-extra td {
      color: #b7791f;
      font-weight: 650;
    }
    .rare-highlight td {
      background: #111827;
      color: #ffffff;
    }
    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      .result-columns { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Recipe Predictor</h1>
    <div class="status" id="status">loading</div>
  </header>
  <main>
    <section>
      <div class="panel-head"><h2>Input</h2></div>
      <div class="body">
        <label>샘플 예시<select id="sample"></select></label>
        <div class="rare-panel">
          <div class="rare-title">희귀 원료 표시</div>
          <div class="rare-options" id="frequencyBuckets"></div>
        </div>
        <div class="grid" id="bulkFields"></div>
        <div class="actions">
          <button id="predictButton" type="button">예측</button>
        </div>
      </div>
    </section>
    <section>
      <div class="panel-head"><h2>예측 결과</h2></div>
      <div class="body" id="resultBody">
        <div class="empty">예측 버튼을 누르면 결과가 표시됩니다.</div>
      </div>
    </section>
  </main>
  <script>
    const state = {
      fields: [],
      samples: [],
      frequency_buckets: [],
      selectedFrequencyBuckets: new Set(),
      lastComparison: null,
      model: "",
    };
    const $ = (id) => document.getElementById(id);

    function renderFields() {
      const wrap = $("bulkFields");
      wrap.innerHTML = "";
      for (const field of state.fields) {
        const label = document.createElement("label");
        label.textContent = field.label;
        const input = document.createElement("input");
        input.id = "field_" + field.name;
        input.setAttribute("list", "list_" + field.name);
        const datalist = document.createElement("datalist");
        datalist.id = "list_" + field.name;
        for (const value of field.values) {
          const option = document.createElement("option");
          option.value = value;
          datalist.appendChild(option);
        }
        label.appendChild(input);
        label.appendChild(datalist);
        wrap.appendChild(label);
      }
    }

    function renderSamples() {
      const select = $("sample");
      select.innerHTML = "";
      for (const sample of state.samples) {
        const option = document.createElement("option");
        option.value = sample.sample;
        option.textContent = sample.label;
        select.appendChild(option);
      }
    }

    function renderFrequencyBuckets() {
      const wrap = $("frequencyBuckets");
      wrap.innerHTML = "";
      for (const bucket of state.frequency_buckets) {
        const label = document.createElement("label");
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = bucket.id;
        input.onchange = () => {
          if (input.checked) state.selectedFrequencyBuckets.add(bucket.id);
          else state.selectedFrequencyBuckets.delete(bucket.id);
          if (state.lastComparison) renderComparison(state.lastComparison);
        };
        label.appendChild(input);
        label.appendChild(document.createTextNode(bucket.label));
        wrap.appendChild(label);
      }
    }

    function loadSampleFields() {
      const sample = state.samples.find((item) => item.sample === $("sample").value);
      if (!sample) return;
      for (const field of state.fields) $("field_" + field.name).value = sample.bulk[field.name] || "";
    }

    function collectBulk() {
      const bulk = {};
      for (const field of state.fields) bulk[field.name] = $("field_" + field.name).value;
      return bulk;
    }

    function renderRecipeTable(items, amountKey, rowClassForItem = null) {
      const rows = items.map((item) => `
        <tr class="${rowClassForItem ? rowClassForItem(item) : ""}">
          <td>${escapeHtml(item.typical_phase || item.phase || "")}</td>
          <td>${escapeHtml(item.code)}</td>
          <td>${escapeHtml(item.label)}</td>
          <td>${escapeHtml(item.frequency_count)}</td>
          <td class="num">${Number(item[amountKey]).toFixed(4)}</td>
        </tr>
      `).join("");
      return `
        <table>
          <thead>
            <tr>
              <th>상</th>
              <th>원료코드</th>
              <th>원료명</th>
              <th>빈도</th>
              <th class="num">함량</th>
            </tr>
          </thead>
          <tbody>${rows || '<tr><td colspan="5">원료가 없습니다.</td></tr>'}</tbody>
        </table>
      `;
    }

    function rareHighlightClass(item) {
      return state.selectedFrequencyBuckets.has(item.frequency_bucket) ? "rare-highlight" : "";
    }

    function joinClasses(...classes) {
      return classes.filter(Boolean).join(" ");
    }

    function renderComparison(data) {
      const wrap = $("resultBody");
      state.lastComparison = data;
      const prediction = data.prediction;
      const actual = data.actual_recipe;
      const hitCodes = new Set(data.comparison.hit_codes);
      wrap.innerHTML = `
        <div class="metrics">
          <div class="metric"><span>모델</span><strong>${escapeHtml(prediction.model)}</strong></div>
          <div class="metric"><span>예측 상 개수</span><strong>${prediction.predicted_phase_count}</strong></div>
          <div class="metric"><span>예측 원료 수</span><strong>${prediction.predicted_count}</strong></div>
        </div>
        <div class="result-columns">
          <div>
            <h3 class="result-title">예측 레시피</h3>
            ${renderRecipeTable(
              prediction.ingredients,
              "median_amount",
              (item) => joinClasses(
                hitCodes.has(item.code) ? "predicted-hit" : "predicted-extra",
                rareHighlightClass(item)
              )
            )}
          </div>
          <div>
            <h3 class="result-title">실제 레시피</h3>
            ${renderRecipeTable(
              actual.ingredients,
              "amount",
              (item) => joinClasses(
                hitCodes.has(item.code) ? "actual-hit" : "actual-miss",
                rareHighlightClass(item)
              )
            )}
          </div>
        </div>
      `;
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    async function predict() {
      $("predictButton").disabled = true;
      $("status").textContent = "predicting";
      try {
        const response = await fetch("/api/compare", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ sample: $("sample").value, bulk: collectBulk() }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "prediction failed");
        renderComparison(data);
        $("status").textContent = `${state.model} · ${state.samples.length} samples`;
      } catch (error) {
        $("resultBody").innerHTML = `<div class="error">${escapeHtml(error.message)}</div>`;
        $("status").textContent = "error";
      } finally {
        $("predictButton").disabled = false;
      }
    }

    async function init() {
      const data = await fetch("/api/options").then((response) => response.json());
      state.fields = data.fields;
      state.samples = data.samples;
      state.frequency_buckets = data.frequency_buckets;
      state.model = data.defaults.model;
      renderFields();
      renderSamples();
      renderFrequencyBuckets();
      loadSampleFields();
      $("status").textContent = `${state.model} · ${state.samples.length} samples`;
    }

    $("sample").onchange = loadSampleFields;
    $("predictButton").onclick = predict;
    init();
  </script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
