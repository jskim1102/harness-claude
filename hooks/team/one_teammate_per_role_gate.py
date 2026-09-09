#!/usr/bin/env python3
"""one_teammate_per_role_gate — 3-Claude 팀 구성과 역할당 1명을 강제.

CTO의 Claude 팀은 planner/reviewer 두 명이다 (designer 는 2026-07-29 부터 독립
designer-cto 세션). production developer는 별도
Codex 세션이므로 `Agent(subagent_type=developer)`는 lead/nested 위치와 무관하게 차단한다.
표준 Claude 화면은 lead + skill activity이고 teammate는 in-process다.

lead(CTO) 호출 vs 팀원의 nested 호출 구별 = payload 의 `transcript_path` — 팀원이 부르면
경로에 `/subagents/` 가 있다(프로브 확인).

게이트 (PreToolUse, `Agent` tool 한정):
  - subagent_type=developer → 항상 차단 (Codex 전용 역할).
  - 그 외 transcript_path 에 `/subagents/` 있음 → pane 없는 병렬 fan-out 허용.
  - lead(CTO) 호출이고 subagent_type ∈ {planner,reviewer} 이며
    그 역할 spawn claim이 이미 있으면 → 차단 (2번째 같은 역할 teammate 금지).
  - 그 외 전부 허용 (general-purpose 등 비-팀역할, 첫 스폰 등).

역할 claim은 원자적 파일 생성으로 기록한다. `/start-project`의 새 explicit signal이
claim을 초기화한다. FAIL OPEN: 상태경로/파싱 실패 등 어떤 예외든 허용.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block  # noqa: E402
from planner_dispatch_gate import TOKEN as PLANNER_TOKEN  # noqa: E402
from planner_dispatch_gate import _tasks_md_exists  # noqa: E402

ROLES = ("planner", "reviewer")
CLAIMS_DIR = os.path.expanduser("~/.harness-claude/orca-team-spawn-claims")


def _tool_input(p):
    return p.get("tool_input") or p.get("toolInput") or {}


def _cto_name(payload):
    role = os.environ.get("HARNESS_ROLE", "")
    if role.startswith("cto:"):
        return role[len("cto:"):]
    cwd = payload.get("cwd") or payload.get("workingDirectory") or ""
    return os.path.basename(os.path.normpath(cwd)) if cwd else ""


def _claim_role(name, role):
    """Atomically claim one top-level role. True=first claim, False=duplicate.

    State I/O failures return None so the caller can fail open.
    """
    if not name or not all(c.isalnum() or c == "-" for c in name):
        return None
    path = os.path.join(CLAIMS_DIR, name, role + ".claimed")
    try:
        os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return None


def main():
    p = read_payload()
    if (p.get("tool_name") or p.get("toolName") or "") != "Agent":
        allow()

    st = (
        _tool_input(p).get("subagent_type")
        or _tool_input(p).get("subagentType")
        or ""
    ).strip().lower()
    if st == "developer":
        block(
            "PreToolUse", p,
            "Claude developer Agent 차단 — production code는 별도 codex-cto-<name> "
            "세션만 작성한다. Claude 팀은 planner/reviewer 2명이다.",
        )
    if st == "designer":
        block(
            "PreToolUse", p,
            "Claude designer Agent 차단 — 디자인은 별도 designer-cto-<name> 독립 "
            "세션이 담당한다 (2026-07-29 분리). 발주는 harness send --to "
            "designer-cto:<name>. Claude 팀은 planner/reviewer 2명이다.",
        )

    tp = p.get("transcript_path") or p.get("transcriptPath") or ""
    if "/subagents/" in tp:
        allow()  # 비-developer nested subagent (paneless 병렬 fan-out)

    if st not in ROLES:
        allow()  # 팀 역할 아님 → 허용

    # planner_dispatch_gate 가 어차피 차단할 호출은 claim 하지 않는다. PreToolUse
    # 훅 둘이 같은 호출에 각각 돌아서, 여기서 claim 을 먼저 쓴 뒤 저쪽이 block
    # 하면 planner.claimed 유령이 남는다 — 이후 사용자 승인(HARNESS_USER_OK=planner)
    # 스폰까지 "중복" 으로 막는 결정론 웨지 (2026-08-20 annodock 실측).
    if st == "planner":
        text = _tool_input(p).get("prompt") or ""
        if _tasks_md_exists(p) is True and PLANNER_TOKEN not in str(text).lower():
            allow()

    claimed = _claim_role(_cto_name(p), st)
    if claimed is False:
        block(
            "PreToolUse", p,
            f"팀원 중복 차단 — 역할 '{st}' teammate spawn이 이미 claim됐다.\n"
            "표준 Claude 팀 = 역할당 1명(lead + planner + reviewer in-process).\n"
            f"→ 같은 역할 2번째 teammate 를 Agent 로 스폰하지 마라. 병렬이 필요하면 기존 '{st}'\n"
            "  teammate 안에서 Agent subagent 로 fan-out 하라(nested subagent 는 pane 을 만들지 않는다).",
        )
    allow()


if __name__ == "__main__":
    main()
