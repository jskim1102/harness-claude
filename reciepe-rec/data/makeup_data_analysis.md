# Makeup Data Analysis

분석 대상:

- `bulk_makeup.xlsx`: 메이크업 제품 마스터, 데이터 1,012행, 고유 `RCP_ID` 1,010개
- `reciepe_makeup.xlsx`: 메이크업 처방 원료 라인, 데이터 27,796행, 고유 `RCP_ID` 1,010개

목표:

- `상`, `원료`, `함량`을 각각 분석해서 추천/예측 시스템을 어떤 구조로 만들어야 하는지 정리한다.
- 결론부터 말하면, 이 데이터는 `bulk -> recipe 전체 생성`보다 `상 template 추천 -> 상별 원료 후보 추천 -> 함량 범위 추천 -> 100% 보정` 구조가 적합하다.

## 1. 상 분석

### 1.1 상의 의미

`상`은 원료 자체의 고정 속성이 아니라, 한 처방 안에서 원료를 묶는 제조/배합 단계 또는 투입 그룹으로 보는 것이 맞다.

예를 들어 같은 `정제수`, `TW-HD`, `1,3-Butylene Glycol`도 제품군과 제형에 따라 여러 상에 등장한다. 따라서 `이 원료는 항상 C상` 같은 규칙으로 예측하면 안 된다.

### 1.2 전체 상 분포

정규화 전에는 전각 문자가 섞여 있다.

```text
raw 상 예:
A, B, C, D, E, F, G, H, I, J, K, L, M, N, O
Ａ, Ｂ, Ｃ, Ｄ, Ｅ
```

정규화 후 주요 line 수:

```text
A: 8,564
D: 3,559
E: 3,240
F: 2,690
C: 2,668
B: 2,274
G: 1,700
I: 1,051
H: 1,039
J: 652
K: 178
L: 114
M: 57
N: 7
O: 3
```

레시피 기준으로는:

```text
A상 존재: 1,010 / 1,010
B상 존재: 1,008 / 1,010
C상 존재: 1,001 / 1,010
D상 존재: 995 / 1,010
E상 존재: 937 / 1,010
F상 존재: 790 / 1,010
G상 존재: 635 / 1,010
```

### 1.3 상 template 구조

대부분의 레시피는 `A`부터 마지막 상까지 연속된 구조다.

```text
연속 template: 1,005 / 1,010
중간 상이 빠진 예외: 5 / 1,010
```

상위 template:

```text
A+B+C+D+E+F+G+H+I: 178
A+B+C+D+E+F: 155
A+B+C+D+E: 150
A+B+C+D+E+F+G+H+I+J: 147
A+B+C+D+E+F+G: 113
A+B+C+D+E+F+G+H: 79
A+B+C+D+E+F+G+H+I+J+K: 70
A+B+C+D: 55
```

상 개수 분포:

```text
9상: 178
6상: 155
5상: 150
10상: 147
7상: 113
8상: 84
11상: 70
4상: 55
```

### 1.4 세그먼트별 상 구조

상 구조는 `제품유형_소그룹 + 제형타입`에 강하게 묶인다.

대표 예:

```text
립스틱 + 고형스틱 유분산
- A+B+C+D+E+F: 76.2%
- A+B+C+D+E+F+G: 23.8%

블러셔 + 고형밤 유분산
- A+B+C+D+E+F: 90.0%

립틴트 + 유분산
- A+B+C+D+E: 100.0%

컨실러/코렉터 + 고형밤 유분산
- A+B+C+D+E: 51.2%
- A+B+C+D+E+F: 29.7%
- A+B+C+D: 14.0%

컨실러/코렉터 + W/Si
- A+B+C+D+E+F+G+H+I: 46.5%
- A+B+C+D+E+F+G+H+I+J: 18.2%
- A+B+C+D+E+F+G+H: 12.6%

파운데이션-쿠션 + W/Si
- A+B+C+D+E+F+G+H+I+J: 30.7%
- A+B+C+D+E+F+G+H+I: 29.2%
- A+B+C+D+E+F+G: 12.4%
```

### 1.5 상 template 추천 가능성

간단한 leave-one-out 기준:

