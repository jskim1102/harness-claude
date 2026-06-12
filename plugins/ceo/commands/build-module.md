---
description: 1단계(CEO) — 모듈 빌드 plan.md 작성. 사용자의 <brief>를 받아 brainstorming으로 정렬하고, 축2(target)·축3(source)를 추론·확인한 뒤 modules/<name>/plan.md 1개를 작성한다. 모듈 = 여러 프로젝트에 재사용되는 기능 단위 (프론트 단순, 기능 목적 최우선). plan-ceo-review 게이트 통과 후 사용자에게 add-cto 스폰 명령을 안내한다. 사용자가 "/build-module <brief>" 또는 "모듈 만들어/모듈로 만들어둬" 류로 요청할 때 사용.
---

# /build-module <brief>

**축1 = module 확정** (이 명령 자체가 선언). 산출물 = **여러 프로젝트에
재사용되는 기능 단위** — 그 자체가 개발 대상이다. 빌드 dir = `modules/<name>/`
(작업장 = 라이브러리 동일).

모듈의 본질 (plan.md ## 5 Constraints 에 반영할 것):
- **프론트엔드는 단순하게** — 데모/테스트용 최소 UI. 화려한 디자인 금지
  (다른 프로젝트가 갖다쓰기 쉬워야 함).
- **기능적 목적이 최우선** — 자기완결, 명확한 경계, 특정 프로젝트 가정에
  묶이지 않을 것.
- 완성 기준 = 기능 완비 + `specs/USAGE.md` (CTO 가 마지막에 작성).

1단계(CEO)의 유일한 산출물은 **`modules/<name>/plan.md` 1개**다.
phase/ckpt 분해는 하지 않는다 (CTO 몫). codex 호출 없음.

## 절차

1. **brainstorming (고정 스킬)** — `<brief>` 를 사용자와 정렬:
   - 축2 (target): `new` | `extend:<기존>` — 추론 + **사용자 확인**
   - 축3 (source): `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합 — 추론 + **사용자 확인**
   - **재사용 경계 + 계약 요점** (무엇을 노출하나, 입출력) 을 brief 에서 끌어낸다.
   - `<name>` (kebab-case) 확정.

2. **Library Check (고정 동작, fail-closed)** — `modules/*/specs/USAGE.md` 스캔.
   같은/비슷한 모듈이 이미 있으면 `reuse:<slug> (이유)` (= 기존 모듈 확장이
   맞는지 사용자와 논의), 없으면 `no-overlap (이유)`. **반드시 명시** (RULES §7).

3. **조건부 고정 (축3 source ≠ scratch — 자동 선택)**:
   - 재료가 코드면 → `understand-anything` (extract 면 파일 수준 위치까지 ## 3 기록)
   - 외부 조사 필요하면 → `deep-research`
   - git URL 소스는 `./run.sh fetch <url>` 선행. 소스 read-only.

4. **plan.md 작성** — `modules/<name>/` 디렉토리를 만들며 작성:

   ```markdown
   # Plan: <name>
   ## 1. Build Type      # deliverable: module / target: <축2> / source: <축3>
   ## 2. Goal            # 무엇을 왜, 1~2줄
   ## 3. Library Check   # reuse:<slug>(이유) | no-overlap(이유) (+extract면 파일 수준 위치)
   ## 4. Requirements    # 핵심 기능 bullet 요점만 + 재사용 경계/계약 요점
   ## 5. Constraints     # 스택/보안/성능, non-goals — "프론트 단순" 명시
   ## 6. Open Questions  # CTO가 분해 때 풀 것
   ```

5. **plan-ceo-review (고정 게이트)** — plan.md 점검 후 사용자 🤚 최종 확인.

6. **사용자 안내**:
   ```
   plan 확정: modules/<name>/plan.md
   다음 — 새 터미널에서:
     ./run.sh add-cto modules/<name>/plan.md
     ./run.sh attach cto-<name>
   ```

## 유동 스킬 (필요 판단 시)

- `office-hours` / `grill-me` / `deep-research`

## Boundaries

- plan.md 외 파일 생성 X. phase/ckpt 분해 X. CTO 스폰 직접 실행 X.
  codex 호출 X. README 작성 X (RULES §1 — `specs/USAGE.md` 는 CTO 의 완성 산출물).

ARGUMENTS: $ARGUMENTS
