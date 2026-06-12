---
description: 1단계(CEO) — 프로젝트 빌드 plan.md 작성. 사용자의 <brief>를 받아 brainstorming으로 정렬하고, 축2(target)·축3(source)를 추론·확인한 뒤 claude-project/<name>/plan.md 1개를 작성한다. plan-ceo-review 게이트 통과 후 사용자에게 add-cto 스폰 명령을 안내한다. 사용자가 "/build-project <brief>" 또는 "프로젝트 만들어/지어/개발해" 류로 요청할 때 사용.
---

# /build-project <brief>

**축1 = project 확정** (이 명령 자체가 선언). 산출물 = 실사용 상용 서비스,
프론트엔드 디자인 중요, 빌드 dir = `claude-project/<name>/`.

1단계(CEO)의 유일한 산출물은 **`claude-project/<name>/plan.md` 1개**다.
phase/ckpt 분해는 여기서 하지 않는다 (CTO 2단계 몫). codex 호출 없음.

## 절차

1. **brainstorming (고정 스킬)** — `<brief>` 를 사용자와 정렬한다. 특히:
   - 축2 (target): `new` | `extend:<기존프로젝트>` — brief 분석으로 추론하고 **사용자 확인**
   - 축3 (source): `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합 — 추론 + **사용자 확인**
   - `<name>` (kebab-case) 도 여기서 확정.

2. **Library Check (고정 동작, fail-closed)** — `modules/*/specs/USAGE.md` 를
   스캔한다. brief 와 겹치는 모듈이 있으면 `reuse:<slug> (이유)`, 없으면
   `no-overlap (이유)` — **반드시 어느 한쪽을 명시**한다. 빈칸/생략 금지 (RULES §7).
   USAGE.md 가 없는 모듈은 빌드 중 — 소비 금지.

3. **조건부 고정 (축3 source ≠ scratch — 자동 선택)**:
   - 재료가 코드(modules/ 또는 기존 프로젝트)면 → `understand-anything` 으로 분석.
     extract 면 **"기능이 어느 파일들에 있는지" 파일 수준**까지 파악해 ## 3 에 기록.
   - 외부/시장 조사가 필요하면 → `deep-research`.
   - extract 소스가 git URL 이면 먼저 `./run.sh fetch <url>` 로 `.sources/` 에 받는다.
     소스는 read-only — 절대 수정하지 않는다.

4. **plan.md 작성** — `claude-project/<name>/` 디렉토리를 만들며 작성:

   ```markdown
   # Plan: <name>
   ## 1. Build Type      # deliverable: project / target: <축2> / source: <축3>
   ## 2. Goal            # 무엇을 왜, 1~2줄
   ## 3. Library Check   # reuse:<slug>(이유) | no-overlap(이유) (+extract면 파일 수준 위치)
   ## 4. Requirements    # 핵심 기능 bullet 요점만 (상세 설계는 CTO 몫)
   ## 5. Constraints     # 스택/보안/성능 선호, non-goals
   ## 6. Open Questions  # CTO가 분해 때 풀 열린 질문
   ```

   `## 4` 는 **요점 bullet 수준** — 기능 풀스펙을 쓰지 않는다.

5. **plan-ceo-review (고정 게이트)** — 작성된 plan.md 의 내용/scope/전제를
   점검한다. 통과 후 사용자에게 🤚 최종 확인.

6. **사용자 안내** — plan 확정되면:
   ```
   plan 확정: claude-project/<name>/plan.md
   다음 — 새 터미널에서:
     ./run.sh add-cto claude-project/<name>/plan.md
     ./run.sh attach cto-<name>
   ```

## 유동 스킬 (필요 판단 시)

- `office-hours` — 제품 아이디어가 모호하거나 "만들 가치" 검증이 필요할 때
- `grill-me` — 사용자가 plan 을 더 압박하고 싶을 때
- `deep-research` — 조건부 외에도 조사가 필요할 때

## Boundaries

- plan.md 외 파일 생성 X. phase/ckpt 분해 X. CTO 스폰을 CEO 가 직접 실행 X
  (사용자가 새 터미널에서). codex 호출 X. README 작성 X (RULES §1).

ARGUMENTS: $ARGUMENTS