```text
sub 기준
Top1: 30.1%
Top3: 72.2%
Top5: 88.2%

sub + form 기준
Top1: 44.6%
Top3: 82.5%
Top5: 94.3%

sub + form + functional 기준
Top1: 44.7%
Top3: 84.3%
Top5: 93.2%

sub + form + functional + bulk_type 기준
Top1: 49.8%
Top3: 85.2%
Top5: 93.7%
```

단일 정답 예측보다는 Top3 template 추천이 현실적이다.

### 1.6 상별 역할 예시

#### 컨실러/코렉터 + 고형밤 유분산

```text
A상: 오일/왁스 베이스, median 36.7%
B상: 에스터/오일, median 27.0%
C상: 안료/색소, median 26.37%
D상: 파우더/필러, median 12.5%
E상 이후: 향, 추출물, 컨셉 원료, 극소량
```

#### 컨실러/코렉터 + W/Si

```text
A상: 실리콘/유화/분산 베이스
B상: 점증/겔 또는 휘발성 실리콘
C/D상: 안료 + 실리콘 분산
E/F/G상: 수상, 보습제, 염, 방부
H/I/J 이후: 컨셉 원료, 향, 극소량
```

#### 파운데이션/쿠션 + W/Si

```text
A상: 오일, 실리콘, 자외선차단제, 유화제
B상: 점증제/겔
C상: 실리콘/휘발성 용매
D상: TiO2, 산화철, ZnO 등 안료/분체
E/F상: 정제수, Niacinamide, Adenosine, 보습제
G 이후: 필름포머, 향, 컨셉 원료
```

#### 립스틱 + 고형스틱 유분산

```text
A/B상: 오일, 왁스, 고형화 베이스
C상: 실리콘/파우더 보조
D/E상: 색소 베이스
F/G상: 향, 추출물, 극소량 컨셉 원료
```

#### 파우더-프레스드 + 압축파우더

```text
A/B상: 주 분체/필러
C/D상: 바인더 오일, 실리콘, 에스터
E/F상: 방부, 향, 컨셉 원료
```

### 1.7 상 예측 시사점

`상`은 다음 순서로 추천하는 것이 좋다.

```text
1. 제품유형_소그룹 + 제형타입 + 기능성 + 벌크유형으로 유사 세그먼트를 찾는다.
2. 해당 세그먼트의 상 template Top3를 추천한다.
3. template별 상 총량 budget을 추천한다.
4. 각 상 안에서 원료 후보와 함량 범위를 추천한다.
```

## 2. 원료 분석

### 2.1 전체 원료 분포

```text
고유 원료코드: 1,189
고유 원료명: 1,185
레시피 line: 27,796
레시피당 원료 수 평균: 27.52
레시피당 원료 수 중앙값: 27
최소 line 수: 2
최대 line 수: 73
```

### 2.2 롱테일 분포

원료는 롱테일이 매우 강하다.

```text
1개 레시피에만 등장: 234개
2~5개 레시피 등장: 417개
6~20개 레시피 등장: 303개
21~100개 레시피 등장: 171개
101~300개 레시피 등장: 50개
300개 초과 등장: 14개
```

즉 전체 원료의 약 54.8%가 5개 이하 레시피에만 등장한다. 이것이 원료 예측이 어려운 핵심 원인이다.

다만 빈도만으로 롱테일 원료를 제거하면 위험하다. `1개 레시피 등장 원료`와 `2~5개 레시피 등장 원료`는 전체 line과 전체 함량에서 차지하는 비중은 작지만, 일부 원료는 단일 레시피에서 큰 함량을 차지한다.

함량 기준으로 보면, 롱테일은 두 종류로 나뉜다.

| 구분 | 전체 원료 | 버려도 될 가능성이 큰 원료 | 따로 살려야 할 고함량 원료 |
|---|---:|---:|---:|
| 1회 등장 | 234개 | 181개는 최대 1% 이하 | 19개는 최대 5% 초과 |
| 2~5회 등장 | 417개 | 297개는 최대 1% 이하 | 47개는 최대 5% 초과 |

해석:

- `1~5회 등장 원료` 651개 중 478개는 한 레시피 안에서도 최대 1% 이하라서, 모델 예측 대상에서 제외해도 큰 문제가 적다.
- 반대로 66개는 등장 빈도는 낮지만 한 레시피에서 5%를 넘는다. 이들은 희귀하지만 처방 구조를 바꾸는 원료라서 그냥 버리면 안 된다.
- 실제로 `1~5회 등장 원료`의 전체 함량 손실 중 약 73%가 이 66개 고함량 희귀 원료에서 나온다.

