# 모델 구조·학습·검증 설명

작성 기준일: 2026-07-28

## 1. 먼저 구분해야 할 두 모델

이 프로젝트에는 현재 서로 다른 상태의 모델이 있다.

| 구분 | 현재 상태 | 역할 |
|---|---|---|
| `RecipePredictor` | `--model statistical`로 계속 사용 가능 | 계층형 pool과 원료 출현 통계를 사용하는 기존 predictor |
| CatBoost 후보 선택기 | CLI·Web 기본 모델로 통합됨 | 허용 입력으로 만든 여러 원료 후보 중 통과 가능성이 가장 높은 후보를 선택 |

이 문서에서 `기존 통계 predictor`는
`src/reciepe_rec/predictor.py`의 `RecipePredictor`를 뜻한다.
`CatBoost 모델` 또는 `현재 연구 최고 모델`은 누수 통제 평가에서
`712/1,010`을 기록한 CatBoost 후보 선택기를 뜻한다.

두 모델의 평가 지표도 다르므로 수치를 섞어서 해석하면 안 된다.

## 2. 예측 입력과 금지 입력

예측에 사용하는 bulk 입력은 다음 19개다.

1. 벌크유형
2. 기능성_벌크품목정보등록 선택
3. 기능성_유기 / 무기 / 유무기 선택
4. 방부력
5. 안정도
6. 제품유형_대그룹
7. 제품유형_중그룹
8. 제품유형_소그룹
9. 제품유형_제형타입
10. 숙성기준_점도
11. 숙성기준_Spindle #
12. 숙성기준_rpm
13. 숙성기준_절단경도
14. 숙성기준_침입경도(kg)
15. 숙성기준_융점
16. pH
17. Leave-on
18. Rinse-off
19. 가스충진

다음 값은 예측 입력으로 사용하지 않는다.

- 등록일자
- 원본 `RCP_ID`
- 제품명
- 예측 대상 recipe의 실제 원료, 함량, 상 정보

`RCP_ID`는 원본 Excel의 bulk와 recipe를 연결할 때만 사용한다.
익명 평가에서는 `A00000` 형태의 무작위 ID로 바뀌며 모델 특징에는 들어가지 않는다.
제품명은 웹 화면의 샘플 표시용일 뿐 `BulkRecord`에 저장되지 않는다.
등록일자는 로드하지 않는다.

안정도처럼 전부 비어 있거나 제품유형_대그룹처럼 값이 하나뿐인 컬럼은
형식상 입력에는 존재하지만 현재 데이터에서는 구분력을 거의 제공하지 않는다.

## 3. 기존 통계 predictor

### 3.1 학습 방식

기존 통계 predictor는 신경망이나 gradient boosting처럼 파라미터를 반복 최적화하는
모델이 아니다. 데이터 로드 시 다음 통계를 구축하는 결정론적 모델이다.

- RCP별 실제 원료 set
- 원료별 대표 이름과 대표 상
- 제품 segment별 원료 출현 횟수
- 중그룹·제형별 원료 출현 횟수
- 전체 원료 출현 횟수
- bulk 조건 단계별 RCP 색인

따라서 여기서 `학습`은 계수를 fitting하는 작업보다
기존 recipe를 색인하고 원료 출현 통계를 계산하는 작업에 가깝다.

### 3.2 예측 pool 선택

새 bulk와 일치하는 과거 recipe를 다음 순서로 찾는다.

1. `full`
2. `segment_plus`
3. `segment`
4. `subform`
5. `midform`
6. `form`
7. 위 단계가 모두 비면 전체 recipe

가장 먼저 한 건 이상 발견되는 단계가 prediction pool이 된다.
`full`은 벌크유형, 기능성, 방부력, 제품 중·소그룹, 제형, 숙성 기준,
pH, Leave-on/Rinse-off, 가스충진을 함께 비교한다.
뒤 단계로 갈수록 일부 조건을 완화한다.

### 3.3 원료 선택

pool의 각 recipe에는 다음 가중치를 준다.

