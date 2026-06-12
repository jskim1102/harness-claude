# harness-claude

다중 에이전트 하네스. CEO 한 명 + N 명의 CTO 가 메시지큐로 협업.
빌드 흐름의 정본: `plans/harness.md`.

## 정신모델

- **claude** = 프로세스 (CEO 또는 CTO 한 명의 두뇌)
- **tmux**   = 컨테이너 (CTO 전용 — CEO 는 사용자 셸에서 직결)
- **CEO/CTO 터미널은 항상 독립 운영** (observe 폐기)

CEO 는 항상 사용자 터미널에 직결로 돈다. CTO 들만 백그라운드 tmux 에서 돈다 —
사용자 부재중에도 작업이 진행되고, 보고는 inbox `[N]` 메시지로 쌓인다.

**모듈 vs 프로젝트** — 빌드는 두 종류다:
- **모듈** (`modules/<name>/`) = 여러 프로젝트에 재사용되는 기능 단위. 프론트 단순.
  완성 표시 = `specs/USAGE.md`.
- **프로젝트** (`claude-project/<name>/`) = 실사용 상용 서비스. 프론트 디자인 중요.

## 사전 준비

repo 밖 도구라 각자 설치해야 한다:

- **claude** — Claude Code CLI ≥ 2.1.139 (Agent Teams + `/goal` autopilot)
- **python3** ≥ 3.10 — 데몬 + 훅
- **tmux** — CTO 세션 컨테이너
- **sqlite3** — 메시지큐 DB

플러그인/스킬은 이 repo 의 `plugins/` 에 들어있다 (clone 에 포함).

## 설치

```bash
git clone <repo-url> harness-claude
cd harness-claude
pip install -e .          # harness CLI 설치 (run.sh 가 ports/inbox 등에 사용)
```

설정 파일(`*/.claude/`)은 **커밋되지 않는다** — `./run.sh` 가 실행 시 자동 생성한다.

> **시작은 반드시 `./run.sh` 경유.** run.sh 가 `HARNESS_ROOT` 를 박아
> 슬래시명령·에이전트가 경로를 해석한다.

## 빌드 흐름 (3단계)

```bash
# 1단계 — CEO 가 plan.md 작성
./run.sh ceo                      # CEO 시작 (현재 셸을 claude 로 교체)
#   CEO 채팅에서:
#   /build-project <brief>        # 프로젝트 빌드 plan
#   /build-module <brief>         # 모듈 빌드 plan
#   → CEO 가 사용자와 정렬 후 <빌드dir>/plan.md 1개 작성

# 2단계 — CTO 스폰 + 분해 (새 터미널)
./run.sh add-cto claude-project/<name>/plan.md    # 프로젝트
./run.sh add-cto modules/<name>/plan.md           # 모듈
#   plan.md 경로가 유일 인자 — 부모 dir=빌드타입, dir명=CTO 이름.
#   plan.md 없으면 스폰 실패 (1단계 선행 강제).
#   CTO 가 자동으로 specs/spec.md + specs/tasks.md (phase→ckpt 트리) 분해.
./run.sh attach cto-<name>        # CTO 화면 접속 (detach: Ctrl+B d)

# 3단계 — segment 개발 (CTO 채팅에서)
#   "phase1.ckpt1 ~ phase2.ckpt2 진행해"        # segment 지정
#   "phase3.ckpt1 ~ phase5.ckpt2 autopilot"     # /goal 기반 자동 진행 (phase3+ 만)
#   게이트: ①환경설정 확인 ②라이브 디자인 루프 승인 ③segment 마다 브라우저 테스트
```

phase1=환경설정, phase2=프론트 디자인(dev 서버 hot-reload — compose 는 phase3부터),
phase3+=개발. codex 교차리뷰는 **사용자가 원할 때만** CEO 창에서 `/codex-review <name>`.

## 조회 / 점검

```bash
./run.sh ls                   # 세션 목록
./run.sh ports                # 포트 레지스트리 (docs/PORT.md)
harness status                # CTO 별 현재 ckpt + 진행률
./run.sh doctor               # 정합 검사 — 하네스 파일 수정 후 무조건
./run.sh smoke                # 결정론 스모크 30+ (tests/smoke.sh)
```

## 비대화형 스모크 테스트

```bash
./run.sh test-cto <name> [--max-turns N] "<prompt>"
```

`claude --print` 로 한 방 호출. 기본 N=10 턴. 실 작업 X — 빠른 검증용.

## 종료 / 삭제

```bash
./run.sh down                 # 전 세션 kill + CTO 가 띄운 dev서버/워커 프로세스 정리
./run.sh delete-cto <name>    # CTO 완전 삭제 (세션+프로세스+dir+sqlite+로그+포트반환)
./run.sh delete-cto --all     # 전체 CTO 삭제 (modules/ 의 완성 모듈은 보호)
```

CEO 는 down 으로 안 죽는다 — 사용자 셸이므로 터미널을 닫거나 `/quit`.
`delete-cto ceo` 는 차단된다 (CEO 디렉토리는 삭제 대상이 아님).

## extract 소스 가져오기

```bash
./run.sh fetch <git-url>      # .sources/ 에 shallow clone (plan 의 extract 재료용)
```

## 완전 초기화

```bash
./run.sh down
rm -rf claude-project modules .sources
rm -rf ~/.harness-claude
```