따라서 롱테일은 일괄 제거가 아니라 `rare_trace`와 `rare_structural`로 나눠야 한다.

### 2.3 상위 원료 커버리지

자주 쓰이는 원료 Top-N은 전체 구조를 파악하는 참고 지표로 유용하다.

| 후보군 | line 커버리지 | 함량 커버리지 | 해석 |
|---|---:|---:|---|
| Top 50 | 49.2% | 63.2% | 핵심 베이스 원료 위주 |
| Top 100 | 65.6% | 75.8% | 기본 처방 골격 |
| Top 300 | 86.9% | 93.2% | 대부분의 반복 원료 포함 |
| Top 500 | 94.0% | 97.0% | 대부분 덮지만 희귀 고함량 예외는 남음 |

상위 원료는 line 기준보다 함량 기준에서 더 강하다. 즉 메이크업 처방의 큰 골격은 소수의 반복 원료가 만든다.

하지만 Top 500이 line의 94.0%, 함량의 97.0%를 덮어도, 나머지 3.0% 안에 `rare_structural` 원료가 있다. 이들은 전체 비중은 작지만 특정 레시피에서는 5~60%를 차지할 수 있으므로, 단순히 Top-N 밖 원료를 전부 버리면 일부 처방이 크게 깨진다.

따라서 Top-N만으로 후보군을 정하기보다, 등장 빈도와 함량 위험도를 결합한 정책이 더 적합하다.

### 2.4 rare_structural 분석

`rare_structural`은 다음 조건으로 정의했다.

```text
등장 레시피 수 <= 5
그리고
원료별 max 함량 > 5%
```

요약:

| 항목 | 값 |
|---|---:|
| 원료코드 | 66개 |
| recipe line | 167개 |
| 영향 recipe | 124개 |
| 전체 함량 비중 | 2.016% |
| 1회 등장 원료 | 19개 |
| 2~5회 등장 원료 | 47개 |

이 원료들은 전체 기준으로는 작아 보이지만, 등장하는 recipe 안에서는 영향이 크다.

| 기준 | 값 |
|---|---:|
| 발생 1회당 함량 중앙값 | 7.66% |
| 발생 1회당 p95 | 38.7% |
| 발생 1회당 최대값 | 60.0% |
| 영향 recipe 내 rare_structural 함량 중앙값 | 11.75% |
| rare_structural 함량이 10% 초과인 recipe | 70개 |
| rare_structural 함량이 20% 초과인 recipe | 33개 |
| rare_structural 함량이 40% 초과인 recipe | 8개 |

즉 `rare_structural`은 전체 평균으로 보면 2.016%뿐이지만, 해당 recipe에서는 처방 골격을 바꾸는 원료다.

제품군별로 보면 `base/complexion`과 `lip` 계열에 가장 많이 몰려 있다.

| 제품군 | 함량 합 | 비중 | 영향 recipe | 원료코드 |
|---|---:|---:|---:|---:|
| base/complexion | 652.4 | 32.0% | 33 | 16 |
| lip | 530.1 | 26.0% | 36 | 18 |
| eyeliner | 168.0 | 8.3% | 3 | 4 |
| cheek/highlighter | 167.6 | 8.2% | 11 | 10 |
| powder | 116.1 | 5.7% | 8 | 7 |
| color base intermediate | 110.0 | 5.4% | 2 | 1 |
| concealer | 77.4 | 3.8% | 15 | 11 |

원료명 패턴 기준으로 보면 다음과 같다. recipe의 `기능` 컬럼은 비어 있어서, 이 분류는 원료명 기반의 보조 분류다.

