# AGENTS.md — harness-claude

외부 AI 코딩 에이전트(Codex / Cursor / Copilot / 기타)가 이 저장소의 **코드를
개발**할 때 읽는 가이드.

> **⚠ RULES.md 와 혼동 금지.** `plugins/_shared/RULES.md` 는 이 하네스가
> *런타임에 자기 CEO/CTO 에이전트에게 SessionStart 훅으로 주입*하는 운영 하드룰
> (포트 할당·인박스 처리·에이전트 역할)이다 — 외부 도구는 그걸 읽지 않는다.
> 이 `AGENTS.md` 는 정반대: *외부 AI 가 이 repo 를 개발할 때* 의 가이드다.
> RULES.md 의 운영규칙을 AGENTS.md 로 옮기지 말 것.

## 무엇인가

다중 에이전트 하네스. CEO 1명 + N명의 CTO 가 SQLite 메시지큐로 협업한다. CEO 는
사용자 셸에 직결, 각 CTO 는 백그라운드 tmux 세션에서 4-teammate Agent Team
(planner / designer / developer / reviewer)을 지휘해 프로젝트를 빌드한다.

- 스택: Python 3.10+ (`harness` CLI/daemon) + Bash (`run.sh`) + Markdown (에이전트
  정의·스킬·프로세스 스펙).
- **핵심**: 이 repo 의 "코드" 대부분은 실행 로직이 아니라 **에이전트에게 주는
  instruction(markdown)** 이다. 버그는 보통 로직 오류가 아니라 *지시의 모순·누락*
  이다. 여러 파일(role.md ↔ SKILL.md ↔ PROCESS.md)의 정합을 항상 확인하라.

## 구조

| 경로 | 역할 |
|---|---|
| `harness/` | Python CLI + daemon (`harness` 명령, SQLite 메시지큐) |
| `run.sh` | 진입점 — `ceo` / `add-cto` / `attach` / `down` / `fetch` 등 (Bash) |
| `hooks/` | Claude Code 훅 — `session_start.py`(role.md+RULES.md+PROCESS.md 주입), `team/`(태스크 형식·검증·idle 가드) |
| `plugins/ceo/`, `plugins/cto/` | CEO/CTO 의 `role.md` + commands + agents + skills |
| `plugins/_shared/` | `RULES.md`(런타임 주입 하드룰) · `PROCESS.md`(빌드 프로세스 스펙) |
| `plugins/codex-review/` | cross-model Codex 리뷰 — `AGENT.md`(리뷰어 정의) + `scripts/review_runner.py` |
| `docs/` | 설계 스펙·문서 |
| `claude-project/`, `modules/`, `.sources/` | 빌드 dir (프로젝트/모듈) · extract 소스 (`.gitignore` 참조) |

## 실행 / 테스트

```bash
./run.sh ceo                                  # CEO 시작 (현재 셸을 claude 로 교체)
./run.sh add-cto <빌드dir>/plan.md             # CTO 추가 (claude-project/<n>/plan.md | modules/<n>/plan.md)
./run.sh attach cto-<name>                    # CTO 화면 접속 (observe 폐기 — 터미널 독립)
./run.sh test-cto <name> "<prompt>"           # CTO 비대화형 스모크
./run.sh down                                 # 전체 종료 (+dev서버/워커 프로세스 정리)
```

- **검증 3계층** (plans/harness.md "시스템 점검"):
  1. `./run.sh doctor` — 정합 검사 (금지토큰/참조무결성/문법/버전). **하네스 수정 후 무조건.**
  2. `./run.sh smoke` — 결정론 스모크 30+ (`tests/smoke.sh`)
  3. `/harness-audit` — 의미 감사 (6 perspective + adversarial verify, 큰 개편 후)
  - cross-model: codex consult/review — 사용자 판단 시
- 새 코드는 doctor+smoke 로 검증하고, 큰 변경은 3·cross-model 로 교차검증하라.
- 의존성: `pyproject.toml` (`harness = harness.cli:main`). 표준 라이브러리 위주.

## 컨벤션

- **포트**: 하드코딩 금지. `.env` 의 `PORT_OFFSET` / `BACKEND_PORT` / `FRONTEND_PORT`
  참조. `.env` 는 커밋하지 않고 `.env.example` 만 올린다. (RULES.md §4)
- **태스크 라인 형식**: `tasks.md` 의 task 는 `[role] verb | files | acceptance.
  Run: cmd` — `TaskCreated` 훅이 강제한다. 위반 시 자동 rollback.
  (`plugins/cto/skills/harness-task-format/`)
- **에이전트 정의 수정**: `role.md` / `SKILL.md` / `PROCESS.md` 는 서로 참조하므로
  한 곳을 바꾸면 정합을 맞춰라. 빌드 흐름의 정본 = `plans/harness.md`,
  운영 추출본 = PROCESS.md (CTO 주입).
- **슬래시 `!`-line 인자**: `$0`/`$1`/`$ARGUMENTS` 는 파싱 전 bash 에 raw-splice
  되므로 in-line quoting 은 완전한 방어가 아니다. 신뢰불가 인자는 `shell=False`
  헬퍼(`codex_review_launch.py` 참고)로 통과시키고 절대 bare-interpolate 하지 마라.
  (RULES.md §6.1)
- **마크다운**: 한영 혼용 (이 repo 는 한국어 기반). 코드·명령·경로·API 명은 영어.

## 경계 (사용자 명시 전 금지)

- **Git**: `git commit` / `push` / `init` / `reset --hard` / `rebase` 등은 사용자가
  명시할 때만. (RULES.md §1)
- **파괴적 명령**: `rm -rf`, DB `DROP`/`TRUNCATE`, 패키지 설치는 사용자 컨펌 필요.
  (RULES.md §2·§3)
- **런타임 생성물**: `claude-project/<cto>/`, `.sources/`, `~/.harness-claude/`,
  `.git/info/exclude`(런타임이 자동 생성) 는 수동 편집 X.
- **RULES.md / PROCESS.md**: 시스템 동작의 권위 소스. 수정은 신중 + 정합 검증 +
  `/codex-review` 권장.
