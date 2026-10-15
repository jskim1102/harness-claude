# CEO/CTO 역할 재분할 — 개발은 CTO 전담, CEO 는 하네스·검토 (2026-10-13)

상태: **보류** — 2026-10-13 사용자: "너무 큰 작업이 될 거 같아, 나중에 생각해보자".
D1(새 빌드 시작 방법) 검토 중 중단. 재개 시 아래 "결정 필요" D1 부터. 구현 착수 X.

## 배경

사용자 제안 (2026-10-13): CEO 가 하던 1~4 번 — ① plan.md 작성 ② CTO 띄우기 안내
③ 인박스 처리 ④ 사용자 지시 전달 — 을 없애거나 CTO 에 넘긴다. "프로젝트 개발은 CTO
가 전부 전담, CEO 는 대시보드·하네스 관리 + CTO 가 개발을 끝내면 검토만."

- 2026-08-20 다이어트(CEO = 호출형 게이트 + 하네스 정비공)의 연장이다. 그때 남겼던
  "CEO 의 plan.md 작성"을 이번에 CTO 로 넘긴다.
- 지금 구조의 비용: CEO 와 나눈 계획 대화가 `plan.md` 한 장으로만 CTO 에 전달돼
  맥락이 빠진다. ③④ 는 08-20 이후 사용자↔CTO 직접 대화 + 대시보드로 거의 안 쓰인다.

## 최종 구조

| 역할 | 지금 | 바뀐 뒤 |
|---|---|---|
| CEO | plan.md 작성 · CTO 띄우기 안내 · 인박스 · 지시 전달 · 하네스 정비 · Codex 리뷰 | **하네스 정비(대시보드 포함) · 완료 빌드 검토(부를 때) · Codex 리뷰(부를 때) · 하네스 문제 신고 처리** |
| CTO lead | plan.md 읽기 → 분해 → 개발 | **계획(plan.md 작성·확정)** → 분해 → 개발 |
| 사용자 | CEO 와 계획 → add-cto → CTO 에 지시 | 새 빌드 생성 → CTO 와 계획부터 완료까지 → (원하면) CEO 에 검토 요청 |

planner·reviewer·designer-cto·codex-cto 의 역할은 그대로다.

## 새 흐름

1. **새 빌드 생성** — `./run.sh add-cto claude-project/<name>` (모듈은
   `modules/<name>`). 경로 형으로 **없는 폴더**를 주면 새 빌드로 만들고 CTO 를
   띄운다. kebab-case·양쪽 중복 검사는 지금 규칙 그대로. (D1)
2. **계획 (CTO)** — 첫 턴에 무엇을 만들지 묻고, 지금 `/build-project`·`/build-module`
   절차를 그대로 한다: brainstorming(축2 target·축3 source) → Library Check
   (fail-closed, RULES §7) → 재료 분석(understand-anything, git 소스는 `run.sh fetch`)
   → `plan.md` 작성(같은 템플릿 — 대시보드·lineage 스캐너가 `## 1` 을 읽는다) →
   plan-ceo-review → **"plan.md 확정할까요?"**
3. **확정** — 사용자 승인 답 → `plan.md` 잠금 + 팀(planner·reviewer) 스폰 신호 +
   카메라 포트 배선(`plan.md` 에 mediamtx 가 있을 때만). (D2)
4. **분해·개발** — 지금과 같다 (PROCESS §2~).
5. **계획 변경** — CTO 가 이유와 함께 **"plan.md 수정할까요?"** → 승인 → 잠금 해제
   → 수정 → 다시 "확정할까요?".
6. **완료 후 검토 (선택)** — 사용자가 CEO 에 "X 검토해" → `/review-build X`. (D3)

## plan.md 잠금 — `plan_readonly_gate` → `plan_lock_gate`

지금은 CTO 쪽 `plan.md` 쓰기를 무조건 막는다(만들다 보면 계획을 결과에 맞춰 고치는
문제). CTO 가 계획을 쓰게 되므로 **"초안일 때만 쓰기 허용, 확정 후 잠금"**으로 바꾼다.

- 상태 = 초안 마커 유무: `~/.claude/logs/plan-draft/<name>.draft`
  - 있으면 **초안** — CTO lead 가 Write/Edit/MultiEdit 가능
  - 없으면 **잠금** — 지금처럼 차단. **기존 빌드는 마커가 없으니 그대로 잠금 (이관 0)**