| 타입 | 함량 합 | 비중 | 해석 |
|---|---:|---:|---|
| named specialty/unknown | 698.7 | 34.3% | 상품명 기반 특수 원료, 별도 매핑 필요 |
| water/extract replacement | 446.9 | 21.9% | 빙하수, 잎수, 콜라겐, 발효수 등 수상 대체 원료 |
| silicone/gel/powder | 319.5 | 15.7% | 실리콘 젤, 엘라스토머, 특수 파우더 |
| base/intermediate | 267.4 | 13.1% | 3JU 계열, 색소/중간 베이스 |
| pigment/pearl/powder | 230.3 | 11.3% | 안료, 펄, 파우더 |
| oil/wax/ester | 48.0 | 2.4% | 오일/왁스/에스터 |
| uv/filter | 25.3 | 1.2% | 자외선 차단 관련 원료 |

세그먼트 위험도는 균일하지 않다.

| 세그먼트 | 전체 recipe | 영향 recipe | rare_structural 함량 합 | 해석 |
|---|---:|---:|---:|---|
| 파운데이션-쿠션 + W/Si | 137 | 8 | 226.1 | 전체에서는 드물지만, 특정 제품에서 수상 대체 원료가 크게 들어감 |
| 파운데이션-쿠션 + W/O | 59 | 13 | 208.8 | 영향 recipe 비율이 높아 예외 후보 필요 |
| 아이라이너 + 가용화 | 3 | 3 | 168.0 | rare_structural 제거 불가 |
| 립틴트 + 가용화 | 4 | 4 | 158.0 | rare_structural 제거 불가 |
| 립-복합 + 고형밤 유분산 | 4 | 4 | 129.0 | rare_structural 제거 불가 |
| 색소베이스 | 4 | 2 | 110.0 | 중간 원료로 별도 처리 필요 |
| 립밤 + 고형스틱 유분산 | 11 | 8 | 75.0 | 영향 recipe 비율이 높음 |

상 기준으로는 A/E/D/F/C/B상에 대부분 몰린다.

```text
A상: 651.7
E상: 489.3
D상: 306.0
F상: 241.4
C상: 166.2
B상: 161.4
```

따라서 `rare_structural`은 전역 모델이 직접 맞혀야 하는 일반 원료가 아니다. 추천 시스템에서는 다음처럼 다루는 것이 적합하다.

```text
core 후보군:
  6개 이상 recipe에 등장한 반복 원료

rare_structural 후보군:
  제품유형_소그룹 + 제형타입 + 상 조건에서만 열리는 예외 후보

rare_trace 후보군:
  모델 예측 대상에서 제외하거나 OTHER_TRACE로 묶음
```

특히 아이라이너, 립틴트 가용화, 립-복합, 색소베이스, 립밤 계열은 `rare_structural`을 제거하면 처방이 무너질 수 있다. 반면 컨실러/코렉터, 대형 파운데이션 세그먼트는 대부분 코어 원료로 설명되고 일부 제품에서만 예외 후보를 추가하면 된다.

### 2.5 후보군 정책 검증

원료 후보군 정책을 recipe line과 함량 기준으로 비교하면, `freq>=6 + rare_structural` 정책이 가장 안정적이다.

| 정책 | 후보 | line | 함량 | p95 누락 | >5% recipe | >10% recipe |
|---|---:|---:|---:|---:|---:|---:|
| Top300 + rare_structural | 366 | 87.54% | 95.19% | 25.65% | 260 | 145 |
| Top500 + rare_structural | 566 | 94.55% | 98.99% | 6.00% | 68 | 17 |
| freq>=6 + rare_structural | 604 | 95.37% | 99.26% | 4.96% | 46 | 11 |

결론:

- Top-N 방식은 원료 수를 깔끔하게 제한할 수 있지만, 빈도 500위 밖의 반복 원료와 세그먼트 특화 원료를 놓칠 수 있다.
- `freq>=6`은 5개 이하 등장 원료를 자연스럽게 롱테일로 분리하면서, 반복성이 있는 원료는 순위와 관계없이 보존한다.
- 여기에 `rare_structural` 66개를 예외 후보로 추가하면 함량 커버리지가 99.26%까지 올라간다.

따라서 MVP 원료 후보군은 다음 기준이 가장 적합하다.

```text
candidate_vocabulary =
  ingredients with recipe_frequency >= 6
  +
  rare_structural ingredients
```

이 정책에서도 남는 누락은 대부분 `max 5% 이하` 희귀 원료가 여러 개 모여서 생긴다.

대표 잔여 패턴:

