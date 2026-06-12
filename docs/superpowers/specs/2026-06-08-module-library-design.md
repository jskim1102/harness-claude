# 모듈 라이브러리 + 사서 에이전트 — 설계

날짜: 2026-06-08
상태: 구현 완료 (stock / modules / librarian 가동). 2026-06-09: borrow 제거; `--plan` 은 feature-extract 전용으로 재도입.

## 1. 문제

하네스로 여러 프로젝트를 만든다. 서로 다른 프로젝트지만 같은 기능을 쓴다
(RTSP 등록/스트리밍, 카카오 로그인, YOLO 양자화 추론 등). 매번 새로
구현하지 말고, 한 번 잘 만든 기능을 모듈로 적립해두고, 새 프로젝트의
planner 가 plan 짤 때 그 모듈을 참고해 재구현을 피한다.

기존 `feature-extract` 는 소스→타겟 1:1 일회성 추출 plan 이다.
이 설계는 시간 따라 쌓이고 plan 시점에 검색되는 **영속 라이브러리**를
추가한다.

## 2. 핵심 결정

| 항목 | 결정 |
|---|---|
| 모듈 내용물 | 실제 코드 벤더링 (정리된 독립 실행가능 코드 복사 보관) |
| 새 에이전트 | CEO 산하 1명 "사서(librarian)". **수집 전담** |
| 라이브러리 위치 | `harness-claude/modules/` (git 추적, 별도 레포 아님) |
| 만드는 명령 | `/stock` (CEO 창 슬래시커맨드) |
| 조회 명령 | `/modules` (CEO·CTO 양쪽) |
| 활용 경로 | `./run.sh add-cto ... --module {모듈명}` 플래그 + planner 자동 grep |
| 중복 처리 | 같은 기능 둘이면 understand-anything 등으로 **의미있게 통합**, 더 나은 단일 모듈로. 출처 양쪽 기록 |

## 3. 대칭 구조

CTO 가 4-agent 팀(planner/designer/developer/reviewer)을 가지듯, CEO 는
1-agent(사서)를 가진다. 현재 CEO 는 에이전트 0개 — 슬래시커맨드+워크플로우뿐.
모듈 라이브러리 생명주기를 독립 페르소나로 묶는다.

```
CEO ─ 사서(1)                              → 기능 창고 채우고 정리
 └ CTO ─ planner/designer/developer/reviewer(4)  → 프로젝트 빌드
          └ planner 가 plan 시 창고 검색 (소비측, 소수정)
```

## 4. 창고 구조 (`harness-claude/modules/`)

```
modules/
  INDEX.md                  # 1개. 얇은 색인 (모듈당 1줄 테이블)
  rtsp-streaming/
    MODULE.md               # 이 모듈 설명서 (사서 작성)
    code/                   # 소스에서 꺼내 정리한 실코드
      backend/...
      frontend/...
    deps.md                 # 라이브러리·런타임 가정
  kakao-login/
    MODULE.md
    code/
    deps.md
```

### INDEX.md — 기획자의 1차 검색 대상

```markdown
| 모듈 | 기능 | 스택 | 출처 | 갱신일 |
|---|---|---|---|---|
| rtsp-streaming | 카메라 RTSP CRUD + mediamtx 스트리밍 | FastAPI+React+mediamtx | prime | 2026-06-08 |
| kakao-login | 카카오 OAuth 로그인 | FastAPI+React | tunnel | 2026-06-08 |
```

### MODULE.md — 모듈별 설명서

- 기능 1문단
- 핵심 파일 목록
- 통합 단계 (새 프로젝트에 꽂는 법)
- 파일별 COPY / ADAPT / RE-IMPL 권고 (feature-extract 출력 재활용)
- 알려진 제약/주의
- 출처 (통합된 경우 양쪽: `prime + tunnel`)

## 5. 명령어 체계

### 만들기 — CEO 창 (사서)

