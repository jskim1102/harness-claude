# CEO/CTO 역할 재분할 — 계획(plan.md)은 CTO 가 쓴다 (2026-10-13 초안 → 2026-10-15 확정)

상태: **확정·착수** (2026-10-15 사용자 결정). 구현 계획 =
`docs/superpowers/plans/2026-10-15-plan-authoring-to-cto.md`.

이력: 2026-10-13 초안은 "새 빌드 시작 방법(D1)" 에서 보류됐다. 2026-10-15 사용자가
아래 흐름으로 확정했다 — 초안의 D1-A(`add-cto` 가 폴더까지 생성) 대신 **CEO 탭이 빈
폴더만 만들고** add-cto 는 그대로 쓴다.

## 배경

지금은 CEO 가 `/build-project <brief>` 로 사용자와 brainstorming 해 `plan.md` 를 쓰고,
CTO 는 그 한 장만 받아 분해한다. 계획 대화의 맥락이 CTO 에 전달되지 않는다. 08-20
다이어트(CEO = 호출형 게이트 + 하네스 정비공)의 연장으로, 계획 작성을 CTO 로 옮긴다.

## 확정 흐름

1. **CEO 탭** `/build-project <name>` 또는 `/build-module <name>` — 하는 일은 이름
   검사(kebab-case, `claude-project/`·`modules/` 양쪽에 없음) + **빈 폴더 생성**뿐.
   brainstorming X, plan.md X. 끝나면 다음 명령을 안내한다.
2. `./run.sh add-cto <name>` — 폴더가 있고 `plan.md` 도 `specs/tasks.md` 도 없으면
   **새 빌드(계획 단계)** 로 띄운다: 초안 마커를 심고, 팀 스폰(시작) 마커는 **안**
   심는다. 폴더가 없으면 지금처럼 거부(오타 방지). `ceo` 는 거부.
3. `./run.sh attach-cto <name>` → 첫 메시지가 곧 brief. "시작" 만 쳐도 CTO 가
   "무엇을 만들까요?" 로 묻는다.
4. **CTO 계획 단계** (스킬 `harness-plan`): brainstorming(축2 target · 축3 source) →
   Library Check(fail-closed, RULES §7) → 재료 분석(understand-anything, git 소스는
   `./run.sh fetch`) → `plan.md` 작성(같은 템플릿 — 대시보드·lineage 스캐너가 `## 1`
   을 읽는다) → plan-ceo-review → **"plan.md 확정할까요?"** 로 턴 종료.
5. 사용자 승인 답 → 훅(`plan_readonly_gate` UserPromptSubmit)이 판정 → **잠금**(초안
   마커 삭제) + **시작 마커**(팀 스폰) + **카메라 포트 배선**(plan.md 에 mediamtx 가
   있을 때만, 멱등). 여기부터 지금과 같다 (PROCESS §2 분해 → segment 루프).
6. **계획 변경** — CTO 가 이유와 함께 **"plan.md 수정할까요?"** → 승인 → 초안 마커
   재생성(잠금 해제) → 수정 → 다시 "확정할까요?".
7. **기존 프로젝트 늘리기** — CEO 탭을 거치지 않는다. 그 CTO 탭에서 직접 말한다.

## 판정 규칙 (결정론, 기존 빌드 이관 0)

| 상태 | add-cto | plan.md 쓰기 (CTO lead) | 팀 스폰 |
|---|---|---|---|
| 폴더 없음 | 거부 | — | — |
| 폴더 있음 · plan.md X · tasks.md X | 새 빌드: 초안 마커 생성, 시작 마커 X | 허용 | 마커 없음 → 차단 |
| 초안 마커 있음 (계획 중 재스폰) | 시작 마커 X | 허용 | 차단 |
| plan.md 있음 · 초안 마커 없음 (기존 빌드) | 지금과 같음 (시작 마커 시딩) | 차단 | 첫 턴 |

- 잠금 = 초안 마커 없음. 마커 위치 `~/.claude/logs/plan-draft/<name>.draft`.
  기존 빌드는 마커가 없으니 자동으로 잠금 (이관 작업 없음).
- 초안이어도 쓸 수 있는 건 **lead 만** (`HARNESS_ROLE=cto:<name>` 이 path 의 이름과
  같고 transcript 가 `/subagents/` 아님). planner·reviewer·designer-cto 는 차단.