- 보습스틱/고형스틱: 2~5% 오일, 왁스, 분체, 기능성 용액이 여러 개 빠지면서 20% 이상 누락될 수 있다.
- 글리터 아이섀도우/하이라이터: 펄, 글리터, 특수 파우더가 3~5%씩 여러 개 들어간다.
- 컨실러 고형스틱: 특정 오일, 실리콘, 왁스 대체 원료가 2~4% 단위로 빠진다.
- 베이스/프라이머/BB 계열 일부: 특수 기능성 원료, 펄, 컨셉 원료가 누락된다.

즉 `freq>=6 + rare_structural`은 기본 후보군으로 충분히 강하지만, 펄/글리터/스틱 계열에는 세그먼트별 후보 확장 규칙이 추가로 필요하다.

2차 후보 확장 규칙을 비교하면 다음과 같다.

| 정책 | 후보 | 함량 | p95 누락 | >5% recipe | >10% recipe |
|---|---:|---:|---:|---:|---:|
| freq>=6 + rare_structural | 604 | 99.26% | 4.96% | 46 | 11 |
| + rare max>3% | 640 | 99.59% | 3.01% | 14 | 0 |
| + segment-local rare | 668 | 99.71% | 1.47% | 10 | 3 |
| + rare max>3% + segment-local rare | 683 | 99.80% | 1.10% | 4 | 0 |

정의:

```text
rare max>3%:
  recipe_frequency <= 5
  그리고
  3% < max 함량 <= 5%

segment-local rare:
  전체 recipe_frequency <= 5
  그리고
  같은 세그먼트에서 2개 이상 recipe에 등장
  그리고
  세그먼트 내 max 함량 > 1% 또는 세그먼트 내 총 함량 >= 4%
```

해석:

- `rare max>3%`는 후보 36개만 추가하면서 10% 초과 누락 recipe를 0개로 줄인다.
- `segment-local rare`는 글리터, 펄, 스틱, 특정 제형 대체 원료처럼 전역 빈도는 낮지만 세그먼트 안에서는 반복되는 원료를 잡는다.
- 두 규칙을 함께 쓰면 후보는 604개에서 683개로 늘지만, 함량 커버리지는 99.80%까지 올라가고 p95 누락은 1.10%까지 낮아진다.

따라서 최종 후보군 정책은 2단계가 적합하다.

```text
기본 후보군:
  recipe_frequency >= 6
  또는
  rare_structural

세그먼트별 확장 후보군:
  rare max>3%
  또는
  segment-local rare
```

이렇게 하면 전역 모델은 과도한 롱테일을 직접 학습하지 않으면서도, 실제 처방이 깨지는 세그먼트는 후보군 확장으로 보호할 수 있다.

### 2.6 주요 공통 원료

레시피 등장 수 기준 상위 원료:

```text
정제수: 612개 recipe
Iron Oxide Red 3AS: 583개
Iron Oxide Yellow 3AS: 575개
TW-HD: 572개
TiO2 HK-50 AS: 567개
Iron Oxide Black 3AS: 539개
1, 3-Butylene Glycol: 531개
PUROLAN OD-C: 477개
Akoline MCM: 441개
ABIL EM 90: 367개
COSMOL 222: 344개
Adenosine: 340개
Sodium Chloride: 304개
PB1400F: 301개
```

메이크업 데이터답게 색소/안료, TiO2, 실리콘, 오일/에스터, 보습제, 기능성 원료가 강하다.

### 2.7 원료 코드와 원료명 품질

원료코드 하나가 여러 이름을 갖는 경우는 없었다.

```text
codes_with_multiple_names: 0
```

같은 원료명이 여러 코드로 등장한 경우는 4건 있었다.

```text
Multiwax W-445 Microcrystalline Wax
Ascorbic Acid Fine Powder
D-BIOTIN
노니캘러스추출물
```

전반적으로 원료코드는 안정적인 key로 쓸 수 있다.

### 2.8 중간 원료/색소 베이스

`3JU...`로 시작하는 원료코드가 있다.

```text
3JU 계열 원료코드: 66개
3JU 계열 line 수: 663
```

대표 예:

```text
R#7 40% DSM BASE
IOR 50% DSM BASE
Color base(B#1)
적색227호 5.0% Sol.
Yellow 6 Al Lake 30% DSM Base
TIO2 50% BASE
```

