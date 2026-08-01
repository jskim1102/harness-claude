# reciepe-rec

메이크업 bulk 조건으로 기존 처방 원료 종류를 예측하는 실험용 predictor/evaluator.

## 기본 예측 모델

CLI와 웹 서버의 기본 모델은 누수 통제 교차검증에서
`712/1,010 = 70.50%`를 기록한
`catboost-candidate-selector-v1`이다.

- 기존 샘플 예측: 해당 샘플이 학습에서 제외된 5-fold OOF 모델 사용
- 새 bulk 입력: 전체 1,010건으로 학습한 최종 모델 사용
- 평가 원료: recipe 기준 21회 이상 등장한 235개 원료코드
- 모델 학습: 프로세스 안에서 최초 요청 시 지연 실행하고 이후 메모리에서 재사용

전체 교차검증 재현:

```bash
PYTHONPATH=src python -m reciepe_rec.cli \
  --data-dir data --model catboost ml-evaluate
```

기존 통계 모델을 사용하려면 CLI나 웹 명령에
`--model statistical`을 추가한다.

## 왜 다시 만들었나

이전 구현은 후보표를 만들었지만, 실제 RCP와 비교했을 때 원료 overlap이 낮았다. 새 구조는 웹 UI보다 먼저 leave-one-out 평가기를 만들고, 실제 기존 데이터를 숨긴 뒤 예측 원료 set과 실제 원료 set을 비교한다.

## 현재 목표

기본 목표는 전체 holdout 평균 기준:

- 상 개수 오차율 평균 <= 10%
- 원료 종류 오차율 평균 <= 30%

오차율 정의:

- 상 개수 오차율 = `abs(actual_phase_count - predicted_phase_count) / actual_phase_count`
- 원료 종류 오차율 = `count(actual_ingredient_codes △ predicted_ingredient_codes) / actual_ingredient_count`

## 기존 통계 알고리즘

1. 평가 시 target RCP의 recipe line은 예측 후보에서 제외한다.
2. target bulk와 유사한 기존 RCP Top-K를 찾는다.
3. 같은 `소그룹`, `제형`, `중그룹`, `기능성`, `벌크유형`, `방부력`, 숙성 기준, `pH`, `Leave-on/Rinse-off`, `가스충진`만 사용한다.
4. `RCP_ID`, `제품명`, `등록일`, target recipe의 실제 원료/상 정보는 예측 입력으로 쓰지 않는다.
5. full allowed key에서 시작해 `segment_plus -> segment -> subform -> midform -> form` 순서로 prediction pool을 찾는다.
6. 원료는 pool 안에서 `1 / recipe_ingredient_count`로 가중한 weighted presence가 threshold를 넘는 코드만 예측한다.
   기본 threshold는 0.70이고, 희귀 원료 포기 모드의 권장 threshold는 0.58이다.
7. 예측 원료 set이 non-target 기존 단일 recipe set과 완전히 같으면 추가 후보를 더 붙여 verbatim clone을 피한다.
8. 상 개수는 target recipe 상 정보를 보지 않고 prediction pool의 median 상 개수로 예측한다.
9. 희귀 원료 포기 모드에서는 학습 recipe 기준 등장 빈도가 낮은 원료를 예측/채점 대상에서 제외한다.
   이 모드는 전체 원료 성능이 아니라 `지원 원료` 성능으로 따로 해석한다.

## 실행

웹 UI:

```bash
PYTHONPATH=src python -m reciepe_rec.webapp \
  --data-dir data --host 127.0.0.1 --port 8765 --model catboost
```

웹 UI는 샘플 선택 드롭다운에만 `RCP_ID|제품명`을 표시한다. 예측용 `BulkRecord`에는 `제품명`을 저장하지 않고, 원본 `RCP_ID`도 bulk/recipe join용 내부 key로만 쓴 뒤 랜덤 익명 sample id로 치환한다. `등록일`은 로드하지 않는다.

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data evaluate --sample-size 250 --seed 7
```

전체 1,012개 holdout:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data evaluate --sample-size 2000 --seed 7
```

예측 원료 수를 25개로 고정해서 평가:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data evaluate --sample-size 2000 --seed 7 --max-ingredients 25
```

특정 기존 RCP를 숨기고 예측:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data predict-existing 3HKCRDC00100
```

특정 기존 RCP를 숨기고 실제 원료와 비교:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data compare-existing 3HKCRDC00100
```

전체 데이터에서 개수/종류 10% 편차 기준으로 엄격 평가:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data strict-evaluate --tolerance 0.10
```

사용자 정의 기준으로 평가:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data user-metrics
```

희귀 원료를 포기하고 지원 원료만 평가:

```bash
PYTHONPATH=src python -m reciepe_rec.cli --data-dir data user-metrics --pool-threshold 0.58 --min-ingredient-frequency 60 --ingredient-type-error-target 0.20
```

## 최근 검증 결과

전체 1,012개 leave-one-out holdout:

```text
RCP_ID count: 1,012
target_passed: true

phase error rate avg/median: 5.892818% / 0.000000%
phase target: <= 10%

ingredient type error rate avg/median: 29.872881% / 9.090909%
ingredient target: <= 30%

exact non-target known recipe set predictions: 0 / 1,012
target RCP in similar recipes: 0 / 1,012
```

금지 필드를 더 엄격하게 배제한 평가:

- `제품명`: 웹 샘플 label 표시용으로만 읽고 예측용 `BulkRecord`에는 저장하지 않음
- `등록일`: 로드하지 않음
- `RCP_ID`: bulk/recipe join과 웹 샘플 label 표시용으로만 쓰고 예측용 key는 랜덤 익명 id로 치환
- target recipe line: target별 predictor 생성 전 제거, 예측 후 채점에만 사용

희귀 원료 포기 모드(`pool_threshold=0.58`, `min_ingredient_frequency=60`)의 엄격 평가:

```text
sample_size: 1,010
phase error rate avg/median/p90: 5.904487% / 0.000000% / 20.000000%

supported ingredient type error rate avg/median/p75/p90:
19.349593% / 0.000000% / 25.986842% / 68.750000%

supported ingredient <=20% pass rate: 73.762376%
ingredient support coverage: 64.668805%
ignored actual ingredient count: 9,585 / 27,129

raw all-ingredient error with supported-only predictions: 46.313412%
exact training recipe set predictions: 0
```

즉 `19.35%`는 전체 원료 기준이 아니라, 등장 빈도 60회 이상인 지원 원료만 예측/채점한 값이다.
전체 원료를 그대로 채점하면 희귀 원료를 포기한 만큼 raw 오차율은 커진다.

참고: CLI에는 사용자가 처음 정의한 raw difference 지표도 함께 남겨 두었다. 그 값은 퍼센트가 아니라 `평균 차이 개수 * 100`이라 오차율 퍼센트와 다르다.

## 남은 약점

색소베이스, 일부 특수 파우더, 특수 컨실러/립 복합 제품은 아직 낮다. 이 케이스는 색상/톤/중간 베이스 정보가 bulk 데이터에 부족하거나, 실제로 유사 처방이 거의 없다.
