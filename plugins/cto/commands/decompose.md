---
description: 분해 시작 — planner 에게 plan.md → specs/spec.md + specs/tasks.md 생성을 dispatch 한다. 사용자의 명시 분해 지시 신호. --design = 디자인 강화 모드.
argument-hint: [--design] [선택 메모 — 분해 시 반영할 지시사항]
---

# /decompose

이 명령 = **사용자의 명시 분해 지시** (PROCESS §2.1 의 "사용자가 CTO 에게 분해를
명시적으로 지시" 신호). 이 턴에 planner 에게 분해를 dispatch 한다.

```
$ARGUMENTS
```

## 모드

인자 맨 앞의 `--design` 플래그로 갈라진다 (그 뒤 나머지 = 메모).

- **(없음) 일반 모드** — 아래 절차 그대로.
- **`--design` 디자인 강화 모드 (design-max)** — phase2 디자인을 사용자↔designer-cto
  직접 대화로 진행하는 모드 (정본: `docs/superpowers/specs/2026-08-05-decompose-design-mode-design.md`).
  분해 자체는 일반 모드와 동일하되 다음 두 가지가 다르다:
  - `<빌드dir>/specs/design-mode` 파일에 `design-max` 한 줄을 기록한다 —
    이후 CTO/designer-cto 세션이 읽을 모드 마커 (독립 세션이라 명령 인자가 안
    닿으므로 파일이 전달로다). 이미 있으면 그대로 둔다.
  - planner 는 phase2 의 `[design]` task acceptance 에 design-max 산출물 계약을
    명시한다: `specs/design/refs/`(mobbin 레퍼런스 이미지) + `specs/design/brief.md`
    (상세 브리프) + `specs/design/assets/`(AI 생성 자산, 키 없으면 스킵) +
    `specs/design/handoff/`(Claude Design 핸드오프 번들 정합).
  phase2 실행 시 CTO 는 발주하지 않는다 — "phase2 시작하세요 (design-max —
  designer 탭에서 진행)" 안내 후 비관여, 사용자가 산출물 경로를 통보하면 그때
  Codex 프론트 구현을 발주한다 (PROCESS.md phase2 design-max 분기 참조).

## 절차

1. **팀 확인** — planner 가 로스터에 없으면 먼저 spawn 한다 (harness-team-spawn).
2. **planner 에 dispatch** — plan.md 를 읽고 PROCESS §2.1 분해 공식대로
   `specs/spec.md` + `specs/tasks.md` 를 생성하라고 지시한다. 위 `$ARGUMENTS` 가
   있으면 분해 지시사항으로 함께 전달한다.
3. **커버리지 검증** — 분해 완료 후 커버리지 기계 검증(RULES 분해 게이트)을
   통과했는지 확인한다. 실패 = 분해 미완, planner 에 반송.
4. **트리 표시 + 대기** — 사용자에게 phase/ckpt 트리를 표시하고 멈춘다.
   **segment 지정 (`phaseN.ckptM~phaseM.ckptK`) = 분해 승인 = 게이트1** —
   사용자가 지정하기 전에는 어떤 task 도 시작하지 않는다.

## 금지

- 이미 `specs/tasks.md` 가 있고 미완 ckpt 가 남아 있으면 = 빌드 진행 중.
  재분해로 기존 트리를 덮지 말고, 사용자에게 현재 트리 상태를 보여주고
  무엇을 바꾸고 싶은지 확인한다 (RULES planner 재사용 규칙).
- 분해와 구현을 한 턴에 잇지 않는다 — segment 지정은 사용자 몫.