이들은 일반 원료라기보다 중간 제조 베이스 또는 색소 베이스에 가깝다. 추천 시스템에서는 일반 원료와 분리해서 다루는 것이 좋다.

### 2.9 세그먼트별 원료 반복성

원료는 전체 기준으로는 어렵지만, `소그룹 + 제형`으로 나누면 반복성이 강해진다.

#### 컨실러/코렉터 + 고형밤 유분산

```text
n: 172
unique codes: 158
Top20 recall: 70.2%
Top40 recall: 84.4%
Top60 recall: 91.9%
```

주요 원료:

```text
PUROLAN OD-C: 99.4%
TW-HD: 99.4%
TIPAQUE CR-50: 94.2%
PB1400F: 94.2%
Cutina HR Powder: 93.6%
MASESTER E6000 MB: 93.6%
SPAN 83: 93.0%
```

#### 컨실러/코렉터 + W/Si

```text
n: 159
unique codes: 215
Top20 recall: 59.7%
Top40 recall: 78.4%
Top60 recall: 87.0%
```

주요 원료:

```text
정제수: 100.0%
TiO2 HK-50 AS: 99.4%
Sodium Chloride: 99.4%
Iron Oxide Yellow 3AS: 96.2%
Iron Oxide Red 3AS: 95.6%
1,3-Butylene Glycol: 88.1%
Iron Oxide Black 3AS: 88.1%
```

#### 파운데이션-쿠션 + W/Si

```text
n: 137
unique codes: 387
Top20 recall: 42.8%
Top40 recall: 59.9%
Top60 recall: 68.9%
```

쿠션 W/Si는 원료 다양성이 높아 단순 빈도 추천이 약하다. 유사도 검색, 제품명 키워드, 기능성, 색상/톤 정보가 더 필요하다.

#### 립틴트 + O/W

```text
n: 31
unique codes: 46
Top20 recall: 76.7%
Top40 recall: 97.8%
Top60 recall: 100.0%
```

#### 블러셔 + W/Si

```text
n: 18
unique codes: 47
Top20 recall: 64.6%
Top40 recall: 96.5%
Top60 recall: 100.0%
```

### 2.10 원료 예측 시사점

원료는 다음 계층으로 나눠 추천하는 것이 좋다.

```text
1. Candidate vocabulary
   recipe_frequency >= 6
   또는 rare_structural

2. Segment expansion vocabulary
   rare max>3%
   또는 segment-local rare

3. Core 원료
   세그먼트에서 80% 이상 반복되는 원료

4. Optional 원료
   세그먼트에서 20~80% 반복되는 원료

5. Color/Base 원료
   산화철, TiO2, 3JU 색소 베이스, 톤 조정 원료

6. Rare structural 원료
   빈도는 낮지만 max 함량이 5%를 넘는 구조 원료

7. Trace/Concept 원료
   희귀 저함량 추출물, 향, 마케팅 원료
```

원료 예측은 단일 multi-label classifier보다 다음 방식이 적합하다.

```text
입력 bulk 조건
-> 유사 세그먼트 선택
-> 유사 RCP 검색
-> freq>=6 + rare_structural 후보군 구성
-> 세그먼트별 확장 후보군 추가
-> 상별 원료 후보 ranking
-> core/optional/color/rare_structural/trace로 분리
```

## 3. 함량 분석

### 3.1 전체 함량 분포

recipe line 27,796개 기준:

```text
min: 0
p05: 0.001
p25: 0.3
median: 1.2
mean: 3.6336
p75: 4.0
p95: 16.12
max: 99.9
```

함량 bucket:

```text
0: 4
<= 0.000001: 377
<= 0.0001: 965
0.0001~0.001: 6
0.001~0.01: 610
0.01~0.1: 2,982
0.1~1: 6,130
1~5: 10,853
5~20: 4,751
>=20: 1,118
```

대부분의 원료 line은 5% 이하이고, 20% 이상 대량 원료는 전체 line 중 소수다.

### 3.2 레시피 합계와 농도 집중도

모든 레시피는 합계 100%로 맞는다.

```text
recipe total min: 100
recipe total median: 100
recipe total max: 100
```

레시피 내부 concentration:

```text
Top1 원료 median: 27.21%
Top3 합 median: 53.4%
Top5 합 median: 67.95%
Top10 합 median: 86.7%
```

