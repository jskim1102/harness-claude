---
description: 블로커·질문 에스컬레이션을 CEO 로 전송 (완료·진행 보고 금지 — 2026-08-20 다이어트). Usage: /msg-ceo "<message>"
argument-hint: "<message>"
---

Send an escalation to CEO via the harness CLI.

용도 = **블로커·질문 에스컬레이션 전용.** 완료·진행 보고는 보내지 않는다
(완료 정본 = tasks.md `[✅]` + 사용자 터미널 보고, 상태 = 대시보드).

!printf '%s' '$0' | harness send --to ceo --body-stdin