```
/stock {source_repo} "<feature 설명>"
예) /stock /path/to/prime "RTSP CRUD + mediamtx 스트리밍"
```

동작:
1. feature-extract 워크플로우 실행 (추출 plan 생성, 기존 도구 재활용)
2. 사서가 plan 따라 소스에서 코드 꺼내 `code/` 에 정리 (의존성 떼고 standalone)
3. `MODULE.md` 작성
4. `INDEX.md` 한 줄 추가
5. 같은 기능 이미 있으면 → 기존 모듈 + 새 소스 둘 다 understand-anything 으로
   분석 → 통합해 더 나은 단일 모듈로 재합성, 출처 양쪽 기록

### 조회 — 양쪽

```
/modules        # INDEX.md 출력
```

## 6. 활용 — 3가지 진입 케이스

> NOTE(2026-06-09): borrow(옛 1:1 차용 커맨드) 제거됨. `--plan` 은 borrow 와
> 분리해 **feature-extract 전용** 플래그로 재도입. add-cto 의 dir 인자는 생략 시
> 컨벤션대로 자동 결정 (greenfield/plan → `claude-project/`, `--module` → `claude-module/`).

```bash
# 1. 아예 새로 (greenfield)
./run.sh add-cto {name}                     # dir 생략 → claude-project/{name}
/start-project "<목표>"                       # CTO 창 안에서

# 2. feature-extract plan 차용
#   먼저 CEO 창: /feature-extract <소스> "<기능>" → feature-extract/<slug>-YYYY-MM-DD.md
./run.sh add-cto {name} --plan {md경로}      # dir 생략 → claude-project/{name}; plan.md 주입
/start-project "<목표>"                       # 부팅시 plan.md, planner 가 그 청사진대로

# 3. 모듈 활용 (창고서 영속 모듈)
#   먼저 CEO 창: /stock 으로 적립 (기능당 한 번)
./run.sh add-cto {name} --module {모듈명}    # dir 생략 → claude-module/{name}
/start-project "<목표>"                       # 부팅시 use-modules.md, planner 가 code/ 참고
```

`--module` 과 `--plan` 은 동시 사용 불가(택1). 여러 모듈은 콤마구분.

### planner 소비측 확장

`plugins/cto/agents/planner.md` 에 단계 추가:
- tasks.md 작성 전 `modules/INDEX.md` grep
- 맞는 모듈 있으면 `MODULE.md` 읽고 `code/` 참고 → 재구현 대신 적용
- spec/design 에 `module:rtsp-streaming 재사용` 명시

## 7. 기존 도구와 관계

- **feature-extract**: 추출 엔진 + plan 생성기 (그대로). 사서가 내부 호출.
- **/stock**: 영속 창고 적립. 시간 따라 쌓임.

## 8. 구현 범위 (변경 파일)

| 파일 | 변경 |
|---|---|
| `plugins/ceo/agents/librarian.md` | 신설 — 사서 페르소나 |
| `plugins/ceo/commands/stock.md` | 신설 — `/stock` 커맨드 |
| `plugins/ceo/commands/modules.md` | 신설 — `/modules` 조회 |
| `plugins/cto/commands/modules.md` | 신설 — CTO 창 조회 |
| `run.sh` | `add-cto` 에 `--module` 플래그 추가 |
| `plugins/cto/agents/planner.md` | 소비 단계 추가 (INDEX grep) |
| `modules/INDEX.md` | 신설 — 빈 색인 스캐폴드 |

## 9. 비범위 (YAGNI, 나중에)

- `/use-module` 중간투입 커맨드 (이미 돌아가는 프로젝트에 모듈 추가) — 나중
- 자동 모듈화 제안 (CTO 완료시 재사용성 감지) — 나중
- 별도 git 레포 승격 — 모듈 많아지면
- 모듈 버전 태그/시맨틱 버저닝 — 필요해지면
