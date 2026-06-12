# 하네스 빌드 프로세스

위치: `plugins/_shared/` (RULES.md 옆 — canonical 운영 스펙). SessionStart 가
**CTO 세션에** 주입한다. 설계 배경·이력의 정본 = `plans/harness.md`.
하드룰(git/파일/포트/인박스/충실도/autopilot 경계)은 RULES.md — 본 문서는 **흐름**.

> 모드 legend: 🤚 사용자 확인 · 🤖 goal 기반 autopilot · ⚙️ 자체 리뷰

## 0. 모듈 vs 프로젝트 (가장 먼저 — 내가 뭘 짓고 있는가)

- **모듈** = 여러 프로젝트에 재사용되는 기능 단위. 그 자체가 산출물.
  프론트 **단순**(재사용 쉽게), 기능 목적 최우선. `modules/<name>/`.
- **프로젝트** = 실사용 상용 서비스. 모듈 조립+glue 또는 scratch.
  프론트 **디자인 중요**. `claude-project/<name>/`.
- 빌드타입은 **plan.md 의 부모 디렉토리가 확정**한다 (modules/ = 모듈,
  claude-project/ = 프로젝트). CTO 재량으로 재해석 금지 — 모듈을 풀
  프로젝트처럼 짓거나, 그 역도 위반.

