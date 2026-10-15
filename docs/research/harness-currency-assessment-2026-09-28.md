2026-09-28 하네스 최신성 평가

현재 하네스는 **부분적으로 out-of-date**다. 실행기 전체가 뒤처진 상태는 아니지만, 지원이 끝난 대시보드 의존성, Orca–Codex 버전 조합, 오래된 지시문과 승인 흐름을 정리할 필요가 있다. 프로젝트 관리·복구·검증 기반을 보존하면서 이 부분을 고치는 것이 우선이다. 전면 재작성이나 특정 모델로의 일괄 전환을 정당화할 비교 실험은 없다.

버전·호환성과 설계·운영을 같은 비중으로 평가했다. 기준은 `74f1207` 위의 현재 작업 트리다. 시작 시 이미 tracked 파일 24개와 기존 `docs/research/` 자료에 작업 내용이 있었으며 그대로 유지했다. 이번 작업은 소스·공식 문서 조사, 기존 검사 실행, 이 보고서와 증거 파일 작성이다. 패키지 설치·업데이트·서비스 재시작·실제 에이전트 작업 발주는 수행하지 않았다. `RULES.md` 원문은 외부 개발자 가이드의 경계에 따라 분석 대상으로 읽지 않았고, 역할 문서·authority map·enforcer를 확인했다.

버전과 의존성을 비교하면 다음과 같다. 설치 버전은 CLI 출력, 프론트 버전은 lockfile, 최신 버전은 공식 릴리스·공식 문서와 배포 레지스트리를 대조했다.

| 대상 | 현재 관측 | 2026-09-28 비교 기준 | 판단 |
|---|---|---|---|
| Claude Code | 2.1.283 | 2.1.283 | 최신. CLI 자체의 노후화가 주된 문제는 아님 |
| Codex CLI | 0.157.1 (사용자 지적 후 재확인) | 0.157.1, 09-26 릴리스 | 최신. Orca와 조합 검증은 별도 |
| Orca CLI | 1.4.198 | 1.4.215, 09-27 릴리스 | 업데이트 후보. Codex 0.157+ 시작 문제 수정이 1.4.212에 포함 |
| Vite | 5.4.21 | 최신 8.3.1; 공식 지원 범위에서 5.x 제외 | 명확한 유지보수 우선순위 |
| React / React DOM | 18.3.1 | 19.3.0 | 이전 major. 버전 차이만으로 장애·취약성을 단정하지 않음 |
| Claude 역할 기본 모델 | CEO/CTO 생성 설정에 `claude-opus-5`; planner/reviewer는 `opus` 별칭 | 현재 모델군에 Opus 5.5·Fable 5.1·Sonnet 5 | 고정 ID와 이동하는 별칭이 혼재. 역할별 실제 모델 기록 필요 |
| Codex 모델 | developer는 사용자 설정 상속; 두 독립 리뷰 실행기는 기본 `gpt-5.5` | Codex 0.157.0에 GPT-6 Sol/Luna 지원 추가 | 모델 설정이 분산됨. 오래된 기본값과 의도적 고정을 구분해야 함 |
| Dashboard backend | `fastapi`, `uvicorn[standard]`, 버전 제약 없음 | 재설치할 때 해석되는 버전이 달라질 수 있음 | 노후 여부보다 재현성 문제. 설치 버전의 최신성은 이번에 판정하지 않음 |

