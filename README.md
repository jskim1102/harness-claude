# 1단계

## 1. 명령어 (CEO)

```bash
./run.sh ceo                     # 재접속 (대화 유지) — Orca runtime terminal에서 생존
./run.sh ceo --fresh             # 맥락 부패 시 새 대화로 재시작 (기억 소멸)
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

# 2단계

## 1. 명령어 (CTO)

```bash
## 실행
./run.sh add-cto <name>           # Claude + Codex Orca terminal 준비
./run.sh attach-cto <name>        # Claude CTO Orca terminal focus
./run.sh attach-codex-cto <name>  # Codex Orca terminal focus

/start-project                     # Claude 3명 spawn + 별도 Codex developer 확인

## 종료
./run.sh stop-ceo            # CEO 세션 정리
./run.sh stop-cto <name>     # Claude + Codex CTO 세션 정리
./run.sh down                # CTO 세션 + (backend/frontend) dev + (backend/frontend) docker compose 컨테이너 정지
./run.sh delete-cto <name>   # CTO 완전 teardown: 세션+프로세스+compose 컨테이너+볼륨(self-host mediamtx 포함)+이미지+dir+sqlite+로그 + 공유 pg db(+_test) 회수
./run.sh delete-cto --all    #

## 조회
./run.sh ls                  # 활성화된 CTO 세션 리스트업
./run.sh ports               # 할당된 포트번호 리스트업
./run.sh schema [<name>]     # DB 스키마 리스트업
./run.sh git-listup [<name>] # git에 업로드되는 파일, 폴더 리스트업
./run.sh help

## 유틸
./run.sh test-cto <name> "<자연어>"   # 비대화 한 방 (claude --print)
./run.sh fetch <git-url>            # extract 소스 .sources/ shallow clone

## 점검
./run.sh doctor               # 정합 검사 (금지토큰/참조무결성/문법/버전) — 토큰 0
./run.sh smoke                # 결정론 스모크 380+ (tests/smoke.sh)
./run.sh netbind [<name>]     # 웹서버 외부접속 바인딩 정적검사 (RULES §5.3, 읽기전용)

## 실행
docker compose up -d --build
docker compose down --remove-orphans
./dev.sh up
./dev.sh down
```

segment 승인 후 Claude CTO는 `[dev]` 범위를 same-name inbox로 Codex CTO에
전달한다. Codex TUI에서 inbox 요약을 확인하고 다음 턴에 실행을 명시하면 Codex가
shared `specs/tasks.md`를 읽고 구현하며, 완료증거/blocker도 Claude CTO inbox로
회신한다. CEO와 Codex CTO는 직접 통신하지 않는다.

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
- segment 진행 상태 = `specs/tasks.md` 체크박스 갱신만 (완료 `[✅]`, 블로커 `[❓]`, 미완 `[ ]`)
- **module 빌드 한정**: 완성 시 `modules/<name>/specs/USAGE.md` — CTO가 마지막 segment 통과 후 작성
```

USAGE.md 존재 = 모듈 완성(재사용 가능) 표시. 없으면 빌드 중 — 소비 금지.
(작성 템플릿은 `plugins/_shared/PROCESS.md` §4 정본.)

## 3. Phase 정의

**정본 = `plugins/_shared/PROCESS.md`** (주체·산출물·검증·스킬 배치 전부). 아래는
대시보드용 한 눈 요약 — 상세를 여기 복제하지 않는다 (복제본이 드리프트한다).

| Phase | 주 구동 | 산출물 | 게이트 |
| :---- | :------ | :----- | :----- |
| **phase1** 환경설정 | Codex developer (포트·venv·scaffold·Docker·dev.sh 작성, 띄우진 않음) | 실행환경 + 첫 migration | 🤚 게이트1 환경설정 확인 |
| **phase2** 프론트 UI | designer (시안·디자인시스템·구현계약) + Codex 가 production 구현 | 디자인 산출물 + production frontend (mock 내장) | 🤚 게이트2 라이브 디자인 루프 승인 |
| **phase3+** 개발 | Codex developer, reviewer on-demand | 코드/테스트 (+module 은 USAGE.md) | CTO 자체검증 + 🤚 게이트3 브라우저 실동작 |

- 게이트1·2·3 는 `/goal`(autopilot)로 통과 불가, CTO 자가 선언 불가.
- phase 별 스킬 배치는 아래 "전체 스킬" 과 PROCESS §5 참조.

---

# Clone

```bash
git clone https://github.com/jskim1102/harness-claude.git
cd harness-claude
./run.sh doctor          # 정합 확인 (핵심파일 다 있음)

cd dashboard/frontend && npm install
cd ../backend && python -m venv .venv && .venv/bin/pip install -r requirements.txt
DASH_TOKEN=<비밀> ./run.sh dashboard up
./run.sh dashboard down   # 종료 (아무 터미널에서나)
```

---

# CODEX

CEO 가 쓰는 교차모델 독립 리뷰 두 가지. `/codex-review <project>` 는 완성된 빌드
(`claude-project/<project>` 또는 `modules/<project>` 의 코드·spec)를,
`/codex-protocol-review` 는 하네스 자신(RULES·PROCESS·CEO/CTO role·hooks)을 검토한다.
돌아온 리포트를 읽을 때는 `--consume` 를 붙인다. 상세는
`plugins/ceo/commands/codex-review.md` · `plugins/ceo/commands/codex-protocol-review.md`.

---

# 전체 스킬

```bash
스킬 — 단계·역할별

분해 (stage-2, planner)

- 고정: writing-plans (spec.md/tasks.md 작성 전)
- 유동: plan-eng-review (복잡 빌드 — 아키텍처/엣지케이스) · harness-unknowns-check (고불확실 — 미해결 unknown은 tasks 작성 차단)

phase1 (Codex developer)

- 역할 계약: `plugins/codex-cto/role.md` + RULES/PROCESS/CODE_QUALITY

phase2 (designer lead)

designer
- 고정(project): design-consultation → design-shotgun → design-html (이 순서, skip 금지)
- 고정(module): design-html만
- 유동: browse · design-review · frontend-design · open-design (canvas-design/brand-guidelines/shadcn-ui/web-design-guidelines)
- on-demand 하네스: harness-relay-qa (사용자 Q&A, CTO 경유) · harness-unknowns-check (완료 선언 전)

Codex developer: 승인된 디자인 계약을 production frontend로 구현; 서버는 CTO가 기동

phase3+ (Codex developer 주 / reviewer on-demand)

Codex developer
- TDD·task 검증·완료증거는 `plugins/codex-cto/role.md` 계약으로 강제

reviewer
- 고정: code-review · qa-only
- 유동: health · browse
- 직접 실행(skill 아님): API 테스트 curl·pytest · DB 무결성 SQL

공통 (Claude planner/designer/reviewer)

- harness-relay-qa (질문 relay) · harness-unknowns-check (불확실 체크) · harness-task-format (task line 형식, hook 강제) · harness-remember (결정/메모리 블록)
```

