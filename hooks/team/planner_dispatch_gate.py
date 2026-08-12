#!/usr/bin/env python3
"""planner_dispatch_gate — 분해(초기 task/spec 생성) 이후의 planner 구동을 차단.

사용자 하드룰 (2026-08-11): planner 는 (1) 최초 분해 — plan.md →
specs/spec.md + specs/tasks.md 생성 — 와 (2) 사용자가 명시적으로 시킨 경우
외에는 절대 돌리지 않는다. 기존에는 decompose.md/RULES 의 "planner 재사용
규칙" prose 뿐이라 CTO 재량으로 재스폰·재디스패치가 가능했다 — 이 게이트가
그 재량을 결정론으로 제거한다.

구동 경로는 두 개고 둘 다 막는다:
  - `Agent(subagent_type=planner)` — 스폰
  - `SendMessage(to=planner)` — 이미 떠 있는 teammate 재디스패치

게이트 로직 (PreToolUse, Agent·SendMessage):
  - planner 대상이 아니면 → 통과.
  - `<빌드dir>/specs/tasks.md` 가 아직 없으면 = 최초 분해 진행 중 → 통과.
  - tasks.md 가 있으면 → 호출 텍스트(Agent prompt / SendMessage message)에
    `HARNESS_USER_OK=planner` 토큰이 있어야 통과. 토큰은 사용자가 planner
    구동을 명시 지시했을 때만 붙인다 — 지시 없이 붙이는 것 자체가 위반
    (git_guard 마커와 같은 계약).

FAIL OPEN: 프로젝트 미식별·상태 I/O 실패 등 어떤 예외든 allow.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block, project_of, repo_root  # noqa: E402

TOKEN = "harness_user_ok=planner"


def _tool_input(p):
    return p.get("tool_input") or p.get("toolInput") or {}


def _tasks_md_exists(p):
    """빌드 dir 의 specs/tasks.md 존재 여부. 프로젝트 미식별이면 None."""
    name = project_of(p)
    if not name or name == "_noteam":
        return None
    repo = repo_root()
    for base in ("claude-project", "modules"):
        d = os.path.join(repo, base, name)
        if os.path.isdir(d):
            return os.path.isfile(os.path.join(d, "specs", "tasks.md"))
    return None


def main():
    p = read_payload()
    tool = p.get("tool_name") or p.get("toolName") or ""
    ti = _tool_input(p)

    if tool == "Agent":
        target = (ti.get("subagent_type") or ti.get("subagentType") or "")
        text = ti.get("prompt") or ""
        verb = "스폰(Agent)"
    elif tool == "SendMessage":
        target = (ti.get("to") or ti.get("recipient") or "")
        text = ti.get("message") or ""
        verb = "디스패치(SendMessage)"
    else:
        allow()
        return

    # agentId 형식(planner@session-xxxx)도 같은 수신자다 — @ 앞만 본다.
    if str(target).strip().lower().split("@")[0] != "planner":
        allow()
        return

    exists = _tasks_md_exists(p)
    if exists is not True:
        allow()  # 최초 분해 진행 중(False) 또는 미식별(None=fail open)
        return

    if TOKEN in str(text).lower():
        allow()  # 사용자 명시 지시 마커 — 지시 없이 붙이면 그 자체가 위반
        return

    block(
        "PreToolUse", p,
        f"planner {verb} 차단 — specs/tasks.md 가 이미 존재한다 (최초 분해 완료).\n"
        "planner 는 (1) 최초 task/spec 생성과 (2) 사용자 명시 지시 외에는 구동 금지다\n"
        "(2026-08-11 사용자 하드룰).\n"
        "→ 사용자가 planner 구동을 명시 지시한 경우에만, 호출 텍스트에\n"
        "  `HARNESS_USER_OK=planner` 토큰을 넣어 재호출하라. 지시 없이 토큰을\n"
        "  붙이는 것 자체가 위반이다.\n"
        "→ 분해 결과를 바꾸고 싶으면 먼저 /msg-ceo 로 CEO/사용자 판단을 받아라.",
    )


if __name__ == "__main__":
    main()
