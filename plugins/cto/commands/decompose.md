---
description: 분해 시작 — planner 에게 plan.md → specs/spec.md + specs/tasks.md 생성을 dispatch 한다. 사용자의 명시 분해 지시 신호. --design = 디자인 강화 모드.
argument-hint: [--design]
---

# /decompose

이 명령 = **사용자의 명시 분해 지시** (PROCESS §2.1 의 "사용자가 CTO 에게 분해를
명시적으로 지시" 신호). 이 턴에 planner 에게 분해를 dispatch 한다.

인자는 `--design` 플래그 하나뿐이다. 분해 방식에 대한 지시는 대화로 한다 —
CTO 세션은 대화형이므로 사용자가 같은 메시지나 다음 턴에 말하면 되고,
요구사항은 plan.md 가 정본이다(명령 인자로 받은 지시는 어디에도 남지 않아
재분해 시 증발한다).

## 모드

`--design` 플래그 유무로 갈라진다.

- **(없음) 일반 모드** — 아래 절차 그대로.
- **`--design` 디자인 강화 모드 (design-max)** — phase2 디자인을 사용자↔designer-cto
  직접 대화로 진행하는 모드 (정본: `docs/superpowers/specs/2026-08-05-decompose-design-mode-design.md`).
  분해 자체는 일반 모드와 동일하되 다음 두 가지가 다르다:
  - `<빌드dir>/specs/design-mode` 파일에 `design-max` 한 줄을 기록한다 —
    이후 CTO/designer-cto 세션이 읽을 모드 마커 (독립 세션이라 명령 인자가 안
    닿으므로 파일이 전달로다). 이미 있으면 그대로 둔다.
  - planner 는 phase2 의 `[design]` task acceptance 에 design-max 산출물 계약을
    명시한다: `specs/design/refs/`(구조 refs — 화면별, 색·폰트 인용 금지) +
    `specs/design/refs-visual/`(톤 refs — 제품 전체 다크1+라이트1, 구조 인용 금지) +
    `specs/design/brief.md`(**UI 구조 전용** 계약) + `specs/design/sample/`
    (**구조 스케치** — 전 화면 무채색 와이어프레임 webp + 생성 스크립트, 사용자
    화면단위 검수 완료) + `specs/design/system/`(**비주얼 정본** — 정본 규격
    `theme.json`+`styles.css`+`readme.md`+`thumbnail.html`+`theme.html`+
    `foundations/`+`components/`, DesignSync push 원본) +
    `specs/design/assets/`(제품 콘텐츠 이미지가 필요한 빌드만 — 데이터 도구의
    mock 이미지는 코드 생성이지 자산이 아니다) +
    `specs/design/handoff/`(Claude Design 화면 생성 결과 수신함).
    **게이트 원칙**: acceptance 는 designer 가 **자기 힘으로 닫을 수 있는 것**만
    검사한다. `handoff/` 는 사용자가 Claude Design 에서 뽑아 놓는 조건부 산출물이라
    폴더 존재·비어있음을 게이트로 걸지 마라 — 검사 대상은 designer 산출물인
    `web-contract.md`(핸드오프 정합 결과)다. 같은 이유로 `assets/` 도 미생성이
    정상일 수 있으니 존재를 게이트로 걸지 않는다(사유는 brief.md 에 기록).
  phase2 실행 시 CTO 는 발주하지 않는다 — "phase2 시작하세요 (design-max —
  designer 탭에서 진행)" 안내 후 비관여, 사용자가 산출물 경로를 통보하면 그때
  Codex 프론트 구현을 발주한다 (PROCESS.md phase2 design-max 분기 참조).

## 절차

1. **팀 확인** — planner 가 로스터에 없으면 먼저 spawn 한다 (harness-team-spawn).
2. **planner 에 dispatch** — plan.md 를 읽고 PROCESS §2.1 분해 공식대로
   `specs/spec.md` + `specs/tasks.md` 를 생성하라고 지시한다. 사용자가 대화로
   분해 방식을 지시했으면 함께 전달하고, 그것이 트리 구조를 바꾸면 planner 가
   `spec.md` 에 근거로 기록한다.
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