plan.md 의 3축 선언을 그대로 따른다:
- 축1 deliverable: `module` | `project`
- 축2 target: `new` | `extend:<기존프로젝트>` (extend = 기존 tasks.md 트리에 append)
- 축3 source: `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합

## 1. 타임라인 (전체 흐름)

| 단계 | 주체 | 하는 일 | 모드 |
|---|---|---|---|
| 1 Plan 작성 | CEO ↔ 사용자 | `/build-project`·`/build-module <brief>` → `<빌드dir>/plan.md` (3축 + Library Check) | 🤚 plan 확정 |
| 1 Plan 검사 | CEO | plan.md 자체 점검 후 CTO로 | ⚙️ |
| 2 스폰 | 사용자 | `./run.sh add-cto <빌드dir>/plan.md` (plan.md 없으면 실패) | 🤚 |
| 2 분해 | CTO | plan.md → `specs/spec.md` + `specs/tasks.md` + 커버리지 기계검증 | ⚙️ |
| 3 구간지정 | 사용자 | `phaseN.ckptN~phaseM.ckptM` 지정 (= 분해 승인) | 🤚 |
| 3 phase1 환경설정 | developer | 포트·venv·Docker 준비 (실행 X) | 🤖 |
| 3 게이트1 | 사용자 | 환경설정 확인 | 🤚 |
| 3 phase2 프론트 디자인 | designer | 시스템→시안→HTML/CSS → dev 서버 기동 | 🤖 |
| 3 게이트2 | 사용자 ↔ designer/developer | 라이브 디자인 루프 → 승인 | 🤚 대화 반복 |
| 3 phase3+ 빌드 | developer | `/goal` autopilot — compose 기동 시작 | 🤖 |
| 3 자체 검증 | CTO → reviewer | 필요 시 API·DB·코드 검증 → 수정 → 완료 보고 | ⚙️ |
| 3 게이트3 | 사용자 | 브라우저 실사용 테스트 → PASS=다음 segment | 🤚 |
| 마감 (module 한정) | CTO | `specs/USAGE.md` 작성 = 재사용 가능 표시 | ⚙️ |
| codex (옵션) | 사용자 → CEO | 사용자가 원할 때만 `/codex-review <name>` | 🤚 |

- `[!]` 블로커 = 어느 단계든 goal 중단 → 사용자 surface
- 🤖 구간이라도 게이트1·2는 `/goal` 로 통과 불가 (RULES §8)

## 2. 분해 (CTO — 스폰 직후)

plan.md 읽고 전체 phase/ckpt 트리를 만든다 → `<빌드dir>/specs/spec.md` + `specs/tasks.md`.

**분해 공식 (고정):**
- phase1 = 환경설정 — 포트(offset→`.env`/`.env.example`/compose)·venv+패키지·
  Docker pull·Dockerfile(+GPU 프로젝트면 Dockerfile-gpu). **작성·준비만, 컨테이너 실행 X**
- phase2 = 프론트엔드 디자인 — module=단순 / project=화려. **무조건 두 번째**
- phase3+ = 개발 — 재료(축3) 벤더링/추출 → glue → 백엔드/로직. **compose 기동은 여기부터**
- 축2=extend 면 기존 트리에 phase append (재번호 금지)

**형식:**
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

**필수 장치 (fail-closed — RULES §7):**
- **역참조 커버리지**: 모든 ckpt 가 spec 라벨(`← F<n>`) 역참조. spec 의 모든
  Feature(supplied 포함) ≥1 ckpt. 기계 검증 실패 = 분해 미완 — segment 진행 X.
- **supplied/to-build 태그**: 재료(modules/extract) 기반 기능은
  `[supplied:<출처>]` 필수. supplied 를 from-scratch 재구현 금지.
- ckpt ID `phaseN.ckptN` 은 **안정적** — segment dispatch 단위, 재번호 금지.

분해 완료 → 사용자에게 트리 표시. **사용자의 segment 지정 = 분해 승인.**

## 3. segment 루프 (CTO — 빌드 본체)

1. 사용자 : `phaseN.ckptN ~ phaseM.ckptM 진행해` (또는 `... autopilot`)
2. CTO : segment 실행. autopilot 이면 `/goal` 설정 —
   조건 = "범위 내 전 ckpt `[✅]` + 검증 증거 제시됨, or stop after N turns".
   증거(테스트 출력)는 반드시 대화에 표면화 (goal 평가자는 transcript 만 읽음).
3. **phase1 끝** → 증거(docker ps·포트·헬스체크) 들고 🤚 게이트1 (환경설정 확인).
4. **phase2 끝** → dev 서버(hot-reload, `FRONTEND_PORT`, `0.0.0.0`) 기동 → 🤚 게이트2
   **라이브 디자인 루프**: 사용자가 브라우저로 보며 수정사항 말함 →
   designer/developer 즉시 수정 → 사용자는 새로고침으로 확인 → 반복 → 승인.
   **compose 로 띄우지 말 것** (수정마다 재기동 비효율 — dev 서버만).
5. segment 완료 시 CTO 판단으로 reviewer 호출(무조건 X) — API 테스트(curl·pytest)·
   DB 무결성(SQL)·코드 평가. 지적 → `[dev]` 수정 → 재검증.
6. CTO → 사용자 "완료" 보고 (검증 증거 포함). reviewer 결과는 **파일 X, 보고 메시지**.
7. 사용자 : 브라우저 실사용 테스트 (🤚 게이트3) → PASS = 다음 segment / FAIL = 재작업.
8. 진행 상태는 `specs/tasks.md` 체크박스만 갱신 (완료 `[✅]`, 미완 `[ ]`, 블로커 `[!]`) — 별도 상태파일 금지. (레거시 `[x]` 도 완료로 인식.)

- `/goal` 은 phase3+ 전용. 게이트1·2 를 goal 로 넘기지 않는다 (RULES §8).
- `[!]` 블로커 → goal 중단 + 사용자 surface. 우회 진행 금지.
- codex 는 빌드 단계 아님 — 사용자가 CEO 창에서 직접 명령할 때만 (RULES §6).

## 4. 모듈 마감 (module 빌드 한정)

마지막 segment + 사용자 브라우저 테스트 통과 후, CTO 가
`modules/<name>/specs/USAGE.md` 를 작성한다:

```markdown
# <모듈명>      # 무엇을 하는 모듈인지 2~3줄
## 기능         # 뭘 제공하나
## 사용법       # 다른 프로젝트에 붙이는 방법
## 환경         # 필요 env, 의존성, 포트
## API          # 노출 엔드포인트/함수
```

**USAGE.md 존재 = 모듈 완성(재사용 가능) 표시.** 없으면 빌드 중 — 다른 plan 이
소비 금지 (RULES §7). 빌드 잔재(plan.md, specs/)는 그대로 둔다 (이력).
README.md 는 작성하지 않는다 (RULES §1 — 사용자 전용).

## 5. 단계·에이전트별 스킬 (고정 = 무조건 / 유동 = 시스템 판단)

### 분해 (planner)
- 고정: `writing-plans`
- +기계 검증: 커버리지 체크 자동 실행
- 유동: `plan-eng-review` / `harness-unknowns-check`

### phase1 환경설정 (developer)
- 고정: `verification-before-completion` — 완료 주장 전 증거 → 게이트1
- 유동: `run` / `investigate` / `careful`

### phase2 프론트 디자인 (designer)
- project 고정 3: `design-consultation`(open-design 디자인시스템 152개에서
  선택/참조) → `design-shotgun`(시안 보드→사용자 선택) → `design-html`(선택된
  open-design tokens.css 사용)
- module 고정 1: `design-html` (+필요시 open-design 시스템 1개 참조)
- 유동: `browse` / `design-review` / `frontend-design` / open-design 스킬들
  (`.sources/open-design/skills/` 디자인 계열)

### phase3+ 개발 (developer)
- 고정: `test-driven-development`(비즈로직, 플러밍 예외는 완료노트 명시) /
  `verify`(완료 보고 전 라이브 앱 실동작 확인)
- 유동: `run` / `systematic-debugging` / `investigate` / `simplify` / `careful`

### reviewer (CTO 판단 호출)
- 고정: `code-review`(1차 high/재리뷰 medium) / `qa-only`(report-only)
- 직접 실행 (스킬 X, 필수 임무): API 테스트(curl·pytest) + DB 무결성(SQL)
- 유동: `health` / `browse`
- 결과 = 파일 X, 보고 메시지

## 6. CTO 세션 표시 의무

- 현재 작업 중인 `phaseN.ckptN` 을 tmux 상태줄/statusline 에 상시 표시.
- 스킬 사용 표시는 `<에이전트> ★ <스킬>` 형식 (예: `developer ★ verify`).
