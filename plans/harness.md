# 하네스 재설계 — 최종 설계

> 상태: **설계 확정** (2026-06-12). 구현 전. 검토 이력: `harness-review.md`.

# 전체 시스템 특징

- CTO tmux는 현재 phase:ckpt와 사용된 스킬·해당 스킬을 사용한 에이전트를 출력 (`developer ★ test-driven-development` 형식)
- CTO 터미널은 항상 `alias claude='claude --dangerously-skip-permissions'`으로 실행
- CEO/CTO 터미널 창 항상 독립 운영 — observe 폐기
- codex 리뷰 = 사용자 요청 시만 (`/codex-review <name>`). 자동 트리거 전부 폐기. 메커니즘(.pending 마커 + --consume 위조방지)은 유지
- inbox [N] 메시징 유지 (SQLite + harnessd, add-cto가 자동 기동)
- 스킬 운용 원칙: 단계마다 필수 스킬 몇 개만 고정, 나머지는 시스템이 유동 판단
- 기존 체계 전면 폐기: greenfield/feature-extract/stock 3분할, modules/INDEX.md, MODULE.md, use-modules.md, autopilot wake-loop·상태파일(autopilot-state/mode-state)
- 모듈 완성 표시 = `modules/<name>/specs/USAGE.md` 존재 (없으면 소비 금지, fail-closed). 1단계 Library Check = `modules/*/specs/USAGE.md` 스캔
- README.md는 사용자 전용 — 시스템 자동 작성 금지 (RULES §1. USAGE.md는 별개)
- extract 동작: CEO가 understand-anything으로 파일 수준 위치 분석(plan ## 3 기록) → CTO가 추출·통합 ckpt 분해 → developer가 직접 복사·적응. 소스 read-only. git URL 소스는 `./run.sh fetch <url>` 로 `.sources/` shallow clone
- run.sh: `down`/`delete-cto`는 CTO가 띄운 dev서버·워커 프로세스까지 정리 (tmux kill만으론 잔존 — rtsp 부활 사고 교훈)
- 빌드 잔재(plan.md, specs/)는 완성 후에도 유지 (이력)
- DB 스키마 = migration 전용 (RULES §9): 빌드 중 스키마 변경은 ad-hoc DDL 금지, migration 파일로만. 파괴적 변경은 사용자 승인. git_guard 가 raw CLI DDL(ALTER/DROP) 결정론 차단. 사용자는 `./run.sh schema [<name>]` 로 빌드별 테이블·컬럼 현황 조회 (정적 스캔, 읽기전용)
- /goal 요건: Claude Code v2.1.139+ — 확인 완료 (현재 2.1.173, run.sh CLAUDE_MIN_VERSION 이 스폰 시 강제)

## 모듈 vs 프로젝트
- **모듈**: 여러 프로젝트에 재사용되는 기능 단위. 그 자체가 개발 산출물. 프론트 **단순**, 기능 목적 최우선. `modules/<name>/` (작업장=라이브러리 동일).
- **프로젝트**: 실사용 상용 서비스. 모듈 조립+glue 또는 scratch. 프론트 **디자인 중요**. `claude-project/<name>/`.
- 둘은 다른 빌드 — 명령어·디렉토리로 명시 분리 → 착각 불가.

---

# 1단계 (CEO)

## 1단계 산출물

- `claude-project/<name>/plan.md`
- `modules/<name>/plan.md`

## 1단계 실행 명령어

```bash
./run.sh ceo                      # CEO 세션 시작
/build-project <brief>            # 프로젝트 빌드 (축1=project 확정)
/build-module <brief>             # 모듈 빌드 (축1=module 확정)
```

## 1단계 요약

- 트리거: `/build-project <brief>` | `/build-module <brief>` → 축1 확정
- CEO가 `<빌드dir>/plan.md` 1개 작성 (project=claude-project/, module=modules/) — dir 생성하며
- 축2(target)·축3(source)는 CEO가 brief 분석 → plan에 적고 사용자 확인
- Library Check = `modules/*/specs/USAGE.md` 스캔 → reuse:<slug>(이유) | no-overlap(이유) — fail-closed

**plan.md 구조:**
```markdown
# Plan: <name>
## 1. Build Type      # 축1(명령서 확정) / 축2 / 축3
## 2. Goal            # 무엇을 왜, 1~2줄
## 3. Library Check   # reuse:<slug>(이유) | no-overlap(이유) (+extract면 파일 수준 위치)
## 4. Requirements    # 핵심 기능 bullet 요점만 (상세는 CTO)
## 5. Constraints     # 스택/보안/성능, non-goals
## 6. Open Questions  # CTO가 분해 때 풀 것
```

## 1단계 특징

- 축1 — 산출물(deliverable): `module` | `project` → 저장위치(modules/ vs claude-project/), 프론트(단순 vs 화려), 완료기준 가름
- 축2 — 대상(target): `new` | `extend:<기존프로젝트>`
- 축3 — 재료(source): `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합 가능

## 1단계 스킬

**고정 (앞):**

1. `brainstorming` — brief↔사용자 정렬 (축2·3 단정 방지)

**조건부 고정 (축3 source ≠ scratch — 시스템 자동 선택):**

- `understand-anything` — 재료가 코드(modules/기존 프로젝트)일 때
- `deep-research` — 외부/시장 조사 필요할 때

**고정 (뒤, plan.md 검사 게이트):**

2. `plan-ceo-review` — 작성된 plan.md 내용/scope/전제 점검 후 CTO로

**유동:**

- `office-hours` — 아이디어 모호/검증 필요 시
- `grill-me` — 사용자가 plan 압박 원할 때
- `deep-research` — 조건부 외에도 필요 시

---

# 2단계 (CTO: 분해 + phase1~2)

## 2단계 산출물

- `claude-project/<name>/specs/spec.md` + `specs/tasks.md`
- `modules/<name>/specs/spec.md` + `specs/tasks.md`

## 2단계 실행 명령어

```bash
# 1) CTO 스폰 (새 터미널)
./run.sh add-cto claude-project/<name>/plan.md    # 프로젝트 빌드 CTO
./run.sh add-cto modules/<name>/plan.md           # 모듈 빌드 CTO
#   → tmux 세션 cto-<name> 생성, plan.md 읽고 분해 자동 시작
#   → plan.md 없으면 스폰 실패 (1단계 선행 강제)
#   → harnessd 자동 기동

# 2) CTO 화면 접속
./run.sh attach cto-<name>        # = tmux attach -t cto-<name>

# 3) 빠져나오기 (세션은 계속 돌아감)
Ctrl+b → d                        # detach

# 보조
./run.sh ls                       # 세션 목록
```

## 2단계 요약

1. CTO : plan.md 읽고 전체 phase/ckpt 트리 구성 → `specs/spec.md` + `specs/tasks.md`
   (phase1=환경설정, phase2=프론트 디자인, phase3+=개발 — 고정. 축2=extend면 기존 트리 append)
2. 사용자 : 트리 보고 segment 지정 — phase1·2도 segment로 실행
3. CTO : phase1 = 환경설정 — 포트(offset→.env/.env.example/compose)·venv+패키지·Docker pull·Dockerfile(+GPU면 Dockerfile-gpu)
   ※ 작성·준비만, 컨테이너 실행 X
   🤚 사용자: 환경설정 확인 ← **게이트 1**
4. CTO : phase2 = 프론트 디자인 — 시안 → dev 서버(hot-reload) 기동
   🤚 사용자: **라이브 디자인 루프** ← **게이트 2**
   브라우저 접속 → 수정사항 말함 → designer/developer 즉시 수정 → 새로고침 확인 → 반복 → 승인
5. phase3+ 개발은 3단계로 — **Docker compose 기동은 phase3부터**

## 2단계 특징

- 산출물 2파일 분리: spec.md(기능 상세 — plan ## 4 요점을 펼침) + tasks.md(phase→ckpt 트리, ckpt ID `phaseN.ckptN` = segment dispatch 단위)
- 분해 공식 고정: phase1=환경설정 → phase2=프론트 디자인 → phase3+=개발
- **장치1 — 역참조 커버리지**: 모든 ckpt가 spec 기능라벨(`← F<n>`) 역참조. "모든 Feature ≥1 ckpt" 기계 검증 (fail-closed, 누락 차단)
- **장치2 — supplied/to-build 태그**: 재료(modules/extract) 기반 기능은 `[supplied:<출처>]` 필수 표기 → 재구현 착각 차단
- 사람 게이트: 사용자가 트리 보고 segment 지정 = 사실상 분해 승인 (별도 리뷰 게이트 없음)

**spec.md / tasks.md 형식:**
```markdown
# Spec: <name>            # specs/spec.md
## Features
- [F1] <기능> [to-build]
- [F2] <기능> [supplied:modules/<name>]
```
```markdown
# Tasks: <name>           # specs/tasks.md
## phase1 — 환경설정
### phase1.ckpt1 포트→.env/compose · venv · Docker · Dockerfile
## phase2 — 프론트엔드 디자인
### phase2.ckpt1 <디자인 작업>
## phase3 — <개발...>
### phase3.ckpt1 <작업>  ← F1
```

## 2단계 스킬

### 분해 (CTO/planner)

**고정:**

1. `writing-plans` — spec.md + tasks.md 생산 본체

**+기계 검증 (스킬 아님):** 장치1 커버리지 체크 자동 실행

**유동:**

- `plan-eng-review` — 복잡 빌드 시 아키텍처 점검
- `harness-unknowns-check` — 불확실성 높을 때

### phase1 환경설정 (developer)

**고정:**

1. `verification-before-completion` — 완료 주장 전 증거 확보 (docker ps·포트·헬스체크) → 🤚 게이트1

**유동:**

- `run` / `investigate` / `careful`

### phase2 프론트엔드 디자인 (designer)

**project: 고정 3개 파이프라인**

1. `design-consultation` — 디자인 시스템 정립. 이때 open-design 디자인시스템 152개에서 선택/참조
2. `design-shotgun` — 시안 N개 보드 → 사용자 선택
3. `design-html` — production HTML/CSS. 선택된 open-design tokens.css 사용
→ 🤚 게이트2

**module: 고정 1개**

- `design-html` (+필요시 open-design 시스템 1개 참조)
→ 🤚 게이트2

**유동 (둘 다):**

- `browse` — 프리뷰/스크린샷
- `design-review` — 시각 QA
- `frontend-design` — 공식 Anthropic 플러그인
- open-design 스킬들 (`.sources/open-design/skills/` 157개 중 디자인 계열 — canvas-design, brand-guidelines, shadcn-ui, web-design-guidelines 등) — 필요시 호출

open-design 참고: 벤더링은 design-systems/ + 스킬 2~3개만(앱/데몬 X). 시험 완료(2026-06-12): frontend-design+linear-app → 관제 대시보드 976줄, 콘솔에러 0, 품질 高. 마찰 4(토큰 누락·앱밀도 가이드 얇음·폰트 미번들·한글 폰트)는 도입 시 처리.

---

# 3단계 (CTO: phase3+)

## 3단계 산출물

- 실산출물은 코드/테스트
- segment 진행 상태 = `specs/tasks.md` 체크박스(`[x]`) 갱신만
- **module 빌드 한정**: 완성 시 `modules/<name>/specs/USAGE.md` — CTO가 마지막 segment 통과 후 작성
  ```markdown
  # <모듈명>      # 무엇을 하는 모듈인지 2~3줄
  ## 기능         # 뭘 제공하나
  ## 사용법       # 다른 프로젝트에 붙이는 방법
  ## 환경         # 필요 env, 의존성, 포트
  ## API          # 노출 엔드포인트/함수
  ```
  USAGE.md 존재 = 모듈 완성(재사용 가능) 표시. 없으면 빌드 중 — 소비 금지.

## 3단계 실행 명령어

```bash
# CTO 세션 채팅에서 (사용자 입력):
"phaseN.ckptN ~ phaseM.ckptM 진행해"            # segment 지정
"phaseN.ckptN ~ phaseM.ckptM autopilot"        # → CTO가 /goal 설정해 자동 진행

# CEO 창에서 (사용자 요청 시만):
/codex-review <name>                            # codex 교차 리뷰
```

## 3단계 요약

1. 사용자 : segment 지정 (`phaseN.ckptN ~ phaseM.ckptM`)
2. CTO : segment 실행 — 내부는 `/goal` autopilot (조건: 범위 내 전 ckpt `[x]` + 검증 증거, `or stop after N turns`)
3. CTO : segment 완료 시 필요 판단되면 reviewer 호출 — API 테스트(curl·pytest)·DB 무결성(SQL)·코드 평가 → 지적 시 수정
4. CTO : 사용자에게 "완료" 보고 (검증 증거 포함)
5. 사용자 : 웹 브라우저 실사용 테스트 ← **게이트3**
6. 통과 → 다음 segment (1로 반복)

- `/goal`로 게이트1·2 통과 불가 (autopilot 범위 = phase3+만)
- `[!]` 블로커 시 CTO가 goal 중단 → 사용자 surface
- codex = 사용자 요청 시만

## 3단계 특징

- segment를 사용자가 지정해주면 segment대로 개발
- segment 내부에서는 autopilot 형태(`/goal` 활용)로 개발 완료될 때까지 CTO가 자동 진행
  (매 턴 끝 소형 모델이 조건 평가 → 미충족 시 자동 다음 턴. 상태 = tasks.md 체크박스만)
- segment가 완료되면 CTO는 API 테스트, DB 무결성 등을 검토
- segment가 완료되면 사용자는 웹 브라우저에서 실제 작동 테스트
- CTO·사용자 테스트 완료되면 다음 segment로

## 3단계 스킬

### developer 스킬

**고정 2개:**

1. `test-driven-development` — 비즈니스 로직 테스트 먼저 (플러밍 예외, 예외 시 완료노트 명시)
2. `verify` — 완료 보고 전 라이브 앱 실동작 확인

**유동:**

- `run` — 앱 기동
- `systematic-debugging` / `investigate` — 버그 근본원인
- `simplify` — 과복잡 코드 정리
- `careful` — destructive 명령 가드

※ phase1용 `verification-before-completion`은 2단계 스킬에 기재
※ karpathy-guidelines = 사용자 글로벌 CLAUDE.md에 동일 내용 → 중복 제외

### reviewer 스킬

**고정 2개:**

1. `code-review` — 코드 평가 (1차 high / 재리뷰 medium)
2. `qa-only` — 웹 UI 흐름 report-only QA

**유동:**

- `health` — 품질 트렌드
- `browse` — 웹 동작 검증/스크린샷

※ API 테스트(curl·pytest)·DB 무결성(SQL)은 스킬 없이 직접 실행 — reviewer 필수 임무
※ 결과 = 파일 X, 보고 메시지

---

# run.sh 명령 세트

```bash
# ── 세션 기동 ──
./run.sh ceo                                     # CEO 활성화
./run.sh add-cto claude-project/<name>/plan.md   # 프로젝트 빌드 CTO
./run.sh add-cto modules/<name>/plan.md          # 모듈 빌드 CTO
./run.sh attach cto-<name>                       # tmux attach 동일

# ── 조회 ──
./run.sh ls / ports / help
./run.sh schema [<name>]                         # DB 스키마 현황 (테이블·컬럼, 읽기전용)

# ── 종료/삭제 ──
./run.sh down                # 전 세션 kill + dev서버/워커 프로세스까지 정리
./run.sh delete-cto <name>   # 특정 CTO 삭제 (세션+프로세스+dir 잔재)
./run.sh delete-cto --all

# ── 유틸 ──
./run.sh test-cto <name> "<자연어>"   # 비대화 한 방 (claude --print)
./run.sh fetch <git-url>              # extract 소스 .sources/ shallow clone

# ── 점검 ──
./run.sh doctor               # 정합 검사 (금지토큰/참조무결성/문법/버전) — 토큰 0
./run.sh smoke                # 결정론 스모크 30+ (tests/smoke.sh)
```

---

# 시스템 점검 (3계층)

2026-06-12 구현 리뷰(다이나믹 워크플로우 27 agents + codex)의 교훈을 제도화.
버그 17건 중 11건 = 참조 문서망의 구체계 drift / 감사 false-positive 62% /
실동작 테스트만 잡는 버그 존재 / 두 트랙(자체·codex)은 상보적.

| 계층 | 도구 | 언제 | 비용 |
|---|---|---|---|
| 1 결정론 | `./run.sh doctor` + `./run.sh smoke` | **하네스 파일 수정 후 무조건** (CEO 의무) | 토큰 0, 초 단위 |
| 2 의미 | `/harness-audit` (6 perspective + adversarial verify) | 큰 개편 후, 가끔 | agent 토큰 |
| 3 교차모델 | codex consult/review | 사용자가 원할 때만 | 외부 모델 |

- doctor 가 새 금지 토큰·참조를 알게 되면 `cmd_doctor` 의 banned 목록을 함께 갱신.
- 감사 finding 은 **adversarial verify 없이 믿지 않는다** (false-positive 62% 실측).
- 운영 주의 2: 에이전트가 고치는 파일은 IDE 탭을 닫아둘 것(stale-buffer 덮어쓰기
  사고 실발생) · 리뷰 도는 중 같은 파일을 동시 수정하지 말 것(반박 노이즈).

---

# 타임라인

모드: 🤚 = 사용자 확인 · 🤖 = goal 기반 autopilot · ⚙️ = 자체 리뷰

| 단계 | 주체 | 하는 일 | 모드 |
|---|---|---|---|
| 1 Plan 작성 | CEO ↔ 사용자 | `/build-project`·`/build-module <brief>` → brief 정렬 → 축2·3 확인 → `<빌드dir>/plan.md` 작성 (Library Check 포함) | 🤚 **plan 확정** |
| 1 Plan 검사 | CEO | 작성된 plan.md 내용/scope/전제 자체 점검 후 CTO로 | ⚙️ **plan 자체 점검** |
| 2 스폰 | 사용자 | `./run.sh add-cto <빌드dir>/plan.md` → `./run.sh attach cto-<name>` (plan.md 없으면 스폰 실패) | 🤚 **스폰 실행** |
| 2 분해 | CTO | plan.md → `specs/spec.md` + `specs/tasks.md` (phase→ckpt 트리) + 커버리지 기계검증 (fail-closed) | ⚙️ **커버리지 기계검증** |
| 3 구간지정 | 사용자 | 트리 보고 **`phaseN.ckptN~phaseM.ckptM`** 지정 (= 분해 승인, phase 걸쳐도 됨) | 🤚 **segment 지정 = 분해 승인** |
| 3 phase1 환경설정 | developer | 포트(`.env`/`.env.example`/compose)·venv+패키지·Docker pull·Dockerfile(+GPU면 Dockerfile-gpu) — **작성·준비만, 컨테이너 실행 X** | 🤖 **자동 진행** |
| 3 게이트1 | 사용자 | 환경설정 확인 | 🤚 **환경 확인** |
| 3 phase2 프론트 디자인 | designer | 디자인 시스템 → 시안 → production HTML/CSS (module=단순/project=화려) → dev 서버(hot-reload) 기동 | 🤖 **자동 진행** |
| 3 게이트2 | 사용자 ↔ designer/developer | **라이브 디자인 루프**: 브라우저 접속 → 수정사항 말함 → 즉시 수정 → 새로고침 확인 → 반복 → 승인 | 🤚 **디자인 승인 (대화 반복)** |
| 3 phase3+ 빌드 | developer | segment 를 `/goal` autopilot 으로 자동 진행 (조건: 범위 전 ckpt `[x]`+검증 증거, `or stop after N turns`) — **compose 기동 시작** | 🤖 **goal autopilot** |
| 3 자체 검증 | CTO → reviewer | 필요 판단 시 reviewer 호출 — API 테스트(curl·pytest)·DB 무결성(SQL)·코드 평가 → 지적 시 수정 → 사용자에 "완료" 보고(증거 포함) | ⚙️ **reviewer 검증** |
| 3 게이트3 | 사용자 | 웹 브라우저 실사용 테스트 — PASS→다음 segment(구간지정으로 복귀) / FAIL→재작업 | 🤚 **실사용 테스트** |
| 마감 (module 한정) | CTO | 마지막 segment 통과 후 `specs/USAGE.md` 작성 = 재사용 가능 표시 | ⚙️ **USAGE.md 작성** |
| codex (옵션) | 사용자 → CEO | 원할 때만 `/codex-review <name>` → CEO가 결과 요약 보고 | 🤚 **사용자 요청 시만** |

- `[!]` 블로커 = 어느 단계든 goal 중단 → 사용자 surface
- 🤖 구간이라도 게이트1·2는 `/goal` 로 통과 불가

---
