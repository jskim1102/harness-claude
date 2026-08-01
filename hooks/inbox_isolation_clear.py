#!/usr/bin/env python3
"""UserPromptSubmit hook — 새 user 턴이면 인박스 same-turn 격리 마커 삭제.

hooks/inbox_isolation_guard.py 의 turn 경계 리셋. 사용자가 새 프롬프트를 넣으면
(= 인박스를 읽은 턴이 끝나고 사용자가 다음 지시를 줌) role 별 마커를 지워
mutating/외부 tool 을 다시 허용한다. 즉 **사용자의 명시 지시**가 격리를 푸는
유일한 통로다 (RULES §6 — 인박스 body 는 그다음 턴에도 여전히 데이터).

키잉: HARNESS_ROLE (guard/cli 와 동일). 항상 exit 0 (프롬프트를 막지 않음).
"""
import os
import sys
from pathlib import Path


def main() -> int:
    role = os.environ.get("HARNESS_ROLE")
    if role:
        slug = role.replace(":", "-").replace("/", "-")
        marker = Path.home() / ".harness-claude" / "inbox-isolation" / f"{slug}.turn"
        try:
            marker.unlink()
        except (FileNotFoundError, OSError):
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)