```text
recipe_weight = 1 / 해당 recipe의 원료 종류 수
```

각 원료의 가중 출현율을 계산한 뒤 기본값 `0.70`을 초과하는 원료를 예측한다.
이 방식은 원료가 많은 recipe 하나가 모든 원료의 출현율을 과도하게 끌어올리는 것을
완화한다.

예측 set이 기존 non-target recipe set과 완전히 같으면 주변 recipe와 segment에서
근거가 있는 원료를 하나 이상 보강해 단순 복제를 피한다.
예측 상 개수는 target의 실제 상 정보를 보지 않고 pool의 상 개수 중앙값으로 정한다.

### 3.4 운영 predictor의 평가

README에 기록된 전체 `1,012`건 leave-one-out 결과는 다음 지표를 사용한다.

- 평균 상 개수 오차율
- 평균 원료 종류 대칭차 오차율
- precision, recall, F1, amount recall

이 평가는 아래 연구 모델의 `712/1,010` 통과율과 지표가 다르다.
따라서 README의 `29.87%` 평균 원료 오차와 연구 모델의 `70.50%` 통과율은
서로 직접 비교할 수 없다.

## 4. 현재 연구 최고 모델

### 4.1 문제 정의

전체 recipe에서 21회 이상 등장한 원료코드만 평가 대상으로 삼는다.

```text
평가 recipe 수: 1,010
평가 원료코드 수: 235
```

한 recipe에 대한 예측 set을 `P`, 실제 지원 원료 set을 `A`라 할 때:

```text
red_rate    = |A - P| / |A|
yellow_rate = |P - A| / |P|
통과        = red_rate < 0.10 and yellow_rate < 0.10
```

경계값이 정확히 `10%`인 경우도 통과가 아니다.

### 4.2 후보 생성

각 target의 실제 recipe는 context에서 제외한다.
운영 predictor와 같은 계층형 pool에서 다음 후보들을 만든다.

- pool에서 실제 관측된 원료 set
- 원료 단순 출현율 threshold 후보
- `1 / recipe 원료 수`로 가중한 출현율 threshold 후보

threshold는 `0.10`부터 `0.95`까지 `0.025` 간격으로 적용한다.

각 후보에는 다음과 같은 특징을 계산한다.

- 19개 bulk 입력
- 선택된 pool 단계와 pool 크기
- 후보 원료 수
- 동일 set의 관측 횟수와 비율
- pool recipe들에 대한 통과율
- 평균 누락 원료 수와 평균 추가 원료 수
- red/yellow 비율의 평균과 최댓값
- 후보 원료들의 평균·최소·최대 support
- 동일 후보를 제공한 source recipe와 target의 최대 유사도
- 후보 원료 set signature

학습 label은 해당 후보가 target 실제 set에 대해 위의 엄격 통과 조건을 만족하면
`1`, 아니면 `0`이다.

### 4.3 CatBoost 설정

현재 연구 최고 설정은 다음과 같다.

```text
model: CatBoostClassifier
catboost version: 1.2.8
loss: Logloss
depth: 8
iterations: 400
learning_rate: 0.03
l2_leaf_reg: 10
random seed base: 20260724
categorical:
  - 19개 bulk 입력
  - chosen_level
  - set_signature
empirical score blend: 사용하지 않음(model_weight=1.00)
```

target별 모든 후보의 통과 확률을 예측하고 가장 높은 후보 하나를 고른다.
확률이 같으면 더 짧은 후보를 우선하고, 그 뒤에는 정렬된 set signature로
결정론적으로 선택한다.

## 5. 학습과 검증 절차

### 5.1 5-fold target crossfit

`1,010`개 recipe를 고정 seed로 5개 fold로 나눈다.
각 fold에서 약 `808`개는 scorer 학습에, 약 `202`개는 검증에 사용한다.

중요한 분리 규칙은 다음과 같다.