즉 보통 레시피는 상위 5개 원료가 약 68%, 상위 10개 원료가 약 87%를 차지한다.

### 3.3 trace 원료

0.1% 미만 원료는 trace 또는 concept 원료로 볼 수 있다.

```text
레시피당 trace 원료 수 median: 4
p75: 7
p95: 13
max: 49
```

trace line이 많은 레시피는 보통 쿠션/파운데이션, 톤업, 보습스틱처럼 컨셉 원료가 많이 붙은 제품이다.

### 3.4 전체 상별 budget

전체 기준 상별 함량 median:

```text
A상: 25.9%
B상: 1.8%
C상: 12.3%
D상: 12.97%
E상: 5.0%
F상: 4.0%
G상: 2.5%
H상: 2.0%
I상: 0.3%
J상: 0.1%
K상: 0.15%
L상: 0.003%
M상: 0.755%
N상: 0.125%
O상: 1.51%
```

단, 이 값은 전체 평균이므로 직접 사용하면 안 된다. 세그먼트별 상 역할이 다르기 때문이다.

### 3.5 세그먼트별 상 budget

#### 컨실러/코렉터 + 고형밤 유분산

```text
A: 36.7%  (p25 28.90, p75 40.30)
B: 27.0%  (p25 21.00, p75 31.03)
C: 26.37% (p25 23.21, p75 27.47)
D: 12.5%  (p25 10.00, p75 14.11)
E 이후: 대부분 trace 또는 선택 상
```

#### 컨실러/코렉터 + W/Si

```text
A: 14.5%
B: 0.87%
C: 16.7%
D: 18.0%
E: 10.0%
F: 6.16%
G: 4.55%
H: 4.0%
I 이후: 소량/trace
```

#### 파운데이션-쿠션 + W/Si

```text
A: 24.0%
B: 1.0%
C: 10.0%
D: 14.54%
E: 13.31%
F: 8.25%
G: 2.0%
H 이후: 보조/컨셉/향/필름포머
```

#### 파운데이션-일반 + W/Si

```text
A: 21.6%
B: 0.8%
C: 11.0%
D: 14.55%
E: 2.0%
F: 31.816%
G: 2.0%
H 이후: 보조/컨셉/향
```

#### 립틴트 + O/W

```text
A: 59.0%
B: 30.3%
C: 9.1%
D: 2.1%
E 이후: 소량
```

#### 립오일 + 유분산

```text
A: 95.54%
B: 2.0%
C: 1.06%
D: 1.5%
E 이후: trace
```

### 3.6 안정적인 함량 원료

전역 기준으로 함량이 매우 안정적인 원료:

```text
Adenosine: median 0.04%, p25 0.04, p75 0.04
Niacinamide: median 2.0%, p25 2.0, p75 2.0
Niacinamide USP: median 2.0%, p25 2.0, p75 2.0
RonaCare Magnesium Sulfate: median 1.0%, p25 1.0, p75 1.0
Chem OS: median 4.8%, p25 4.5, p75 4.8
Uvinul MC 80 N: median 7.0%, p25 7.0, p75 7.0
Sodium Chloride: median 1.0%, p25 1.0, p75 1.0
Chlorphenesin BP: median 0.25%, p25 0.25, p75 0.25
```

불안정한 원료:

```text
색소류
Iron Oxide 계열
TiO2 계열
일부 분체/베이스
추출물/컨셉 원료
```

색소와 안료는 제품 색상, 톤, 커버력 정보가 없으면 정확 예측이 어렵다.

### 3.7 함량 예측 기준 비교

leave-one-out median predictor 기준:

```text
ingredient_global
- coverage: 96.7%
- MAE: 1.6698
- median_abs_error: 0.2

phase + ingredient
- coverage: 90.9%
- MAE: 1.2971
- median_abs_error: 0.1

segment + ingredient
- coverage: 86.0%
- MAE: 1.0956
- median_abs_error: 0.0

segment + phase + ingredient
- coverage: 80.5%
- MAE: 0.7680
- median_abs_error: 0.0

segment + functional + phase + ingredient
- coverage: 77.7%
- MAE: 0.7120
- median_abs_error: 0.0
```

더 좁게 묶을수록 오차는 줄지만 coverage가 떨어진다.

