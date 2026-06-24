# 1단계

## 1. 명령어 (CEO)

```bash
./run.sh ceo

/build-project <brief>           # 축1: project
/build-module <brief>            # 축1: module
```

### 축 정의

```bash
- 축1 - 산출물(deliverable): module | project
- 축2 - 대상(target): new (디렉토리 새로 만듬) | extend:<기존프로젝트> (기존 프로젝트 확장)
- 축3 - 재료(source): scratch | modules:[slug…] | extract:[프로젝트/기능…] | 조합
  - scratch: 재료 없음
  - modules:[slug…]: modules/의 완성 모듈(USAGE.md 있음)을 재료로 사용
  - extract:[프로젝트/기능…]: 기존 프로젝트/소스에서 기능 추출
```

## 2. 스킬

```bash
## 고정
- brainstorming (superpowers) → brief 정렬(축2, 축3, name 확정 + 사용자 확인)
- Library Check → `reuse:<slug> (이유)` 또는 `no-overlap (이유)` 필수
- plan-ceo-review (gstack) → 완성된 plan.md 점검

## 조건부 (축3이 modules/extract/조합인 경우)
- understand-anything → 원본 소스 조사
- extract면 CEO는 파일 수준 위치까지만 plan.md에 기록

## 유동 (사용자 요청)
- grill-me → 사용자 opt-in으로 plan을 더 압박하고 싶을 때
- deep-research → 외부조사가 없으면 plan 필드를 닫을 수 없을 때 CEO가 제안, 사용자 승인 후 실행
```

---

---

---

# 2단계

## 1. 명령어 (CTO)

```bash
## 실행
./run.sh add-cto <name>
./run.sh attach-cto <name>
./run.sh split-cto <name>

## 종료
./run.sh stop-cto <name>     # 한 CTO 정지 (작업 보존 — 세션+프로세스만, dir/specs/포트 유지). 재개 = add-cto
./run.sh down                # 전 세션 kill + dev서버/워커 프로세스 + docker compose 컨테이너까지 정리
./run.sh delete-cto <name>   #
./run.sh delete-cto --all    #

## 조회
./run.sh ls                  # 활성화된 CTO 세션 리스트업
./run.sh ports               # 할당된 포트번호 리스트업
./run.sh schema [<name>]     # DB 스키마 리스트업
./run.sh git-listup [<name>] # git에 업로드되는 파일, 폴더 리스트업
./run.sh help

## 유틸
./run.sh test-cto <name> "<자연어>"   # 비대화 한 방 (claude --print)
./run.sh fetch <git-url>              # extract 소스 .sources/ shallow clone

## 점검
./run.sh doctor               # 정합 검사 (금지토큰/참조무결성/문법/버전) — 토큰 0
./run.sh smoke                # 결정론 스모크 30+ (tests/smoke.sh)

## 실행
docker compose
docker compose down
./dev.sh up
./dev.sh down
```

## 2. 산출물

```bash
- `claude-project/<name>/specs/spec.md` + `specs/tasks.md`
- `modules/<name>/specs/spec.md` + `specs/tasks.md`
```

## 3. 스킬

```bash
## 고정
- writing-plans (superpowers) → spec.md/tasks.md 트리 작성

## 유동 (사용자 요청)
- plan-eng-review (gstack) → 프로젝트/모듈 검토
```

---

---

---

# 3단계

## 1. 명령어

```bash
## CTO
"phaseN.ckptN ~ phaseM.ckptM 진행해"            # segment 지정
"phaseN.ckptN ~ phaseM.ckptM autopilot"        # → CTO가 /goal 설정해 자동 진행

## CEO
/codex-review <name>                            # codex 교차 리뷰
```

## 2. 산출물

```bash
- 실산출물은 코드/테스트
- segment 진행 상태 = `specs/tasks.md` 체크박스(`[x]`) 갱신만
- **module 빌드 한정**: 완성 시 `modules/<name>/specs/USAGE.md` — CTO가 마지막 segment 통과 후 작성
```

```markdown
# <모듈명>      # 무엇을 하는 모듈인지 2~3줄
## 기능         # 뭘 제공하나
## 사용법       # 다른 프로젝트에 붙이는 방법
## 환경         # 필요 env, 의존성, 포트
## API          # 노출 엔드포인트/함수
```