Claude 최신 버전과 prompt-audit 추가는 [공식 changelog](https://raw.githubusercontent.com/anthropics/claude-code/main/CHANGELOG.md), Codex 버전·모델·background-server 변경은 [공식 changelog](https://learn.chatgpt.com/docs/changelog), Orca 최신 버전은 [1.4.215 릴리스](https://github.com/stablyai/orca/releases/tag/v1.4.215), 프론트 지원 상태는 [Vite 지원 정책](https://vite.dev/releases)과 [React 버전 문서](https://react.dev/versions), Claude 모델군은 [공식 모델 목록](https://platform.claude.com/docs/en/models/overview)에 근거한다. 정확한 npm 버전 조회 결과는 [증거 파일](harness-currency-evidence-2026-09-28.json)에 기록했다.

로컬 모델 설정 근거는 [run.sh](../../run.sh)의 `write_role_settings`, [code-review 실행기](../../plugins/codex-review/scripts/review_runner.py)의 `DEFAULT_MODEL`, [protocol-review 실행기](../../plugins/codex-protocol-review/scripts/review_runner.py)의 `DEFAULT_MODEL`이다. 이는 시작 설정의 확인이다. 기존 세션의 실제 모델, 계정별 접근 가능 모델, 새 모델의 품질 우월성을 검증한 것은 아니다.

사용자 지적 후 같은 실행 경로를 다시 확인한 결과, `codex --version`과 설치된 `@openai/codex/package.json`이 모두 **0.157.1**이었다. 최초 조사에서는 0.155.1이 관측됐지만 현재 Codex 업데이트 권고는 철회한다. 기존 검사 결과는 최초 조사 시점의 결과이며 이 재확인에서 다시 실행하지 않았다. 실행 중인 기존 세션의 바이너리 버전까지 확인한 것은 아니다.

남은 항목은 Orca와의 조합 검증이다. Orca 1.4.212는 **Orca 관리 home에서 Codex 0.157+가 `SUN_LEN` 오류로 시작하지 못하는 문제**를 수정했다. 현재 Codex는 이미 0.157.1이므로 Orca 업데이트 검토와 역할 세션 시작·복구 확인을 권한다. 이 환경에서 해당 오류를 직접 재현한 것은 아니다. [Orca 공식 수정 내역](https://github.com/stablyai/orca/releases/tag/v1.4.212)

대시보드는 실제 유지보수 항목이 발견됐다. `npm audit --package-lock-only --ignore-scripts --json` 결과는 **high 4개·moderate 2개 패키지 항목**이다. 대상은 `vite`, `postcss`, `nanoid`, `browserslist`, `esbuild`, `baseline-browser-mapping`이다. 이는 여섯 개의 독립 CVE나 현재 서버에서 여섯 가지 공격이 가능하다는 뜻은 아니다. 여러 advisory와 전이 의존성이 집계되고 Windows 전용 조건도 포함된다.

현재 [dashboard 기동 코드](../../run.sh)는 `npm run dev`를 실행하고, [Vite 설정](../../dashboard/frontend/vite.config.js)은 `host: '0.0.0.0'`이다. Vite의 `.map` 경로 문제는 네트워크에 노출된 개발 서버와 예측 가능한 민감한 `.map` 파일이라는 조건을 명시한다. 첫 조건에 해당하는 설정은 확인했지만, 실제 민감 파일 존재·외부 접근성·악용은 검사하지 않았다. 개발 의존성이라는 이유로 낮은 우선순위로 볼 수는 없다. 지원되는 Vite 및 플러그인 조합으로 이동하고, 상시 대시보드를 정적 빌드로 서비스할지 검토할 가치가 있다. [Vite 공식 advisory](https://github.com/vitejs/vite/security/advisories/GHSA-4w7w-66w2-5vf9)

설계·운영에서의 판단은 다음과 같다. '구현 확인'과 '개선 가설'을 구분해야 한다.

| 항목 | 현재 근거 | 판단과 개선 방향 |
|---|---|---|
| 승인·인계 흐름 | Codex role은 inbox를 읽고 멈춘 뒤 다음 사용자 턴의 명시 승인을 요구. lead는 production 구현을 금지 | 명시적인 설계 비용. 같은 승인 범위가 lead→developer로 전달될 때 사람이 다시 개입해야 함. 승인 범위를 기계적으로 보존하거나 작업 소유자를 합치는 실험 후보 |
| 상태 관측 | `orca_runtime.role_idle()`은 terminal preview의 `Working`, `Permission`, `esc to interrupt` 등 문자열로 busy 판정 | 공식 구조화 이벤트와 비교하면 취약한 연동 방식. Codex부터 상태 이벤트 어댑터를 검토 |
| 지시문 정합 | CEO는 부팅 포트 confirm에 회신해야 한다고 지시하지만 CTO는 08-20에 왕복 폐지라고 설명 | 현재 작업본에 남아 있는 명시적 충돌. 모델 교체보다 먼저 정리할 대상 |
| 팀 구성 정합 | protocol은 항상 planner+reviewer 두 명; spawn skill은 기존 tasks가 있으면 reviewer 한 명 | 재개 작업의 기대 행동이 다름. 정본을 정하고 소비자 문서를 맞춰야 함 |
| Claude 내부 계약 의존 | idle hook이 `team_name`과 `~/.claude/tasks/<team>/`를 직접 사용 | 공식적으로 폐기 예정인 필드에 의존. 누락 시 nudge가 조용히 생략될 수 있음. 실제 현 버전 장애로 확정하지는 않음 |
| 역할·컨텍스트 로딩 | lead는 시작 마커가 있으면 질문의 성격과 무관하게 팀 spawn을 먼저 요구. SessionStart에서 공통 규칙·역할·PROCESS 주입 | 필요 시 역할을 호출하고 단계별 지시를 로드하는 실험 후보. 토큰 절감률은 미측정 |
| 평가·운영 지표 | doctor/smoke는 존재. 역할별 비용·승인 대기·재작업을 한 작업 단위로 연결하는 계측은 확인하지 못함 | 역할 분리와 새 모델이 실제로 이득인지 판정할 근거가 부족. 전면 전환 전에 계측 필요 |

승인·인계의 근거는 [Codex 역할](../../plugins/codex-cto/role.md)의 `Before Any Work`와 `Paired Inbox`, [inbox 격리 훅](../../hooks/inbox_isolation_guard.py)이다. inbox 본문을 신뢰할 수 있는 사용자 명령으로 승격시키는 변경을 권하는 것이 아니다. 대안은 **사용자가 승인한 scope와 수신자·유효 범위·완료 조건을 별도 상태로 관리**하고, 메시지는 그 승인 범위 안의 자료로 취급하는 것이다. 정책 변경이므로 현행 경계와 동등한 통제가 입증되어야 한다.

상태 관측의 근거는 [Orca runtime](../../harness/orca_runtime.py)의 `role_idle`과 [daemon](../../harness/daemon.py)의 idle 확인 루프다. daemon에는 이미 짧은 오판을 줄이는 연속 idle 확인이 있으므로 완전히 무방비한 구현은 아니다. 다만 Codex App Server는 `thread/status/changed`, `turn/completed`, `thread/tokenUsage/updated`를 제공한다. 이를 쓰면 화면 문구를 추정하는 의존성을 줄일 수 있다는 것이 개선 가설이다. 현재 Orca 터미널 세션에 이 이벤트 경로를 연결하고 기존 승인·복구·UI를 유지하는 작업은 별도로 필요하다. [공식 App Server 문서](https://learn.chatgpt.com/docs/app-server)

문서 충돌은 [CEO role](../../plugins/ceo/role.md)의 포트 confirm 절, [CTO role](../../plugins/cto/role.md)의 부팅 self-check 절, [team protocol](../../plugins/cto/rules/agent-team-protocol.md)의 Team Composition, [spawn skill](../../plugins/cto/skills/harness-team-spawn/SKILL.md)의 Standard Spawn에서 현재도 확인된다. 09-21 평가를 그대로 인용한 것이 아니라 현재 파일을 다시 확인했다. 단순한 테스트 성공으로 의미 충돌이 없어졌다고 볼 수 없다.

Claude 호환성은 일괄적으로 낡았다고 판정하면 안 된다. 이 하네스는 이미 `TeamCreate` 대신 `Agent` spawn과 session 기반 team naming을 반영했다. TaskCreated/TaskCompleted도 현재 공식 hook에 존재한다. 다만 공식 문서는 세 이벤트의 `team_name`을 폐기 예정으로 표시하고 있고, [idle hook](../../hooks/team/teammate_idle_workcheck.py)은 이 값이 없으면 allow 처리한다. 완료 증거 경로는 [공통 hook 코드](../../hooks/team/team_hook_common.py)에서 project 기준과 레거시 폴백으로 완화되어 있다. 따라서 '모든 팀 훅이 깨졌다'가 아니라 **남은 내부 계약 의존성의 호환성 부채**다. [Claude hooks 문서](https://code.claude.com/docs/en/hooks)

내장 멀티에이전트 기능만으로 하네스의 가치가 사라진 것도 아니다. Codex는 사용자 요청이나 프로젝트 지시에 따라 subagent를 호출할 수 있지만, Claude Agent Teams와 동일한 task store나 복구 의미를 제공한다고 가정할 수 없다. Claude의 in-process teammates는 여전히 session resume으로 복원되지 않는다고 공식 문서에 적혀 있다. 모델·도구가 좋아졌다는 이유로 프로젝트 간 SQLite 큐, exact terminal 식별, 세션 복구와 재스폰 코드를 일괄 제거해서는 안 된다. [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents), [Claude Agent Teams 한계](https://code.claude.com/docs/en/agent-teams#limitations)

유지할 핵심은 프로젝트·모듈 경계, 포트와 실행 환경 관리, 내구성 있는 메시지 큐, 세션 복구, 실제 동작 검증, 독립 리뷰다. 작은 작업까지 모든 역할과 승인 왕복을 동일하게 적용해야 하는지는 별도의 문제다. 상주 프로세스가 있다는 사실만으로 계속 토큰을 쓴다고 계산하거나, 역할 수가 줄면 품질이 유지된다고 가정해서도 안 된다.

검증 결과와 한계는 다음과 같다.

| 검사 | 결과 | 해석 |
|---|---|---|
| `./run.sh doctor` | exit 0, ALL CLEAN | 현재 결정론 검사 통과. 탭 없는 에이전트 프로세스 3개 advisory 경고는 존재 |
| `./run.sh smoke` | PASS 531 / FAIL 0 | 현행 계약과 fixture 검사 통과. 새 CLI 조합의 실제 세션 E2E 검증은 아님 |
| npm audit, lockfile 기준 | high 4 / moderate 2 / critical 0 | 의존성 경고 확인. 실제 악용 가능성은 미검증 |
| 설치·공식 릴리스 비교 | Claude 최신; 재확인한 Codex도 최신; Orca 및 프론트 차이 확인 | 실행 중인 모든 세션의 모델·binary provenance까지 확인한 것은 아님 |
| 동일 과제 비교 실험 | 미실행 | 역할 통합·모델 변경의 비용/속도/품질 효과를 수치로 단정할 수 없음 |

doctor의 고아 경고 대상은 `bulk-receipe-v2`의 lead/developer/designer다. 실행 중 작업이나 토큰 소비 여부는 이번에 측정하지 않았고, 프로세스를 종료하지 않았다. 기존 09-21 문서에도 비슷한 관측이 있지만 동일 PID의 지속 생존 여부까지 대조하지 않았다. 또한 AGENTS.md의 386개 smoke 수는 과거 기준일의 숫자이며 현재 실행 결과는 531개다.

권장 순서는 다음과 같다.

1. **지원·호환성 정비:** Vite와 관련 의존성 갱신, Orca 업데이트 및 이미 설치된 Codex 0.157.1과의 조합 검증, backend 재현 가능한 버전 기록. Orca 업그레이드 시 terminal identity·resume·hook 설치를 실제 fixture 프로젝트에서 확인한다.
2. **지시문과 계약 정리:** 포트 confirm·재개 팀 구성 충돌 해소, `team_name` 없는 payload와 task store 의존성 점검, CLI 조합·모델 설정을 doctor에서 관측할 수 있게 한다. Claude 2.1.283의 `/doctor prompt-audit`도 보조 수단 후보이며 이번에 실행하지 않았다.
3. **작은 운영 실험:** 기존 방식과 '작업 소유자 1명 + 필요 시 planner/designer + 독립 reviewer'를 같은 과제로 비교한다. 현행 방식 유지하되 승인 범위 재사용만 바꾸는 안도 비교 대상으로 둔다. 어느 안도 아직 기본값으로 권고하지 않는다.
4. **측정 후 제어층 개선:** 사용자 개입 수, 승인 대기시간, 전체 완료시간, 실제 모델·사용량, 재작업과 누락 결함을 수집한다. Codex 구조화 이벤트를 먼저 연결하고, 중복 제어 코드 제거는 동작 동등성이 확인된 부분에 한정한다.

이번 판단에서 가장 확실한 업데이트 대상은 **대시보드 의존성과 Orca**이며, Codex CLI는 재확인 결과 최신이다. 설계 측면에서 가장 먼저 손댈 부분은 **충돌하는 지시문과 승인·인계의 중복**이다. 최신 모델로 바꾸는 작업은 이 두 문제의 해결을 대신하지 못한다.

재현용 관측과 검사 출력은 [증거 JSON](harness-currency-evidence-2026-09-28.json)에 함께 저장했다. 기존 [09-21 단순화 평가](harness-simplification-assessment-2026-09-21.md)와 [Astra 평가](astra-harness-assessment.md)는 배경 자료이며, 이번 최신 버전·advisory 판단은 새로 조회한 자료에 근거한다.