1. 검증 fold의 recipe label은 CatBoost 학습에 사용하지 않는다.
2. 학습 후보의 pool과 집계 특징을 만들 때도 검증 fold 전체를 제외한다.
3. 학습 recipe 자신의 후보 특징을 만들 때는 그 recipe 자체를 제외한다.
4. 검증 target의 후보를 만들 때는 target 자신의 recipe만 제외한다.
5. 다섯 fold에서 자신이 검증 대상이었을 때의 예측만 합쳐 최종 점수를 계산한다.

검증 target 후보가 다른 검증 recipe의 label을 사용할 수 있는 이유는
현재 평가가 `각 target 하나만 숨기는 leave-one-target-out` benchmark이기 때문이다.
대신 CatBoost를 학습시키는 행과 집계 문맥에서는 검증 fold 전체를 제거해,
검증 target label이 scorer 학습 특징으로 돌아오는 경로를 차단했다.

이 방식은 일반적인 랜덤 train/test 평가와 완전히 같지는 않다.
새로운 미래 batch를 한꺼번에 예측하는 운영 환경이라면
과거 데이터만 사용한 별도 time holdout이 필요하다.

### 5.2 검증 결과

현재 연구 최고 결과:

```text
passed: 712 / 1,010
pass rate: 70.4950495%
candidate oracle: 832 / 1,010
tested-model selector oracle: 743 / 1,010
```

`candidate oracle`은 후보 중 정답 통과 후보가 하나라도 있었던 target 수다.
실제 모델 성능이 아니라 후보 생성기의 상한 진단값이다.

`selector oracle`도 실서비스 성능이 아니다.
시험한 여러 selector 중 target마다 사후적으로 정답인 모델을 고른 값이므로
도달 가능한 다양성을 보는 진단값일 뿐이다.

## 6. 단순 학습 과적합으로 보기 어려운 이유

`70.50%`는 학습 데이터에 대한 재채점 결과가 아니다.
각 recipe의 점수는 그 recipe가 CatBoost 학습에서 빠진 fold의 예측으로만 계산했다.

구체적인 근거는 다음과 같다.

- target의 실제 원료는 후보 생성과 scorer 학습에서 자기 자신에 대해 제외된다.
- 검증 fold의 label은 CatBoost fitting에 들어가지 않는다.
- 검증 fold는 학습 후보의 pool 통계에서도 제외된다.
- 제품명, 등록일, 원본 ID 같은 암기 가능한 식별 입력을 사용하지 않는다.
- 예측을 만든 뒤에만 숨겨둔 target 실제 원료와 비교한다.
- 높은 수치가 나와도 영향 제거 감사를 통과하지 못하면 최종 결과에서 폐기했다.

특히 한 실험에서는 중간 prefix가 약 `78~79%`, 전체가
`758/1,010 = 75.05%`까지 나왔다. 그러나 다른 학습행의 1단계 특징에
outer target이 간접 영향을 줄 수 있다는 사실이 확인됐다.
영향받은 직접 동료 행을 제거한 첫 100건 감사에서 성능이
`77/100`에서 `69/100`으로 떨어졌기 때문에 이 결과는 폐기했다.

즉 현재의 `70.50%`는 더 높은 수치를 유지하기 위해 검증 규칙을 완화한 값이 아니라,
누수 의심 결과를 제거한 뒤 남은 crossfit 결과다.

## 7. 그래도 과적합이 전혀 없다고 단정할 수 없는 이유

crossfit은 과적합 위험을 줄이지만 완전히 없애지는 않는다.

- 같은 `1,010`건으로 여러 모델과 hyperparameter를 비교했다.
- 최종 설정 선택 자체에 대한 완전한 nested 검증은 하지 않았다.
- 무작위 fold이므로 시간에 따른 recipe 분포 변화는 검증하지 못했다.
- 완전히 새로운 외부 데이터셋을 잠금 holdout으로 평가하지 않았다.
- 현재 benchmark는 target 하나만 숨기는 LOO 환경이며 실제 신규 데이터 환경과
  학습 정보량이 다를 수 있다.

