---
description: 하네스 문제 신고를 CEO 로 전송 (훅·게이트 오작동, 규칙 충돌 — 2026-10-15). 프로젝트 질문·블로커는 CTO 터미널에서 사용자에게 직접. 완료·진행 보고 금지. Usage: /msg-ceo "<message>"
argument-hint: "<message>"
---

Send a harness problem report to CEO via the harness CLI.

용도 = **하네스 문제 신고 전용** (2026-10-15 역할 재분할). 훅·게이트가 잘못 막거나
규칙끼리 충돌하는 *시스템* 문제만 보낸다. 프로젝트 질문·블로커는 CEO 가 아니라
**이 터미널에서 사용자에게 직접** 묻는다. 완료·진행 보고는 보내지 않는다
(완료 정본 = tasks.md `[✅]` + 사용자 터미널 보고, 상태 = 대시보드).

!printf '%s' '$0' | harness send --to ceo --body-stdin