따라서 함량 추천은 fallback hierarchy가 필요하다.

```text
1. segment + functional + phase + ingredient
2. segment + phase + ingredient
3. segment + ingredient
4. phase + ingredient
5. ingredient_global
```

fallback hierarchy 결과:

```text
coverage: 96.7%
MAE: 0.9336
median_abs_error: 0.0
p75_abs_error: 0.5
p95_abs_error: 5.0
```

### 3.8 함량 예측 시사점

함량은 단일 point prediction보다 분위수 범위 추천이 맞다.

추천 출력 예:

```text
원료명 | 상 | 권장값 | 일반 범위 | 근거
Niacinamide | F | 2.0% | 2.0~2.0 | 안정 원료
Adenosine | F | 0.04% | 0.04~0.04 | 안정 원료
TiO2 HK-50 AS | D | 9.42% | 7.68~17.21 | 색상/커버력 따라 변동
컨셉 추출물 | J/K/L | 0.001~0.01% | 선택 원료
```

## 4. 추천/예측 시스템 설계 시사점

### 4.1 피해야 할 방식

다음 방식은 성능이 나쁠 가능성이 높다.

```text
bulk 입력 -> 상/원료/함량 전체를 한 번에 생성
```

이유:

- 샘플 수가 1,010개로 작다.
- 원료코드는 1,189개로 차원이 크다.
- 희귀 원료가 많다.
- 같은 제품 조건에서도 가능한 처방이 여러 개다.
- 색상, 톤, 원가, 고객사 선호, 규제 정보가 없다.

### 4.2 권장 구조

추천 시스템은 계층형으로 만든다.

```text
1. 입력 bulk 조건 정규화
   - 제품유형_소그룹
   - 제형타입
   - 기능성
   - 벌크유형
   - 기능성 유/무기
   - pH
   - 제품명 키워드

2. 유사 RCP 검색
   - 같은 소그룹/제형/기능성 우선
   - 부족하면 form, sub, keyword 유사도로 fallback

3. 상 template 추천
   - Top3 template 추천
   - 각 template별 상 budget 추천

4. 원료 후보 추천
   - 기본 후보군: recipe_frequency >= 6 또는 rare_structural
   - 세그먼트별 확장 후보군: rare max>3% 또는 segment-local rare
   - core 원료
   - optional 원료
   - color/base 원료
   - rare_structural 예외 원료
   - trace/concept 원료

5. 함량 범위 추천
   - segment + phase + ingredient 단위 p25/median/p75
   - 데이터 부족 시 fallback hierarchy 사용

6. 100% 보정
   - 상 budget에 맞춰 조정
   - 전체 합계 100% 보장
```

### 4.3 MVP 출력

첫 MVP는 다음을 출력하면 된다.

```text
1. 유사 기존 RCP Top10
2. 추천 상 template Top3
3. template별 상 budget
4. 상별 core/optional/rare_structural 원료 후보
5. 원료별 권장 함량과 p25~p75 범위
6. 추천 근거: 몇 개 유사 처방에서 등장했는지
7. 후보군 밖 누락 위험 경고
8. 세그먼트별 확장 후보 사용 여부
```

### 4.4 평가 방법

기존 RCP 하나를 숨기고 bulk만 입력해서 다음을 평가한다.

```text
상 template:
- Top1/Top3/Top5 hit rate

원료:
- Top20/Top40/Top60 recall
- core 원료 recall
- color/base 원료 recall
- rare_structural recall
- 함량 가중 recall
- 후보군 밖 누락 함량

함량:
- MAE
- median absolute error
- p75 absolute error
- 100% 합계 보정 후 오차
```

### 4.5 최종 결론

이 데이터에서는 완전 자동 생성 모델보다 다음 접근이 가장 현실적이다.

```text
유사 처방 검색 기반 추천
+ 세그먼트별 통계
+ 상 template 추천
+ 기본 후보군: freq>=6 + rare_structural
+ 세그먼트별 확장 후보군: rare max>3% + segment-local rare
+ 원료 후보 ranking
+ 함량 분위수 추천
+ 100% normalization
```

특히 `상`은 레시피 구조, `원료`는 세그먼트별 후보, `함량`은 상/원료별 분위수로 분리해서 다뤄야 한다.