따라서 `70.50%`는 현재 가장 누수 통제가 잘 된 내부 검증치이지,
미래 실서비스 정확도의 보증값은 아니다.

과적합 여부를 최종 확인하려면 다음 절차가 필요하다.

1. 현재 입력, 후보 생성법, CatBoost 설정을 변경 불가능하게 고정한다.
2. 지금까지 모델 선택에 한 번도 사용하지 않은 새 recipe를 확보한다.
3. 가능하면 등록 시점 이후 데이터로 time holdout을 만든다.
4. holdout 결과를 확인하기 전에 threshold와 성공 기준을 고정한다.
5. 단 한 번 평가하고, 결과를 본 뒤 같은 holdout으로 재튜닝하지 않는다.

## 8. 채택하지 않은 결과

다음 결과는 현재 공식 성능으로 사용하지 않는다.

| 결과 | 수치 | 제외 이유 |
|---|---:|---|
| near-exact meta LOO | 758/1,010 (75.05%) | 다른 학습행 특징을 통한 target 간접 영향 |
| influence-recomputed LOO | 724/1,010 (71.68%) | broad pool과 사전 계산 vote 영향이 완전히 제거되지 않음 |
| OOB tree diagnostic | 718/1,010 (71.09%) | decoder와 모델 설정 선택이 완전한 nested 검증이 아님 |
| strict retrieval ranker | 646/1,010 (63.96%) | 엄격하지만 현재 최고보다 낮음 |
| strict enhanced tree | 706/1,010 (69.90%) | 엄격하지만 현재 최고보다 낮음 |

현재 공식 연구 기준선은 `712/1,010 = 70.50%`다.
`75%`를 검증 완료 성능으로 기록해서는 안 된다.

## 9. 운영 반영 상태

2026-07-28 기준 CatBoost 후보 선택기는 다음 경로에 반영됐다.

- 구현: `src/reciepe_rec/ml_predictor.py`
- CLI 기본값: `--model catboost`
- 웹 서버 기본값: `--model catboost`
- 기존 통계 predictor fallback: `--model statistical`
- 재현 명령: `python -m reciepe_rec.cli --model catboost ml-evaluate`

알려진 기존 샘플을 예측할 때는 그 샘플이 속한 validation fold 전체를
학습에서 제외한 OOF CatBoost를 사용한다. 따라서 웹의 기존 샘플 비교 화면에서
target label을 학습한 full model로 다시 맞히는 누수를 만들지 않는다.

사용자가 기존 샘플과 무관한 새 bulk를 입력할 때는 전체 데이터로 학습한
production scorer를 사용한다. 이 full model은 이용 가능한 모든 과거 데이터를
사용하기 위한 배포 모델이며, `70.50%`라는 수치는 이 full model의 학습 점수가
아니라 동일 코드의 5-fold OOF 검증 결과다.

모델은 프로세스 시작 시 모두 학습하지 않는다.

- 첫 기존 샘플 요청: 해당 OOF fold 모델 하나를 학습
- 다른 fold의 첫 요청: 그 fold 모델을 추가 학습
- 첫 신규 bulk 요청: 전체 데이터 모델을 학습
- 이후 요청: 프로세스 메모리에 있는 모델을 재사용

웹 응답과 `/api/health`에는 실제 모델 이름과 현재 학습된 fold 상태가 포함된다.
웹 화면 상단과 결과 패널에도 `catboost-candidate-selector-v1`을 표시한다.

현재 남은 운영 한계는 다음과 같다.

- 모델 파일을 영구 저장하지 않아 프로세스를 재시작하면 지연 학습을 다시 한다.
- 여러 웹 worker는 각자 모델을 학습하고 메모리에 보관한다.
- 현재 데이터가 바뀌면 같은 설정으로 자동 재학습되지만, 새 데이터에 대한
  잠금 holdout 검증은 별도로 수행해야 한다.
- 재현성을 위해 CatBoost 1.2.8, NumPy 1.26.4, pandas 2.2.2,
  scikit-learn 1.5.1을 고정했다.