USAGE.md 존재 = 모듈 완성(재사용 가능) 표시. 없으면 빌드 중 — 소비 금지.

## 3. Phase 정의

### phase1: 환경설정

```bash
## 주체
- developer 주 구동 — 포트·venv·scaffold+npm·Docker·dev.sh 작성·설치 (띄우지 않음)
- planner 관찰 — segment loop 내내 생존 + 진행 감시 + 발산 시 revise
- designer 휴면 (phase1 idle, inbox 감시 — phase2부터 lead)
- reviewer 휴면 (on-demand)

## 포트
- offset 할당 → .env / .env.example / compose 기록 (${VAR} 참조, 하드넘버 금지)

## backend
- 호스트: .venv + 선언 패키지 설치
- docker: Dockerfile(백엔드) 작성 + base image pull

## frontend
- 호스트: scaffold(vite 등) → package.json + npm install → node_modules
- docker: Dockerfile(프론트) 작성 + base image pull

## 공통 docker
- docker-compose.yml 작성 (backend+frontend[+db] 서비스 정의). compose up 안 함 — phase3부터

## DB 빌드
- migration 툴(alembic 등) 셋업 + plan 데이터모델 → 첫 migration (raw CREATE TABLE 금지)

## 스킬
developer
- 고정: verification-before-completion (완료 선언 전 증거 수집 — docker images/포트플랜/파일존재)
- 유동: careful (파괴 명령 가드)
```

## phase2: 프론트엔드 UI 디자인

```bash
## 주체 (역할 — 4-상시병렬 아님)

- designer 주 구동 (lead) — 빌드타입별 강도: project = consultation→shotgun→html 체인 / module = design-html만. 게이트2 라이브 디자인 루프(사용자 보는 앞에서 소스 편집)
- developer 보조 — dev 서버(vite) 띄워 유지 + 접속 URL 보고; extract면 frontend-extract [dev] task; 게이트2 배선 이슈 즉시 수정
- planner 관찰 — segment loop 내내 생존 + 진행 감시 + 발산 시 spec/tasks revise + churning 에스컬레이션
- reviewer 휴면 (on-demand — phase2엔 보통 미호출)

## 산출물
- 프론트 UI/디자인 전부 (디자인 시스템 → 시안 → HTML/CSS; 실 UI, 빈 스캐폴드 금지 — phase3로 미루지 마라)
- extract면 프론트 UI 추출(컴포넌트·훅·페이지)도 여기
- mock/local-state(dev-only ?mock 가드) 내장 → 백엔드 없이 핵심 UI 전 경로 검수 (phase3 진입 시 제거)
- 진행상태 = specs/tasks.md 체크박스 [✅]만

## 검증·완료 (게이트2)
- 게이트2 = 사용자 ↔ designer/developer 라이브 디자인 루프 → 승인 (대화 반복)
- dev 서버(vite, 0.0.0.0)로 실 UI 보여야; 접속 URL 보고 의무 (PROCESS §3 step4)
- 게이트2는 /goal로 통과 불가, CTO 자가 선언 불가

## DB
- phase2엔 DB/compose 안 띄움 — live 데이터는 phase3+ (백엔드 contract 기준)

## 스킬
designer
- 고정(project): design-consultation → design-shotgun → design-html (이 순서, skip 금지)
- 고정(module): design-html만
- 유동: browse · design-review · frontend-design · open-design (canvas-design/brand-guidelines/shadcn-ui/web-design-guidelines)
- on-demand 하네스: harness-relay-qa (사용자 Q&A, CTO 경유) · harness-unknowns-check (phase2 완료 선언 전; 미해결 unknown은 design-shotgun 변형으로)

developer (보조)
- dev 서버 유지(vite hot-reload, 0.0.0.0) + URL 보고. compose 안 씀(편집마다 재시작=루프 깨짐)
- extract면 frontend-extract [dev] task 처리
```

## phase3+: 개발

