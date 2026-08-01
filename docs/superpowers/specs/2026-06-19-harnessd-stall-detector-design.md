# harnessd autopilot stall 감지기 — 설계

> **Historical design record.** 이 문서는 2026-06-19 당시의 tmux 기반 설계를
> 기록한다. 현재 세션/화면 lifecycle은 `run.sh`와 `harness/orca_runtime.py`의
> Orca Project/terminal 모델이 정본이며, 아래 tmux 명령·가정은 운영 지침이 아니다.

## 배경 / 문제

CTO rtsp-streaming v2 빌드 중 사고(inbox #33): autopilot(`/goal`) dispatch 후
developer/designer 가 plan 안 쓰고 idle (파일변경 0, team task STORE 0). CTO 는
dispatch 했다는 사실만으로 "구동 중" 보고. **사용자가 직접 "진행중?" 물어서야
멈춘 것 발견.** 안 물었으면 무진행 방치.

근본 = 무진행을 자동 감지하는 안전장치 부재. 기존 `TeammateIdle` 훅은
CTO-dispatch 된 team task STORE(`~/.claude/tasks/<team>/`)만 보므로, dispatch 가
STORE 에 안 들어간 무진행은 못 잡는다 (훅을 `tasks.md` 로 넓히면 미dispatch 미래
phase 로 잘못 nudge → segment 1개씩 게이팅 깨짐 = 회귀, 그래서 금지).

advisory 문서 규칙(PROCESS §3 "진행 보고도 검증 필수")은 이미 추가했으나, 사고
원인 자체가 "CTO 가 할 일 안 함" 이라 같은 모델-준수에 다시 의존. **결정론 감지기**가
필요하다.

## 목표

`harnessd` (1초 폴링 Python 데몬, 토큰 0) 가 활성 CTO 세션의 silent stall 을
결정론으로 감지해 **CEO 인박스에 surface** 한다. 사용자가 물어봐서야 발견하는 일이
없게 한다.

## 비목표

- CTO pane 자동 nudge — 채택 안 함(surface-only). 세션 비침습.
- `/goal` 활성 상태 감지 — 불가(상태파일 없음). 대신 4신호 조합으로 대체.
- teammate 개별 추적 — 데몬은 tmux 세션 레벨만 본다.
- 훅을 `tasks.md` 로 확장 — 금지(segment 게이팅 회귀).

## 핵심 통찰 — false-positive 구분

"느리지만 작동 중" vs "진짜 stall" 을 4신호 AND 로 분리:

| 케이스 | 신호 | 판정 |
|---|---|---|
| 빌드 작동 중 (docker build/npm ci/test) | pane BUSY ("esc to interrupt"/실행중 명령) | 알림 X |
| 게이트에서 사용자 대기 (정상) | CTO 가 직전 surface 메시지 보냄 (outbound msg 있음) | 알림 X |
| 빌드 완료 | tasks.md 미완 `[ ]` 0개 | 알림 X |
| **silent stall (사고)** | idle + 파일변경 0 + 미surface + tasks 미완, 5분 지속 | **알림 O** |

게이트 대기와 stall 의 결정적 구분 = **outbound surface 유무** (사고 시그니처 =
"surface 안 함"). 전부 데몬이 이미 가진 primitive 로 결정론 계산.

## 아키텍처

`harness/daemon.py` 의 main 루프에 `detect_stalls()` 추가 (discover_ctos / reap /
tick 옆에서 매 폴링 호출).

### 감지 로직 (활성 CTO 세션마다)

활성 세션 = `_list_cto_sessions()`. 각각:

1. **빌드 미완?** `_session_cwd(session)` → `specs/tasks.md` 파싱.
   미완(`[ ]`/`[!]`) 개수 > 0 인지. 0 이면 완료 → state 클리어, skip.
2. **pane idle?** `_pane_idle(session)`. BUSY 면 작동 중 → `last_progress_ts=now`,
   skip.
3. **무진행?** idle 일 때만, 30초 스로틀로 `find <cwd> -mmin -5`
   (`.venv`/`node_modules`/`.git`/`dist`/`__pycache__` 제외) → 최근 변경 있으면
   `last_progress_ts=now`.
4. **미surface?** msg 테이블: `from_role='cto:<name>' AND ts > now-STALL_SEC` 행이
   있으면 → 소통 중 → skip.

→ 4개 충족 + `now - last_progress_ts ≥ STALL_SEC(300)` = **STALL**.

### 동작 (surface-only)

CEO 인박스에 `[system]` 메시지 INSERT:

```
[system] cto:<name> 무진행 의심
  5분간 pane idle + 파일변경 0 + surface 없음. tasks.md 미완 <K>개.
  다음 미완: <첫 [ ] 줄>
  의도된 대기면 무시. 아니면 확인:
    ./run.sh attach cto-<name>
```

INSERT → 기존 wake 로직이 CEO 깨움(/inbox) = 의도한 surface 경로.

### 상태 / 안전

- 모듈 레벨 `_stall_state: dict[session] = {last_progress_ts, last_scan_ts, alert_count, next_alert_ts}`.
- **dedup**: 미읽음 stall 알림이 이미 있으면 재INSERT 금지 (`_ceo_already_notified` 식
  msg 테이블 LIKE 조회). 세션 죽거나 진행 재개(빌드 완료/파일변경) 시 state +
  미읽음 알림 정리.
- **backoff 재알림**: 무응답 지속 시 5→10→20분 지수 (`next_alert_ts` 더블링,
  기존 wake backoff 패턴). 진행 재개 시 리셋.
- **fail-open**: per-session try/except. 에러 = 그 세션 skip, 데몬 안 죽음. 모든
  subprocess timeout=2s (기존 `TMUX_TIMEOUT_SEC` 준수).
- **부하**: per-tick 은 싼 것만 — pane capture(`_pane_idle` 이미 호출), tasks.md
  mtime/파싱. `find` 스캔은 idle 일 때 30초 스로틀(`last_scan_ts`).

## 상수

```python
STALL_SEC = 300.0              # 무진행 임계
STALL_SCAN_THROTTLE_SEC = 30.0 # find 진행스캔 스로틀
STALL_BACKOFF_MAX_SEC = 1200.0 # 재알림 backoff 상한 (20분)
PAIR_DEGRADED_GRACE_SEC = 30.0 # hybrid half 유실 확정 유예
STALL_EXCLUDE_DIRS = (".venv", "node_modules", ".git", "dist", "__pycache__")
```

## Hybrid CTO pair-liveness 확장

Claude CTO(`cto-<name>`)와 Codex developer(`codex-cto-<name>`)가 한 프로젝트를
이루므로, 일반 project stall과 별도로 pair 상태를 감시한다.

- 상태: `healthy`, `claude-only`, `codex-only`, `both-down`.
- `claude-only`/`codex-only` + `tasks.md` 미완이 30초 지속되면 CEO에 누락 half를
  특정해 한 번 알린다. 미읽음 DB 행으로 daemon 재시작 후에도 dedup한다.
- recovery, `both-down`, tasks 완료 시 미읽음 pair 경고를 읽음 처리한다.
- partial 상태에서는 같은 프로젝트의 일반 Claude-anchor stall을 억제해 이중 경고를
  막는다.
- `_list_cto_sessions()`는 기존 `cto-<name>` 계약을 유지한다. Codex 세션을 여기에
  섞으면 이름 파싱과 동일 프로젝트 이중 판정이 깨지므로 `_discover_roles()` 결과를
  조합하는 별도 pair detector를 사용한다.
- 이 확장은 **half 유실/종료** 감지다. tmux 세션은 살아 있지만 Codex 프로세스가
  내부적으로 멎은 경우까지 판정하지 않는다.

## 테스트 (결정론)

신호 계산을 순수함수로 분리해 `tests/smoke.sh` 에 케이스 추가:

- `_parse_tasks_incomplete(text) -> int` — `[ ]`/`[!]` 카운트, `[✅]`/`[x]` 제외.
  - 미완 있는 tasks.md → >0
  - 전부 `[✅]` → 0
- `_stall_verdict(signals) -> bool` — (idle, has_progress, has_surface,
  incomplete, elapsed) 입력 결정론.
  - busy → False
  - idle+미완+미surface+무진행+5분초과 → True
  - 완료 → False
  - surface 있음 → False
- `_pair_status(claude_alive, codex_alive) -> str` — 4상태 전이.
- pair lifecycle — grace 전 무알림, grace 후 1회, restart dedup, recovery 정리,
  반대 half 유실, 완료 시 정리, 일반 stall 억제.

## 영향 파일

- `harness/daemon.py` — project stall + hybrid pair-liveness detector.
- `tests/smoke.sh` — 순수함수 및 pair lifecycle 결정론 케이스.
- 문서: `PROCESS.md`/`role.md` 의 advisory 규칙은 이미 추가됨 (이 감지기가 그
  결정론 백업).
