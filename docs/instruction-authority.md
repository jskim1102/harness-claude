# Instruction Authority Map

이 문서는 **규칙 전문이 아니라 authority index** 다. 규칙 내용은 Authority 파일에만 둔다.
여기엔 "어떤 concern 의 정본이 어느 파일인가" 와 "어떻게 강제되는가" 만 적는다.

**원칙**
- map 에 규칙 전문을 쓰지 않는다 (= RULES/PROCESS/map 삼중정본 방지).
- Authority 는 concern 당 **하나**. 추가 파일은 Enforcer/Consumer 또는 Notes 로.
- `Enforcement` = **결정론(hook/code)** 이면 런타임이 보장, **advisory(instruction)** 이면
  모델이 RULES/PROCESS 를 읽고 지켜야 함(= 모델이 까먹으면 깨짐 → 승격 후보).
- 이 map 자체는 색인일 뿐 — 추가/이관/중복제거의 *전제*지, 그 자체로 문제를 해결하지 않는다.

| Concern | Authority (정본) | Enforcer / Consumer | Enforcement | Notes |
| --- | --- | --- | --- | --- |
| Git / 배포 비가역 명령 | `RULES.md` §1 | `hooks/git_guard.py`, `tests/smoke.sh` | 결정론(hook) | Claude(settings.json)+Codex(config.toml) 양쪽 PreToolUse |
| 파일시스템 비가역(rm/DROP/볼륨) | `RULES.md` §2 | `hooks/git_guard.py` | 결정론(hook) | 동 git_guard 가 codex-cto 세션도 커버 |
| 외부 네트워크 / 패키지 설치 | `RULES.md` §3 | CTO·teammate | advisory | |
| 포트 할당(offset) | `RULES.md` §4 | `harness/cli.py`(할당·PORT.md 생성), `run.sh` | 결정론(code) | doctor 검증은 후속 PR(2단계) |
| 환경설정 / venv+Docker 병행 | `RULES.md` §5 | Codex developer, `tests/smoke.sh` | advisory | |
| 웹서버 외부접속 바인딩(0.0.0.0) | `RULES.md` §5.3 | `harness/netbind_scan.py`(`run.sh netbind`), reviewer 필수검사, `tests/smoke.sh` | 결정론(static scan) | reviewer 게이트가 행동 강제 |
| CTO hybrid spawn = 시작 마커 (add-cto 자동 시딩; /start-project 는 수동 재신호) | `plugins/cto/skills/harness-team-spawn/SKILL.md` "When To Spawn" | `run.sh add-cto`(마커 시딩), `start_project_gate.py`(UserPromptSubmit 마커 + PreToolUse:Agent), `start_project_spawn_nudge.py`, `one_teammate_per_role_gate.py`, `tests/smoke.sh` | 결정론(hook) | 2026-08-04 사용자 결정: 첫 지시 턴 = 시작 신호; Codex=별도 세션 |
| reviewer [review] = code-review 스킬 실행 | `reviewer.md` Verification Sentinel | `skill_announce.py`(호출 .invoked 기록) + `task_completed_verify_gate.py`([review] 완료 시 직전리뷰 이후 새 호출 요구), `tests/smoke.sh` | 결정론(hook) | code-review 미실행 시 [review] 완료 차단 (2026-06-24 수동검증-only PASS 사고) |
| 인박스/메시지 처리(injection 방지) | `RULES.md` §6 | `harness/cli.py`(Codex pair 권한), `harness/daemon.py`(role별 wake), `inbox_isolation_guard.py` + `inbox_isolation_clear.py` | 결정론(code/hook) + advisory | Claude/Codex 양쪽 훅; §6 heading 이 `# 6.`(level-1) |
| Codex 독립 검증 정책 | `RULES.md` §6 (Codex carve-out) | `plugins/ceo/role.md` §Codex, `plugins/ceo/commands/codex-review.md`, `plugins/ceo/commands/codex-protocol-review.md`, `codex_review_launch.py`, `codex_protocol_review_launch.py` | advisory + marker | user explicit only |
| 슬래시 `!`-line 인자 injection | `RULES.md` §6.1 | `codex_review_launch.py`, `codex_protocol_review_launch.py`(shell=False) | 부분 결정론 | |
| 모듈 재사용 충실도 | `RULES.md` §7 | CTO·planner | advisory | |
| 모듈 보안 경계(host 책임) | `RULES.md` §7 | `codex_review_launch.py`→`review_runner.py`(`--target-type module`), `reviewer.md` 분류게이트, CEO dispatch 판단 | 부분 결정론(codex 프롬프트 주입) + advisory | host-책임 security=non-blocking; 실 시크릿/키 커밋은 예외(blocking) |
| 모듈 완성기준(self-heal / USAGE) | `plugins/_shared/PROCESS.md`(모듈 마감) | CTO, reviewer | advisory ← 승격후보 | |
| Autopilot(/goal) 경계 | `RULES.md` §8 | CTO | advisory | |
| DB 스키마 = migration 전용 | `RULES.md` §9 | `hooks/git_guard.py`(DROP/TRUNCATE 차단) | 결정론(hook) | |
| 3rd-party / OAuth 통합테스트 | `RULES.md` §10 | Codex developer | advisory | |
| 단회소비 토큰 atomic | `RULES.md` §11 | 빌드 코드 | advisory | |
| 하네스 네임스페이스(teammate↔CTO) | `RULES.md` §12 | OS ns, CTO | advisory | |
| Docker build/compose = 사용자 명시 시만 | `RULES.md` §13 | `hooks/git_guard.py`(`_docker_hits`), `tests/smoke.sh` | 결정론(hook) | build/compose build·`up --build`·bare `up` 차단; service-specific app `compose up` fail-closed(이미지 전용 의존 서비스만 통과) |
| 세션/화면 제어 = Orca only | `RULES.md` §14 | `run.sh`, `harness/orca_runtime.py`, `tests/smoke.sh` | 결정론(code) | exact durable title + live root handle; tab 단위 stop/delete, native split 카운트 |
| 빌드 lifecycle phase/gate | `plugins/_shared/PROCESS.md` §2-3 | CTO role, planner, reviewer | advisory ← 승격후보 | 게이트 순차·게이트2 전제·상태형 의존 재싱크 포함 |
| 크로스플랫폼(.gitattributes eol=lf + Dockerfile CR-strip) | `plugins/_shared/PROCESS.md` phase1 | planner(phase1.ckpt1), Codex developer | advisory | Win autocrlf → 컨테이너 shebang 깨짐 방어(rtsp-streaming 2026-07-16). 셸 entrypoint+Docker 쓰는 전 프로젝트·신규 스캐폴딩 기본 |
| Code quality contract | `plugins/_shared/CODE_QUALITY.md` | `plugins/codex-cto/role.md` 완료증거, reviewer BLOCKER/SHOULD/NIT, `run.sh doctor` | advisory + doctor anti-drift | 철학문 X; 완료/승인 게이트가 행동을 강제 |
| Task line 포맷 | `plugins/cto/skills/harness-task-format/SKILL.md` | `hooks/team/task_created_format_check.py` | 결정론(hook) | |
| 완료 verification / sentinel | `plugins/cto/rules/agent-team-protocol.md` §Verification Gate | `hooks/team/task_completed_verify_gate.py`; Claude teammates = consumer | 결정론(hook) | Codex는 role.md 완료증거 + Claude reviewer 검증 |
| teammate 도구 계약 | `plugins/cto/agents/{planner,designer,reviewer}.md` frontmatter | Claude Code(frontmatter tools/disallowedTools 파싱) | 결정론(런타임) | denylist 방식(2026-07-16 #368, 실 subagent 스폰으로 관찰) — 화이트리스트 미지정=전부 상속(planner/designer), reviewer 만 `disallowedTools: Write, Edit`. **SendMessage 는 상속되나(보고채널 복구), TaskUpdate/TaskList/TaskGet 은 subagent 에 구조적으로 전파 안 됨**(부모엔 있어도 subagent deferred 리스트에 부재 — Agent/ExitPlanMode 부류). ⇒ teammate 의 task claim/완료는 tasks.md 체크박스 Edit + **CTO 가 TaskUpdate 대행**이 유일 경로(우회 아님, 설계). plan 승인은 native plan mode(EnterPlanMode/ExitPlanMode)가 아니라 **SendMessage 왕복**(teammate plan 제출 → CTO `APPROVED`/`REJECTED`, `harness-team-spawn` plan-approval-default) — 그래서 ExitPlanMode/`permissionMode: plan` 은 이 harness 에 불필요, SendMessage 만 있으면 된다 |
| Team spawn protocol | `plugins/cto/skills/harness-team-spawn/SKILL.md` | `start-project.md` + team hooks | advisory + 결정론(hook) | |
| Production code 소유 / Codex handoff | `plugins/codex-cto/role.md` | `run.sh` role env/hooks, `harness/cli.py` pair-only send, `harness/daemon.py` wake, `PROCESS.md` segment loop | 결정론(transport) + advisory(승인) | same-name inbox transport; inbox 다음 user turn에서만 실행 |
| Agent team 통신 규약 | `plugins/cto/rules/agent-team-protocol.md` | CTO agents | advisory | |
| 사용자 질문 relay | `plugins/cto/skills/harness-relay-qa/SKILL.md` | CTO role, teammates | advisory | |
| idle/무진행 감지 | `harness/daemon.py` | harnessd | 결정론(code) | Claude-anchor project stall + Claude/Codex pair half 유실(30초 grace, CEO surface) |
| 역할 컨텍스트 주입 | Claude=`hooks/session_start.py`; Codex=`plugins/codex-cto/role.md` | SessionStart; `run.sh` `HARNESS_ROLE` + `-c developer_instructions` | 결정론(code/hook) | |
| Project/terminal lifecycle / Orca UX | `run.sh` | `run.sh`, `harness/orca_runtime.py` | 결정론(code) | 빌드 dir=Project; add가 Claude+Codex tab 준비, stop은 Project 보존, delete는 경로 검증 후 등록 제거 |
| daemon wake/stall/discovery lifecycle | `harness/daemon.py` | harnessd | 결정론(code) | Claude=`/inbox`; Codex=고정 untrusted-inbox 읽기 prompt |

## Known gaps (후속 PR 대상 — 이 PR 에선 수정 안 함)

- **RULES §6 heading level 불일치**: `# 6. 인박스 처리`(L195, level-1) 인데 나머지는 `## N.`(level-2).
  §6 자체는 **존재**하며 `cto/role.md` 의 "RULES §6" 참조도 유효 — 헤더 레벨만 비정규.
  → 번호/레벨 정규화 PR(4단계)에서 `## 6.` 로 통일.
- **advisory ← 승격후보** 표시 항목(PROCESS lifecycle = 게이트 순차·게이트2 전제·
  상태형 재싱크, 모듈 완성기준)은 이번 세션 실증으로 자주 깨짐 → 결정론(hook) 승격 1순위(5단계).
- **doctor 가 아직 이 map 을 검증하지 않음**: doctor 통과 = 기존 검사만 통과. map 구조 검증(경로·
  §N 참조·중복 authority)은 2단계 PR 에서 추가.