```bash
## 주체 (역할 — 4-상시병렬 아님)
- developer 주 구동 — /goal autopilot, segment 구현, TDD
- reviewer on-demand — 코드리뷰 + API 테스트(curl·pytest) + DB 무결성, dev 서버 기준
- planner 관찰 — reality 발산 시 spec/tasks revise + segment loop 내내 생존 + 진행 감시 + churning(블로커/gate FAIL 반복) 에스컬레이션.
- designer 휴면 (phase2에서 끝)

## 산출물
- 코드/테스트 (재료(축3) 백엔드 벤더링·추출 → glue → API/로직/DB)
- 진행상태 = specs/tasks.md 체크박스 [✅]만
- module 빌드 한정: 완료 시 specs/USAGE.md

## 검증·완료
- CTO 자체검증 (reviewer pass) + 사용자 게이트3 (브라우저 실동작 e2e) → 둘 다 PASS = 완료
- agent의 live-app/browse 확인 = 기계적 자체검증, 게이트3 대체 불가, 단독 완료 선언 X
- 게이트3는 /goal로 통과 불가, CTO 자가 선언 불가

## DB 빌드
- 스키마 변경 = migration 전용 (raw DDL = git_guard 차단).
- 파괴적 변경(drop/alter)은 사용자 승인 후

## 스킬
developer
- 고정: test-driven-development (실패 테스트 먼저) · verify (완료 보고 전 실 앱 동작 확인) · verification-before-completion (증거 없이 완료 선언 금지)
- 유동: run (앱 띄워 변경 확인) · systematic-debugging/investigate (버그=근본원인 먼저) · simplify (과복잡 시) · careful (파괴 명령 가드)

reviewer
- 고정: code-review (코드 평가 주력) · qa-only (웹 UI 플로우, report-only)
- 유동: health (품질 추세 점수) · browse (라이브 동작 확인+스샷; 게이트3 대체 X)
```

---

---

---
# Clone
```bash
git clone https://github.com/jskim1102/harness-claude.gitcd harness-claude
./run.sh doctor          # 정합 확인 (핵심파일 다 있음)

cd dashboard/frontend && npm install
cd ../backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
DASH_TOKEN=<비밀> ./run.sh dashboard up
./run.sh dashboard down   # 종료 (아무 터미널에서나)
```

---

---

---

#  CODEX
```bash
  1. 프로젝트 산출물 리뷰

  /codex-review <project-name>
  /codex-review <project-name> --consume

  대상:
  claude-project/<project> 또는 modules/<project>

  역할:
  완성된 빌드 코드/spec/README를 독립 리뷰합니다.

  2. 하네스 프로토콜 리뷰

  /codex-protocol-review
  /codex-protocol-review --consume

  대상:
  harness-claude 자체의 RULES.md, PROCESS.md, CEO/CTO role, hooks, authority map 등
```
---

---

---

# 전체 스킬

```bash
스킬 — 단계·역할별

분해 (stage-2, planner)

- 고정: writing-plans (spec.md/tasks.md 작성 전)
- 유동: plan-eng-review (복잡 빌드 — 아키텍처/엣지케이스) · harness-unknowns-check (고불확실 — 미해결 unknown은 tasks 작성 차단)

phase1 (developer)

- 고정: verification-before-completion (완료 선언 전 증거 수집 — docker images/포트플랜/파일존재)
- 유동: careful (파괴 명령 가드)

phase2 (designer lead)

designer
- 고정(project): design-consultation → design-shotgun → design-html (이 순서, skip 금지)
- 고정(module): design-html만
- 유동: browse · design-review · frontend-design · open-design (canvas-design/brand-guidelines/shadcn-ui/web-design-guidelines)
- on-demand 하네스: harness-relay-qa (사용자 Q&A, CTO 경유) · harness-unknowns-check (완료 선언 전)

developer (보조): 신규 고정 스킬 없음 (dev 서버 유지 = 직접 실행)

phase3+ (developer 주 / reviewer on-demand)

developer
- 고정: test-driven-development · verify · verification-before-completion
- 유동: run · systematic-debugging/investigate · simplify · careful

reviewer
- 고정: code-review · qa-only
- 유동: health · browse
- 직접 실행(skill 아님): API 테스트 curl·pytest · DB 무결성 SQL

공통 (전 teammate)

- harness-relay-qa (질문 relay) · harness-unknowns-check (불확실 체크) · harness-task-format (task line 형식, hook 강제) · harness-remember (결정/메모리 블록)
```