- 승인 판정 = reviewer 스폰 질문(2026-10-06)과 같은 장치: 사용자 프롬프트(모델이 못
  꾸밈) + 직전 CTO 메시지의 질문. 다른 질문에 한 "응"·옛 질문은 무효. 판정 함수는
  `team_hook_common.py` 로 옮겨 두 게이트가 공유한다.
- 확정은 `plan.md` 가 실존할 때만 성립한다.

## 같이 바뀌는 것

- **카메라 포트 배선 시점**: `_wire_project_env` 를 멱등으로(이미 `MEDIAMTX_API_PORT`
  있으면 안 씀) 바꾸고, add-cto(기존 빌드)와 확정 훅(새 빌드) 둘 다에서 부른다.
  훅은 `run.sh` 를 source 해 같은 함수를 쓴다 — 구현 둘로 갈라지지 않는다.
- **팀 스폰 시점 (새 빌드만)**: 확정 때 시작 마커. 기존 빌드는 add-cto 시딩 그대로.
- **CTO → CEO 메시지 (`/msg-ceo`)**: 하네스 문제 신고 전용 (훅·게이트 오작동, 규칙
  충돌). 프로젝트 질문·블로커는 CTO 터미널에서 사용자에게 직접.
- **CEO `/msg-cto`**: "사용자 지시 중계" 의무 삭제. 사용자가 굳이 CEO 창에서 시킬 때의
  보조 통로로만 남는다.
- **CEO 커맨드**: `/build-project`·`/build-module` 은 폴더 생성 전용으로 축소. 트리거
  문구("프로젝트 만들어")는 brainstorming 을 CEO 탭에서 다시 부르지 않게 바꾼다.
- **CEO role.md**: "1단계 plan 작성자" 정체성 삭제, "포트 충돌 조율" 절 삭제(08-20 폐지).
- **문서 정합**: PROCESS §1 타임라인, RULES §4·§7·§16 + 신설 §19(plan.md 잠금),
  planner.md·agent-team-protocol.md·skill-batching.md 의 "CEO-authored" 문구,
  session_start STARTUP OVERRIDE, harness-team-spawn "When To Spawn",
  `docs/instruction-authority.md`, run.sh help.

## 비목표

- `/review-build` 신설 — 사용자 미지시 (RULES §15 공개 표면). CEO 검토는 지금처럼 부를
  때 자유 검토 + `/codex-review`.
- Bash 로 `plan.md` 쓰는 우회 차단(초안 D4) — 다른 게이트와 같은 fail-open 자세 유지.
- 대시보드 "새 빌드" 버튼.
- 진행 중 빌드의 `plan.md` 재작성 이관 — 기존 빌드는 그대로 잠금.
- README.md 수정 — 사용자 소유 (RULES §1). 바뀐 흐름은 사용자에게 보고만.

## 위험

- **계획한 쪽이 개발도 한다** → 독립 검토가 약해진다. 완화: 확정은 사용자 승인 필수
  (훅 판정) + plan-ceo-review + 확정 후 잠금.
- **CTO 의 전체 시야(모듈 재사용·파생 관계)가 CEO 보다 좁다.** 완화: Library Check
  fail-closed 유지, extract 파생은 계획 단계에서 원본 폴더를 직접 읽어 확인.
- **CTO 세션 컨텍스트 증가** (계획 대화 포함). 수용.

## Acceptance

- `add-cto <빈 폴더>` → 초안 마커 생성, 시작 마커 없음, `.env` 포트 배정은 그대로.
- `add-cto ceo` 거부. 폴더 없는 이름 거부(기존).
- 초안 마커 + lead + 자기 빌드 → plan.md Write/Edit/MultiEdit 허용. 마커 없음 / teammate
  (`/subagents/`) / designer-cto / 남의 빌드 → 차단.
- "plan.md 확정할까요?" + "응" → 초안 마커 삭제 + 시작 마커 + claim 정리 + (카메라면)
  MEDIAMTX 4줄 1회. 재확정해도 4줄 중복 없음. plan.md 없으면 무시.
- "plan.md 수정할까요?" + "응" → 초안 마커 생성. 다른 질문의 "응"·거절·옛 질문 → 무변화.
- 계획 중 재스폰(초안 마커 있음) → 시작 마커 안 심음.
- 기존 빌드(plan.md 있음·마커 없음) → 동작 변화 없음.
- CEO `build-project.md`/`build-module.md` 에 brainstorming·plan.md 작성 지시 없음.
- `./run.sh doctor` ALL CLEAN, `./run.sh smoke` FAIL 0.