- 마커를 만드는 곳: 새 빌드 `add-cto`, "plan.md 수정할까요?" 승인
- 마커를 지우는 곳: "plan.md 확정할까요?" 승인
- 승인 판정은 reviewer 스폰 질문(2026-10-06)과 같은 장치 — 사용자 프롬프트(모델이 못
  꾸밈) + 직전 CTO 메시지의 질문. 판정 함수(`_approves`·`_last_assistant_text`)는
  `team_hook_common.py` 로 옮겨 공유.
- 초안이어도 쓸 수 있는 건 **lead 만** — planner·reviewer(`/subagents/`)·designer-cto
  는 계속 차단.

## 같이 바뀌는 것

- **카메라 포트 배선 시점**: `add-cto` 때 → `plan.md` 확정 때. `_wire_project_env` 는
  지금 `add-cto` 시점에 `plan.md` 의 mediamtx 문구를 보는데, 새 빌드는 그때 plan 이
  없다. 확정 시점에서 부를 수 있게 분리하고 **멱등**하게(이미 4줄 있으면 안 씀).
- **팀 스폰 시점 (새 빌드만)**: `add-cto` 의 시작 마커 시드 대신 확정 때 시작 마커.
  기존 빌드는 지금처럼 `add-cto` 가 시드.
- **CTO → CEO 메시지 (`/msg-ceo`)**: 하네스 문제 신고 전용(훅·게이트 오작동, 규칙
  충돌). 프로젝트 질문·블로커는 CTO 터미널에서 사용자에게 직접. (D5)
- **CEO `/msg-cto`**: "사용자 지시 중계" 의무 삭제. 명령은 검토 후속·하네스 공지용으로
  남긴다(사용자 승인 시).
- **CEO 커맨드**: `/build-project`·`/build-module` 삭제(절차는 CTO 스킬
  `harness-plan` 으로 이전), `/review-build` 신설.
- **CEO role.md 잔재 정리**: "포트 충돌 조율(CTO 포트 confirm)" 절 삭제 — 08-20 에
  RULES §4.0 에서 폐지된 절차.

## `/review-build <name>` (D3)

CEO 가 부를 때만 한다. 빌드를 고치지 않고 판정과 보완 목록만 낸다.

1. `plan.md` 의 Goal·Requirements 대비 결과 — `specs/tasks.md` 의 `[✅]`/`[❓]`/`[ ]` 집계
2. 검증 흔적 — reviewer 판정 항목, 게이트 통과 여부
3. 실제 동작 — 서버가 떠 있으면 핵심 화면 1회 확인 (사용자 요청 시)
4. 실사용 위험 — `/codex-review <name>` 을 **제안** (승인 시 실행)
5. 결과 = 통과 / 보완 목록. 보완 전달(`/msg-cto`)은 사용자 승인 후.

## 구현 인벤토리

| 파일 | 변경 |
|---|---|
| `run.sh` | `add-cto` 경로 형 새 빌드 생성(+초안 마커, 시작 마커 시드 생략), `_build_ready` 분기, `_wire_project_env` 확정 시점 재사용·멱등 |
| `hooks/team/plan_readonly_gate.py` → `plan_lock_gate.py` | 초안/잠금 판정 + 확정·수정 질문 승인(UserPromptSubmit). settings 템플릿에 UserPromptSubmit 배선 추가 |
| `hooks/team/team_hook_common.py` | 승인 판정 공유 (`start_project_gate` 에서 이동) |
| `plugins/cto/skills/harness-plan/` (신규) | `/build-project`·`/build-module` 절차 이관 (project/module 차이 포함) |
| `plugins/cto/role.md` | 정체성(계획 포함)·부팅 시퀀스(계획 단계 분기)·`plan.md` 규칙(잠금)·`/msg-ceo` 범위 |
| `plugins/cto/commands/msg-ceo.md` | 하네스 문제 신고 전용 |
| `plugins/_shared/PROCESS.md` | §0 계획 단계 추가 |
| `plugins/_shared/RULES.md` | `plan.md` 주체("CEO 발주서" → CTO 계획서), Library Check 주체, 카메라 판별 시점 |
| `plugins/ceo/role.md` | 하는 일 재작성(하네스·대시보드·검토), 포트 confirm 절 삭제 |
| `plugins/ceo/commands/` | `build-project.md`·`build-module.md` 삭제, `review-build.md` 신설 |
| `hooks/session_start.py` | CEO/CTO 주입 문구 정합 |
| `hooks/git_guard.py` | (D4 채택 시) 잠긴 `plan.md` 의 Bash 쓰기 차단 |
| `docs/instruction-authority.md` | 계획 작성·잠금·검토 행 |
| `tests/smoke.sh` | 아래 Acceptance 를 케이스로 |

