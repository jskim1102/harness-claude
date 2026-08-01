# Designer 독립 직군화 + Claude Design 미세조정 루프 (2026-07-29)

## 배경

phase2 디자인에서 사용자의 병목 = designer 초안에 대한 **세밀 수정/수정요청이
어렵다** (말로 설명해야 함). 또한 designer 를 codex 처럼 대등한 독립 직군으로
두고 사용자가 직접 대화하고 싶다는 요구 (2026-07-29 사용자 확정: "codex 처럼
대등한 직군, 내가 직접 대화" + "Claude Design 은 총괄이 아니라 세밀 수정 도구").

Claude Design (Anthropic Labs, 2026-04 출시·2.0): 캔버스 직접 조작(드래그·
리사이즈)·인라인 코멘트·챗 3종 편집, MCP 서버로 Claude Code 세션과 연동
(`/design-login` 1회 — 사용자 완료), export = standalone HTML·zip·Handoff to
Claude Code. 독립 터미널 세션이어야 인터랙티브 MCP 인증이 가능 — 분리 결정과
시너지.

## 최종 구조 (잠금)

```
사용자 ─┬─ CEO
        ├─ CTO lead (cto:<name>) ── Agent Team: planner · reviewer (in-process 2명)
        ├─ codex-cto:<name>     developer (기존 그대로)
        └─ designer-cto:<name>  Claude 독립 세션 (NEW, 사용자 직접 대화 가능)
```

- CTO↔designer 통신 = same-name harness inbox (codex 패턴 미러).
- 팀 내 `SendMessage(designer)` 는 게이트 차단 + `harness send --to
  designer-cto:<name>` 안내 (developer 차단과 동일 패턴).
- rail = **3단** (skill ½ / planner ¼ / reviewer ¼). skill 피드 필터는
  `[cto:<name>]` + `[designer-cto:<name>]` 둘 다.

## phase2 워크플로우 (역할 계약)

1. CTO 가 inbox 로 designer 발주 (또는 사용자가 designer 탭에서 직접 지시).
2. designer 초안 제작 (DESIGN.md + 시안) → Claude Design 에 push (MCP) →
   사용자에게 캔버스 링크 제시.
3. **사용자 미세조정 게이트**: 캔버스에서 드래그·리사이즈·인라인 코멘트로 수정.
   Claude Design 은 이 단계의 도구일 뿐 — 총괄 아님.
4. 사용자 확정 → designer 가 Handoff/HTML export 를 받아 DESIGN.md·구현계약에
   정합 반영, tasks.md `[design]` 체크 직접 Edit, CTO 에 완료보고(inbox) →
   CTO 가 codex 발주.
5. production frontend/backend 소스 작성 금지는 유지 (구현 = codex 전담).

## 구현 인벤토리

| # | 영역 | 변경 |
|---|---|---|
| 1 | run.sh | `_start_designer_cto_session` (codex 미러: keeper `cto-<name>-designer`, id 파일 `cto-designer-session-<name>.id`, `_claude_resume_args`, `HARNESS_ROLE=designer-cto:<name>`, 순수 claude skip-permissions) · add-cto 에서 3번째 탭 생성 · `_orca_close_cto` keeper 추가 · fresh(=id rm + cto↔designer msg purge 확장) · delete-cto id rm · rail 3단 + skill grep 확장 · usage |
| 2 | harness/orca_runtime.py | `_TITLE_RE` 에 designer member 추가 + `designer-cto:<name>` role 해석 (codex-cto 매핑 미러) |
| 3 | harness/cli.py | 송신 라우팅: `cto:<name> ↔ designer-cto:<name>` 페어 허용 + role 검증 확장 |
| 4 | harness/daemon.py | designer-cto 인박스 nudge (codex nudge 미러) |
| 5 | hooks/session_start.py | designer-cto role 의 id 파일 기록 + `plugins/designer-cto/role.md` 주입 (role_dir 파싱은 기존 generic) |
| 6 | plugins/designer-cto/role.md | 신설 — 위 워크플로우 계약 + inbox 프로토콜 + Claude Design MCP 사용 |
| 7 | plugins/cto/agents/designer.md | tombstone (developer.md 방식) + run.sh 설치 필터 제외 |
| 8 | hooks/team/* | one_teammate_per_role_gate: designer spawn 차단 · sendmessage_recipient_gate: designer 수신 차단(안내 문구)+TEAMMATES={planner,reviewer} · start_project_spawn_nudge roster 2명 |
| 9 | harness-team-spawn SKILL/spawn-prompt/plan-approval | 2-teammate 로 개정, designer 는 독립 세션 안내 |
| 10 | PROCESS.md / agent-teams-mapping.md | phase2 = inbox 발주 + Claude Design 게이트 |
| 11 | dashboard backend/frontend | 3자 판정 (claude+codex+designer), 표시문구 |
| 12 | tests/smoke.sh + doctor | designer 터미널/keeper/fresh/게이트 핀, agents 파일 검사 갱신 |

## Acceptance

1. `add-cto <name>`: 탭 3개 (lead/codex/designer), designer 세션에 role.md 주입.
2. `harness send --from cto:<n> --to designer-cto:<n>` 성공 + 역방향 성공 +
   비페어(designer-cto:a → cto:b) 거부.
3. 팀 스폰 = planner+reviewer 2명, Agent(designer)/SendMessage(designer) 차단.
4. rail 3단 + designer 스킬활동이 skill 피드에 표시.
5. stop/fresh/delete 가 designer 포함 (fresh = designer 대화 리셋 + 페어 msg 삭제).
6. 대시보드 시작/정지 = 3자, 셋 다 떠야 ready.
7. doctor CLEAN + smoke 전 케이스 그린 (prune 4 제외 — 사용자 WIP).
8. 라이브: 유휴 CTO 1개로 add-cto→3탭→inbox 왕복→stop 실증.

## 비목표

기존 활성 CTO 마이그레이션(다음 재기동부터), 대시보드 designer 인박스 열람 UI,
Claude Design handoff 포맷 자동 파싱(첫 실사용 때 검증), designer 모델 강제.
