---
description: Read-only audit of the harness-claude project itself. 결정론 검사(doctor+smoke)를 먼저 돌리고 의미 수준 감사를 수행한다 — 세션 effort 가 ultracode 면 다이나믹 워크플로우(6 perspective + adversarial verify), 아니면 같은 관점을 CEO 가 직접 순회 검사.
---

점검 3계층:
deterministic(doctor·smoke) → semantic(이 워크플로우) → cross-model(codex, 사용자 판단).

## 절차

1. **결정론 선행** — 둘 다 실행하고 결과를 사용자에게 1줄씩 보고:
   ```
   ./run.sh doctor    # 금지토큰/참조무결성/문법/버전
   ./run.sh smoke     # 30+ 결정론 스모크
   ```
   FAIL 이 있으면 그것부터 사용자에게 surface — 의미 감사 전에 고칠지 결정받는다.

2. **의미 감사** — 하네스 루트를 resolve (`echo $HARNESS_ROOT`) 후, 세션 effort 로 분기:
   - **ultracode 세션** (ultracode on 시스템 리마인더로 확인) → 다이나믹 워크플로우:
     ```
     Workflow({ scriptPath: "<harness root>/plugins/ceo/workflows/harness-audit.js",
                args: { repo: "<absolute harness root>" } })
     ```
   - **그 외 effort** → 워크플로우 없이 직접 진행: `plugins/ceo/workflows/harness-audit.js`
     의 Analyze 단계 6개 perspective 프롬프트를 읽고 그 관점들을 본인이 순서대로 검사,
     finding 을 같은 분류(KEEP/SHRINK/MOVE/SPLIT/CONVERT/DELETE)로 정리한다.
     파괴적 권고(DELETE/SHRINK/MOVE 등)는 스스로 반증을 시도한 뒤 살아남은 것만 보고
     (adversarial self-check — 아래 감사 철학의 false-positive 교훈 동일 적용).

3. 의미 감사 완료 후:
   - 1화면 요약: 분류별 카운트, top 5 고임팩트 finding (KEEP 제외),
     adversarial `survives=false` 판정 목록.
   - 전체 리포트를 `~/.harness-claude/audits/harness-audit-YYYY-MM-DD.md` 로 저장.
   - 어떤 finding 에 조치할지 사용자에게 질문. **이 턴에서 직접 수정하지 않는다.**

Read-only contract: 감사(워크플로우/직접 모두)는 파일을 수정하지 않는다. 적용은 별도 결정.

## 감사 철학 (2026-06-12 구현 리뷰 교훈)

버그 17건 중 11건 = 참조 문서망의 구체계 drift (런타임 미주입 문서가 stale).
**감사 finding 은 adversarial verify 없이 믿지 않는다 — false-positive 62% 실측.**
자체 트랙(이 워크플로우)과 codex 트랙은 상보적이며, 실동작 테스트만 잡는 버그가
따로 있으므로 정적 감사로 끝내지 않는다.