## Acceptance

- 새 빌드: `add-cto claude-project/<new>` → 폴더 생성 + 초안 마커, 시작 마커 없음 →
  CTO 가 계획 질문으로 시작 → `plan.md` 작성 → "확정할까요?" → "응" → 잠금 + 시작
  마커(팀 스폰)
- 잠금 후 CTO lead 의 `plan.md` Write/Edit 차단, "수정할까요?" 승인 뒤에만 가능
- 초안이어도 planner·reviewer·designer 는 차단
- 다른 질문에 한 "응"·거절·옛 질문은 확정/수정으로 인정 안 함
- 카메라 프로젝트: 확정 때 mediamtx 4줄 1회 (재확정해도 중복 없음)
- 기존 빌드: 동작 변화 없음 (잠금 유지, `add-cto` 시드 유지)
- CEO: 계획 커맨드 없음, `/review-build` 동작, role.md 하는 일 = 하네스·대시보드·검토
- `./run.sh doctor` CLEAN, `./run.sh smoke` 전부 통과 (기존 bulk-receipe-v2 netbind 제외)

## 결정 필요 (★ = 추천)

| # | 질문 | 기존 방식 | ★A (추천) | B |
|---|---|---|---|---|
| D1 | 새 빌드 시작 방법 | CEO 창 `/build-project`·`/build-module` → CEO 가 폴더+`plan.md` 작성 → 사용자가 `./run.sh add-cto <name>` (`plan.md` 없으면 거부) | `./run.sh add-cto claude-project/<name>` — 없는 폴더면 새 빌드 생성 + CTO 기동, 계획은 CTO (새 명령 없음) | A + 대시보드 "새 빌드" 버튼 |
| D2 | 새 빌드의 planner·reviewer 스폰 시점 | `add-cto` 가 시작 마커를 미리 심음 → CTO 첫 턴에 바로 스폰 (`plan.md` 가 이미 있으니까) | 새 빌드는 `plan.md` 확정 때 스폰 (기존 빌드는 지금처럼 첫 턴) | 새 빌드도 첫 턴에 스폰 (계획 끝날 때까지 대기) |
| D3 | CEO 검토 방식 | 정해진 검토 없음 — 08-20 에 CEO 최종 리뷰 폐지, 부르면 그때그때 판단 + 실사용 위험은 `/codex-review` | `/review-build <name>` — plan 대비 결과·검증 흔적·실제 동작 확인 + `/codex-review` 제안 → 통과/보완 목록 | 기존과 같음 (부를 때 자유 검토) |
| D4 | Bash 로 `plan.md` 쓰는 우회 | CTO 쪽 Claude 세션의 Write/Edit/MultiEdit 만 차단, Bash(`cat > plan.md`)·Codex 는 열려 있음 | git_guard 에 "잠긴 `plan.md` Bash 쓰기 차단" 추가 | 기존과 같음 (열어 둠) |
| D5 | CTO → CEO 메시지 (`/msg-ceo`) | 블로커·질문 에스컬레이션 전용 (08-20 부터 완료 보고 폐지), CEO 는 인박스를 매 턴 최우선 처리 | 하네스 문제 신고 전용 — 프로젝트 질문·블로커는 CTO 가 사용자에게 직접 | 완전 폐지 |

## 비목표

- 진행 중 빌드의 `plan.md` 재작성 (기존 그대로 잠금)
- CEO 상시 감시·완료 자동 보고 부활 — 08-20 폐지 유지, 검토는 부를 때만
- Codex 세션의 `plan.md` 편집 차단 — Codex 는 Claude 훅 밖 (D4 는 Bash 경로만)

## 위험

- **계획한 쪽이 개발도 한다** → 독립 검토가 약해진다. 완화: 확정은 사용자 승인 필수
  (결정론) + plan-ceo-review + 확정 후 잠금.
- **CTO 의 전체 시야(모듈 재사용·파생 관계)가 CEO 보다 좁다.** 완화: Library Check
  fail-closed 유지, extract 파생은 계획 단계에서 원본 폴더를 직접 읽어 확인.
- **CTO 세션 컨텍스트 증가** (계획 대화 포함). 수용.
