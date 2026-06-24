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
| Git / 배포 비가역 명령 | `RULES.md` §1 | `hooks/git_guard.py`, `tests/smoke.sh` | 결정론(hook) | |
| 파일시스템 비가역(rm/DROP/볼륨) | `RULES.md` §2 | `hooks/git_guard.py` | 결정론(hook) | |
| 외부 네트워크 / 패키지 설치 | `RULES.md` §3 | CTO·teammate | advisory | |
| 포트 할당(offset) | `RULES.md` §4 | `harness/cli.py`(할당·PORT.md 생성), `run.sh` | 결정론(code) | doctor 검증은 후속 PR(2단계) |
| 환경설정 / Poetry+Docker 병행 | `RULES.md` §5 | developer, `tests/smoke.sh` | advisory | |
| 인박스/메시지 처리(injection 방지) | `RULES.md` §6 | CEO·CTO | advisory | §6 heading 이 `# 6.`(level-1) |
| Codex 독립 검증 정책 | `RULES.md` §6 (Codex carve-out) | `plugins/ceo/role.md` §Codex, `plugins/ceo/commands/codex-review.md`, `plugins/ceo/commands/codex-protocol-review.md`, `codex_review_launch.py`, `codex_protocol_review_launch.py` | advisory + marker | user explicit only |
| 슬래시 `!`-line 인자 injection | `RULES.md` §6.1 | `codex_review_launch.py`, `codex_protocol_review_launch.py`(shell=False) | 부분 결정론 | |
| 모듈 재사용 충실도 | `RULES.md` §7 | CTO·planner | advisory | |
| 모듈 완성기준(self-heal / USAGE) | `plugins/_shared/PROCESS.md`(모듈 마감) | CTO, reviewer | advisory ← 승격후보 | |
| Autopilot(/goal) 경계 | `RULES.md` §8 | CTO | advisory | |
| DB 스키마 = migration 전용 | `RULES.md` §9 | `hooks/git_guard.py`(DROP/TRUNCATE 차단) | 결정론(hook) | |
| 3rd-party / OAuth 통합테스트 | `RULES.md` §10 | developer | advisory | |
| 단회소비 토큰 atomic | `RULES.md` §11 | 빌드 코드 | advisory | |
| 하네스 네임스페이스(teammate↔CTO) | `RULES.md` §12 | OS ns, CTO | advisory | |
| Docker build/compose = 사용자 명시 시만 | `RULES.md` §13 | (없음) | advisory ← 승격후보 | |
| 빌드 lifecycle phase/gate | `plugins/_shared/PROCESS.md` §2-3 | CTO role, planner, reviewer | advisory ← 승격후보 | 게이트 순차·게이트2 전제·상태형 의존 재싱크 포함 |
| Code quality contract | `plugins/_shared/CODE_QUALITY.md` | developer 완료증거, reviewer BLOCKER/SHOULD/NIT, `run.sh doctor` | advisory + doctor anti-drift | 철학문 X; 완료/승인 게이트가 행동을 강제 |
| Task line 포맷 | `plugins/cto/skills/harness-task-format/SKILL.md` | `hooks/team/task_created_format_check.py` | 결정론(hook) | |
| 완료 verification / sentinel | `plugins/cto/rules/agent-team-protocol.md` §Verification Gate | `hooks/team/task_completed_verify_gate.py`; developer/designer/planner = consumer | 결정론(hook) | developer.md 는 role 반복본 |
| Team spawn protocol | `plugins/cto/skills/harness-team-spawn/SKILL.md` | `plugins/cto/commands/start-project.md` | advisory | |
| Agent team 통신 규약 | `plugins/cto/rules/agent-team-protocol.md` | CTO agents | advisory | |
| 사용자 질문 relay | `plugins/cto/skills/harness-relay-qa/SKILL.md` | CTO role, teammates | advisory | |
| idle/무진행 감지 | `harness/daemon.py` | harnessd | 결정론(code) | |
| 역할 컨텍스트 주입 | `hooks/session_start.py` | SessionStart | 결정론(hook) | role+RULES+PROCESS 주입 |
| 세션 lifecycle / tmux UX | `run.sh` | run.sh | 결정론(code) | |
| daemon wake/stall/discovery lifecycle | `harness/daemon.py` | harnessd | 결정론(code) | |

## Known gaps (후속 PR 대상 — 이 PR 에선 수정 안 함)

- **RULES §6 heading level 불일치**: `# 6. 인박스 처리`(L195, level-1) 인데 나머지는 `## N.`(level-2).
  §6 자체는 **존재**하며 `cto/role.md` 의 "RULES §6" 참조도 유효 — 헤더 레벨만 비정규.
  → 번호/레벨 정규화 PR(4단계)에서 `## 6.` 로 통일.
- **advisory ← 승격후보** 표시 항목(§13 docker, PROCESS lifecycle = 게이트 순차·게이트2 전제·
  상태형 재싱크, 모듈 완성기준)은 이번 세션 실증으로 자주 깨짐 → 결정론(hook) 승격 1순위(5단계).
- **doctor 가 아직 이 map 을 검증하지 않음**: doctor 통과 = 기존 검사만 통과. map 구조 검증(경로·
  §N 참조·중복 authority)은 2단계 PR 에서 추가.
