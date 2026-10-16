---
name: harness-plan
description: Author and confirm the build's plan.md with the user (planning phase). Use on the CTO lead's first turn whenever the build dir has no plan.md (start marker absent — do not spawn the team), and whenever the user asks to change the plan after it was confirmed. Runs brief → brainstorming → Library Check → source analysis → plan.md → plan-ceo-review and ends the turn with `plan.md 확정할까요?`.
---

# harness-plan — 계획 단계 (CTO lead)

2026-10-15 역할 재분할: `plan.md` 는 **lead CTO 가 사용자와 쓴다**. CEO 는
`/build-project <name>`·`/build-module <name>` 로 빈 폴더만 만들었다. 이 스킬이
끝나면 사용자 승인 한 번으로 `plan.md` 가 잠기고 팀이 뜬다 (RULES §19).

## 언제

- **빌드 dir 에 `plan.md` 가 없고 시작 마커도 없다** = 계획 단계. 팀을 스폰하지
  말고, `스폰할까요?` 도 묻지 말고, 이 스킬부터. 첫 메시지가 brief 면 그걸로
  시작하고, "시작"·인사뿐이면 "무엇을 만들까요? 한두 줄이면 됩니다." 로 묻는다.
- 확정 후 사용자가 계획 변경을 요구하거나, 분해·개발 중 계획 자체가 틀렸음이
  드러났을 때 → 아래 "계획 변경".

## 하지 않는 것

- phase/ckpt 분해 X (planner 몫, 확정 후). 코드·디자인 X. Codex·designer 발주 X.
- 팀 스폰 X — 확정 승인 턴에 훅(`plan_readonly_gate`)이 시작 마커를 심는다. 그
  턴에 `harness-team-spawn` 으로 spawn 하고 사용자의 분해 지시를 기다린다.
- `plan.md` 외 파일 생성 X. README X (RULES §1).
- 확정 질문을 다른 승인(alembic, 포트 …)과 한 메시지에 섞지 않는다 — bare "응" 이
  모호해지고 훅은 직전 메시지의 질문만 본다.

## 절차

빌드타입은 내 디렉토리가 확정한다 (`claude-project/` = project, `modules/` = module
— PROCESS §0). 재해석 금지.

1. **brief** — 사용자가 만들고 싶은 것 한두 줄.
2. **brainstorming** (`superpowers:brainstorming` 스킬) — 사용자와 정렬:
   - 축2 target: `new` | `extend:<기존프로젝트>` — 추론 + **사용자 확인**.
     `extend` 면 보통 이 빌드가 아니라 그 프로젝트의 CTO 탭에서 할 일이다 —
     사용자에게 짚어주고 멈춘다.
   - 축3 source: `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합
     (여럿이면 `+` 로 나열: `modules:[x] + extract:[y/기능]`) — 추론 + **사용자 확인**.
   - 모듈이면 **재사용 경계 + 계약 요점**(무엇을 노출하나, 입출력)을 끌어낸다.
3. **Library Check (fail-closed, RULES §7)** — `$HARNESS_ROOT/modules/*/specs/USAGE.md`
   스캔 (`/modules`). 겹치면 `reuse:<slug> (이유)`, 없으면 `no-overlap (이유)` —
   **반드시 하나를 적는다**. USAGE.md 없는 모듈 = 빌드 중, 소비 금지.
4. **재료 분석 (축3 ≠ scratch 일 때만)** — 재료가 코드(modules/ 또는 다른 프로젝트)면
   `understand-anything` 으로 **기능이 어느 파일에 있는지** 파일 수준까지 파악해
   `## 3` 에 기록한다 (라인 수준 추출은 분해 때 planner 의 `From:` 포인터 몫). 재료가 git
   URL 이면 먼저 `$HARNESS_ROOT/run.sh fetch <url>` 로 `.sources/` 에 받는다. 소스는
   read-only — 절대 수정하지 않는다.
5. **plan.md 작성** — 빌드 dir 루트에 쓴다 (초안 마커가 있어 Write 가 통과한다):

   ```markdown
   # Plan: <name>
   ## 1. Build Type      # deliverable: project|module / target: <축2> / source: <축3>
   ## 2. Goal            # 무엇을 왜, 1~2줄
   ## 3. Library Check   # reuse:<slug>(이유) | no-overlap(이유) (+extract 면 파일 수준 위치)
   ## 4. Requirements    # 핵심 기능 bullet 요점만 (+모듈: 재사용 경계/계약 요점)
   ## 5. Constraints     # 스택/보안/성능 선호, non-goals (모듈: "프론트 단순" 명시)
   ## 6. Open Questions  # 분해 때 풀 열린 질문
   ```

   - `## 1` 은 대시보드·lineage 스캐너가 읽는다 — 형식을 지킨다 (`source: modules:[x]`).
   - `## 4` 는 요점 bullet — 풀스펙은 spec.md 몫.
   - `## 5`: postgres 는 **공유 인스턴스**(127.0.0.1:5435 db-per-project, RULES
     §4.1/§5.2) — 전용 postgres 를 spec 하지 않는다. **카메라 빌드는 `mediamtx` 를
     self-host** — 그 단어가 plan.md 에 있어야 확정 때 `MEDIAMTX_*` 포트 4줄이
     `.env` 에 들어간다 (RULES §4). 비카메라 빌드엔 쓰지 않는다.
   - 모듈: 프론트는 데모용 최소 UI, 기능 목적 최우선, 완성 = 기능 + `specs/USAGE.md`.
6. **plan-ceo-review** (gstack 스킬) — 내용/scope/전제 점검. 지적은 사용자와 정리해
   반영한다.
7. **확정 질문** — 요약 몇 줄 + **`plan.md 확정할까요?`** 로 턴을 끝낸다. 단독으로.
   사용자가 승인(응/네/확정)하면 훅이 그 턴에 잠금 + 시작 마커를 심는다 → 그 턴에
   `harness-team-spawn` 으로 planner·reviewer 를 spawn 하고 사용자의 분해 지시
   (`/decompose` 또는 자연어)를 기다린다. 거절·수정 요청이면 반영 후 다시 묻는다.

## 계획 변경 (확정 후)

잠긴 `plan.md` 는 Write/Edit 가 막힌다. 바꿔야 하면: 이유 한 줄 +
**`plan.md 수정할까요?`** 로 묻고 턴을 끝낸다 → 승인 → (훅이 초안으로 되돌림) →
수정 → 다시 **`plan.md 확정할까요?`**. 계획-현실의 작은 괴리는 plan.md 가 아니라
`specs/spec.md`·`specs/tasks.md` 갱신으로 (재분해 규모면 사용자에게 — planner 는
사용자 명시 시만, RULES §17).

## 유동 스킬

- `grill-me` — 사용자가 계획을 더 압박하고 싶을 때 (opt-in).
- 외부 조사(WebSearch·WebFetch) — 외부 사실 없이는 *지금* 못 닫는 plan 필드(규제·
  표준, 기술 실현가능성, 외부 API 제약)가 있을 때만 **제안** → 승인 시 실행. 미룰 수
  있으면 `## 6 Open Questions` 로.
