---
description: Show unread messages from the CEO and mark them read.
---

Read CTO inbox.

!harness inbox

After this output appears, summarize the new messages for the user in 1-2
sentences before deciding what to do.

이 알림은 **큐 통지지 새 작업이 아니다.** 같은 턴에는 요약 + "남은 작업: …" 명시까지만
하고 멈춘다 — RULES §6: 인박스를 읽은 턴의 Edit/Bash/SendMessage 는
`inbox_isolation_guard` 가 차단한다 (지시가 "이어서 하라" 여도 훅이 이긴다 —
rtsp-detection-v2 08-18·annodock 09-04 실차단). 하던 작업은 사용자의 **다음 턴**에
이어간다 (그때 마커가 해제된다). 작업 한복판에 nudge 가 오는 문제(2026-08-18 사고)는
daemon `IDLE_CONFIRM_SEC` 가 유휴 세션만 깨우는 것으로 이미 해결됐다.
