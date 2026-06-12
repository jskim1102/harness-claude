---
description: Read-only audit of the harness-claude project itself. 결정론 검사(doctor+smoke)를 먼저 돌리고, harness-audit 다이나믹 워크플로우(6 perspective + adversarial verify)로 의미 수준 감사를 수행해 JSON 결과를 요약한다.
---

점검 3계층 (plans/harness.md "시스템 점검"):
deterministic(doctor·smoke) → semantic(이 워크플로우) → cross-model(codex, 사용자 판단).

## 절차

1. **결정론 선행** — 둘 다 실행하고 결과를 사용자에게 1줄씩 보고:
   ```
   ./run.sh doctor    # 금지토큰/참조무결성/문법/버전
   ./run.sh smoke     # 30+ 결정론 스모크
   ```
   FAIL 이 있으면 그것부터 사용자에게 surface — 의미 감사 전에 고칠지 결정받는다.

2. **의미 감사** — 하네스 루트를 resolve (`echo $HARNESS_ROOT`) 후:
   ```
   Workflow({ name: "harness-audit", args: { repo: "<absolute harness root>" } })
   ```

3. 워크플로우 완료 후:
   - 1화면 요약: 분류별 카운트, top 5 고임팩트 finding (KEEP 제외),
     adversarial `survives=false` 판정 목록.
   - 전체 리포트를 `~/.harness-claude/audits/harness-audit-YYYY-MM-DD.md` 로 저장.
   - 어떤 finding 에 조치할지 사용자에게 질문. **이 턴에서 직접 수정하지 않는다.**

Read-only contract: 워크플로우는 파일을 수정하지 않는다. 적용은 별도 결정.
