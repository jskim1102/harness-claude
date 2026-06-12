---
description: Spawn the standard 4-teammate Agent Team (planner, designer, developer, reviewer) and start the 2단계 decomposition from plan.md.
argument-hint: [one-line note — plan.md 가 정본]
---

# /start-project

표준 4-teammate Agent Team 을 spawn 하고, **plan.md(CEO 작성)로부터
2단계 분해**를 시작한다. 모드 분기 없음 — 빌드타입은 디렉토리가 이미
확정했다 (claude-project/=프로젝트, modules/=모듈. PROCESS §0).

전제: 프로젝트 루트에 `plan.md` 가 있어야 한다 (add-cto 가 보장).
없으면 중단하고 사용자에게 1단계(CEO `/build-project`|`/build-module`)
선행을 안내한다.

```
$ARGUMENTS
```

## How To Spawn

Invoke the `harness-team-spawn` skill. It owns the full spawn workflow:

- **Team name derivation** from `HARNESS_ROLE` + slug, with the
  `<slug>-<8char-hash>` fallback when the env is missing (via
  `scripts/derive_team_name.sh` — do not hand-roll the hash length).
- **Standard spawn prompt** for the 4-teammate Opus team (planner,
  designer, developer, reviewer) with plan-approval mode default-on.
- **Existing-team handling** — resume vs. delete vs. cross-CTO
  collision rename.

Do not paraphrase, do not shorten the spawn prompt, do not skip
teammates.

## After Spawn — 분해 위임

planner 에게 첫 SendMessage:

```
SendMessage to planner: plan.md (프로젝트 루트) 를 읽고 PROCESS §2 분해를
실행하라. writing-plans 로 specs/spec.md + specs/tasks.md (phase→ckpt 트리)
작성. 분해 공식 고정: phase1=환경설정 / phase2=프론트 디자인 / phase3+=개발
(축2=extend 면 기존 트리 append). 장치: 모든 ckpt 가 spec 라벨(← F<n>) 역참조,
재료 기반 기능은 [supplied:<출처>] 태그. 완료 시 알려라.
```

planner 완료 → **커버리지 기계검증** (spec 의 모든 Feature ≥1 ckpt —
fail-closed) → 트리를 진행률과 함께 사용자에게 surface.

## Report to the user

1. Team name + spec 위치 (`specs/spec.md`, `specs/tasks.md`)
2. phase→ckpt 트리 (분해 완료 후)
3. 다음 행동 안내: "segment 를 지정해주세요 — 예: `phase1.ckpt1 ~
   phase2.ckpt2 진행해` (autopilot 은 phase3+ 범위에 `... autopilot`)"

**사용자의 segment 지정 = 분해 승인.** 그 전에 빌드 작업을 시작하지
않는다.
