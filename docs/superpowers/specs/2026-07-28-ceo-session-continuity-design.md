# CEO 세션 연속성 — 원인 추적 + 조치 (2026-07-28)

## 증상

2026-07-27(월) 저녁까지 대화하던 CEO 세션이, 2026-07-28(화) 아침에 보니 사라져
있었다. 사용자는 종료한 적이 없다. `./run.sh ceo` 로 다시 띄우면 **빈 대화**로
시작해 전날 맥락이 전부 날아갔다.

원래 tmux 를 쓰던 이유가 정확히 이것이었다 — 터미널을 실수로 닫거나 오류로 죽거나
주말이 지나 다시 출근해도 CEO/CTO 대화가 이어지는 것. Orca 로 대체한 뒤 그게 깨졌다.

## 조사에서 확정된 사실

- 서버는 재부팅되지 않았다 (`system boot 2026-07-23 13:03`, 연속 가동).
- `orca-harness.service` 는 4일 연속 active. Orca 크래시 아님.
- 대시보드·harnessd 는 터미널을 죽이는 코드 경로가 없다 (grep 0건 + 접근 로그 0건).
- 자동 pruner 는 타이머가 없고 Orca 종료 상태에서만 도는 수동 도구다.
- Orca `daemon.log` 의 CEO pty 수명 기록:

  | 생성 | 소멸 |
  |---|---|
  | 07-24 02:07 | 07-24 16:17 |
  | 07-25 15:15 | 07-27 16:29 (주말 이틀 생존) |
  | 07-27 16:29 | 07-28 09:35 |

  밤/새벽 자연사는 한 건도 없다. 소멸은 전부 낮 사용자 활동 시간대다.

## 확정하지 못한 것 — 그리고 그 이유

**죽는 순간의 기록이 어디에도 없다.**

| 소스 | 결과 |
|---|---|
| Orca `daemon.log` | 07-27 20:28 ~ 07-28 09:34 이벤트 0건 |
| `journalctl --user` | 같은 구간 18줄, 전부 무관 |
| OOM / segfault | 0건 |
| core dump | `coredumpctl` 미설치 → 수집 자체가 안 됨 |
| 터미널 출력 로그 | Orca 가 세션 수거 시 `terminal-history/<ptyId>/` 를 통째 삭제 |

09:35 의 `session-killed`/`session-exited(code=129)` 는 Orca 가 그 시점에 **수거하며**
찍은 기록이라, 이것으로 사인을 역산할 수 없다. 없는 증거를 추정으로 메우지 않는다.

## 조사 중 발견한 실제 결함 — harnessd 폴링 폭주

`orca` CLI 는 호출마다 AppImage(Electron) 를 새로 마운트해서 뜬다. 실측:

```
orca terminal list  (CLI)   706.4 ms
terminal.list       (RPC)     0.4 ms   ← 1,600x
```

harnessd 는 `POLL_INTERVAL_SEC = 1.0` 으로 돌며 매 틱 터미널 목록을 읽었고,
그 경로가 CLI 였다. 결과:

- 시간당 ~3,000회, 하루 ~72,000회 Electron 기동 (journal 의 `mount_orca` 이벤트로 실측)
- harnessd 서비스 누적: **CPU 3d 10h / 메모리 피크 11.2GB** (uptime 4d 20h 기준 = 코어 0.7개 상시)

CEO 사망과의 인과는 **입증되지 않았다** (fd·메모리 누수는 관측되지 않음). 다만 밤새
유일하게 벌어지고 있던 일이고, pty 를 소유한 데몬을 하루 7만 번 두드리는 구조는
그 자체로 결함이라 고친다.

## 조치

### 1. 폴링 경로를 CLI → 런타임 소켓 RPC 로

- `harness/orca_runtime.py::_rpc_terminal_records()` — `orca_rpc.call("terminal.list")`.
  실패하면 기존 CLI 경로로 그대로 폴백한다.
- `ORCA_CLI_COMMAND` / `ORCA_DEV_REPO_ROOT` 가 설정돼 있으면 RPC 를 쓰지 않는다.
  스텁 CLI 를 우회해 실 런타임을 읽으면 스모크가 거짓말을 한다.
- `harness/cli.py::_alive_sessions()` 가 자체적으로 `orca terminal list` 를 직접
  띄우던 두 번째 경로도 `orca_runtime.terminals()` 로 합쳤다.

**검증:** 조치 후 90초간 Electron 기동 **0회** (전 ~75회). harnessd RSS 111MB → 15.9MB.

### 2. CEO 사망 계측 (다음 번엔 사인을 잡는다)

`harness/daemon.py::watch_ceo()` — 매 틱(이제 공짜) CEO pty 생존을 확인하고,
사라진 순간 `~/.harness-claude/ceo-death/<timestamp>/` 에 스냅샷을 굳힌다.

답해야 할 질문은 하나다: **프로세스가 먼저 죽었나, 탭만 사라졌나.**

- `summary.json` — `verdict`: `process-gone` (claude 프로세스 사망) 또는
  `orphan-pty` (프로세스 생존, 탭/세션만 유실). pid 는 Orca `daemon.log` 의
  `session-created` 에서 역산하고, 소멸 시점에 `/proc/<pid>` 로 판정한다.
- `orca-daemon.log.tail`, `ps.txt`, 그리고 **Orca 가 지우기 전에 복사한
  `terminal-history/`** (claude 가 스택을 뱉고 죽었다면 여기 남는다).

두 원인은 대응이 정반대다 — 전자는 claude 크래시, 후자는 Orca 워크스페이스 상태 유실.

### 3. 대화 복원 — `--resume`, `stop-ceo` 의미는 보존

pty 가 죽어도 트랜스크립트는 디스크에 남는다. 세션 id 만 알면 그대로 잇는다.

- `hooks/session_start.py` — `HARNESS_ROLE=ceo` 면 훅 payload 의 `session_id` 를
  `~/.harness-claude/ceo-session.id` 에 기록. resume 로 뜬 세션도 id 가 같아 그대로 유지.
- `run.sh::_ceo_resume_args()` — 그 id 로 `--resume` 을 붙인다.
- `run.sh::cmd_stop_ceo()` — id 파일을 삭제한다. **`stop-ceo` = 기억 소멸** 이라는
  기존 의미가 그대로 유지되고, `ceo --fresh` 는 stop-ceo 를 타므로 자동으로 새 대화가 된다.

**함정 (실측):** 존재하지 않는 세션 id 로 `--resume` 하면 claude 가
`No conversation found with session ID` 로 **exit 1** 한다. `exec` 로 띄우므로
터미널이 그대로 죽는다. 그래서 트랜스크립트 파일이 실재할 때만 플래그를 붙인다.

| 상황 | 결과 |
|---|---|
| pty 가 밤새 소멸 / 재부팅 / 탭 실수로 닫음 | `./run.sh ceo` → 이전 대화 복원 |
| `./run.sh stop-ceo` | id 삭제 → 다음 ceo 는 새 대화 (의도된 초기화) |
| id 는 있는데 트랜스크립트가 없음 | note 출력 후 새 대화 (터미널 즉사 방지) |

## 검증

- `tests/smoke.sh` **384 PASS / 0 FAIL** — 신규 4건:
  resume 인자 3분기 · stop-ceo id 삭제 · 훅 id 기록(CTO 미기록) · 사망 verdict + 동초 충돌 보존
- `./run.sh doctor` **ALL CLEAN**
- harnessd 재기동 후 로그: `CEO 감시 시작 pty=…@@8ffea50a pid=1830908`

## 확장: CTO 복원 (같은 날 후속)

CEO 와 같은 사망 클래스라 CTO 도 잇는다. `stop-cto` 는 stop-ceo 와 의미가 다르다 —
"세션만 정지, add-cto 로 재개" 전제. 그래서 id 파일 수명이 다르다:

| | 기록 | 복원 | id 폐기 |
|---|---|---|---|
| CEO | 훅 → `ceo-session.id` | `claude --resume` | `stop-ceo` (기억 소멸) |
| CTO lead | 훅 → `cto-session-<name>.id` | `orca claude-teams --resume` (passthrough 실측 OK) | `delete-cto` 만 (stop-cto 는 유지) |
| Codex | 기록 불필요 | `codex resume <id>` — `~/.codex/sessions` meta 의 `cwd==빌드dir` 로 발굴 | (파일 없음) |

- **팀원(planner/designer/reviewer)은 구조적으로 복원 불가** — 별도 세션.
  lead 만 잇고, 팀은 `/start-project` 재spawn. add-cto 가 복원 시 이를 안내한다.
- 훅 기록은 lead 만 한다 — 팀원 프로세스는 `HARNESS_ROLE` 을 상속받지 않음을
  실측으로 확인 (HARNESS_ROOT 만 존재). 이름은 파일명이 되므로 kebab-case
  화이트리스트 밖이면 기록 거부 (경로 조작 방지).
- **codex 는 `resume --last` 금지** — 전역 최신이라 CTO 여럿이면 남의 세션을
  물어온다. cwd 정확 매칭 + **`.git` birth 가드**: 빌드 dir 의 `.git` 생성시각보다
  오래된 세션은 무시 (delete-cto 후 같은 이름 재생성 시 옛 빌드 대화 오염 방지).
  부작용: git init 도입(07-23) 이전의 기존 codex 세션은 복원 대상에서 빠진다 —
  fail-safe 방향이라 수용 (실측: rtsp-detection 07-21 세션이 그렇게 걸러짐).

## 남은 것

- **`coredumpctl` 미설치** — 네이티브 크래시면 지금도 증거가 안 남는다.
  설치에 sudo 가 필요하다 (`systemd-coredump`).
- 사망 계측(watch_ceo)은 CEO 전용 — CTO pty 도 감시하려면 role 별 일반화 필요.
