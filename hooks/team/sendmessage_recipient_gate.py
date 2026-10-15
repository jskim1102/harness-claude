#!/usr/bin/env python3
"""sendmessage_recipient_gate — 존재할 수 없는 수신자에게 보내는 SendMessage 차단.

문제: Codex developer 는 **SendMessage teammate 가 아니다** — `harness send`
인박스 페어 브릿지로만 닿는다 (cli.py `_assert_send_route`: cto:<name> ↔
codex-cto:<same-name>). 그런데 CTO 가 `SendMessage(developer)` 를 호출하면
도구는 성공한 것처럼 보이고 아무도 못 받는다 = **환각 전달**. 실제로 관측된
실패 모드다 (harness-team-spawn/SKILL.md: "SendMessage(developer) worked;
no such Claude teammate exists").

Claude developer teammate 는 spawn 자체가 이미 무조건 차단돼 있고
(one_teammate_per_role_gate — "Codex 전용 역할"), `plugins/cto/agents/
developer.md` 는 INACTIVE LEGACY 로 설치조차 안 된다. 즉 수신자가 존재할
방법이 없다. spawn 쪽만 막혀 있고 send 쪽이 열려 있던 반쪽을 닫는다.

게이트:
  - PreToolUse(SendMessage): 수신자 이름이 `developer` 이거나 `codex` 로
    시작하면 차단하고 `harness send --to codex-cto:<name>` 으로 안내.
  - 정당한 수신자(planner/reviewer/lead/team-lead)는 무관 → 통과.
  - designer 는 2026-07-29 부터 독립 designer-cto 세션 — SendMessage 로 안 닿는다.

주의: role.md 의 짝 규칙 "Claude teammate에게 전달됐다고 주장하지 않는다"
(허위 보고 금지)는 훅으로 잡을 수 없는 행동 규칙이라 prose 로 남는다 —
결정론 게이트 + 행동 분기의 하네스 표준 패턴.

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block  # noqa: E402

TEAMMATES = {"planner", "reviewer"}

# 앵커 매칭 — 부분문자열 금지 (`code-xyz`·`my-developer-notes` 오탐 방지).
FORBIDDEN_RE = re.compile(r"^(developer|designer(-.*)?|codex(-.*)?)$", re.IGNORECASE)


def _tool_input(payload):
    return payload.get("tool_input") or payload.get("toolInput") or {}


def _recipients(ti):
    """SendMessage 수신자 후보를 payload 모양에 관계없이 긁어온다."""
    out = []
    for key in ("to", "recipient", "agent", "agentId", "agent_id", "name"):
        v = ti.get(key)
        if isinstance(v, str):
            out.append(v)
        elif isinstance(v, list):
            out.extend(x for x in v if isinstance(x, str))
    return out


def _bare_name(recipient: str) -> str:
    """`planner@session-ab12` / `cto:demo` 에서 순수 이름만 뽑는다."""
    n = recipient.strip()
    n = n.split("@", 1)[0]      # agentId 형식
    if ":" in n:                 # role 형식 (codex-cto:demo)
        n = n.split(":", 1)[0]
    return n


def _current_roster():
    """현 빌드의 팀 roster 이름 집합 (cwd 매칭 config 전체의 **union**).
    판단 불가면 None (fail-open).

    같은 살아있는 lead 프로세스가 팀 dir 을 **여러 개** 가질 수 있다 — 스폰이
    만든 roster dir 과, 그 몇 초 뒤 런타임이 lazy 생성하는 lead-only dir 이
    공존한다 (2026-07-29 실측: session-25666517[3명] + 6초 뒤
    session-23c22595[lead만]). 예전의 "최신 createdAt 1개 선택"은 이때
    lead-only 쪽을 골라 방금 스폰된 팀을 오탐 차단했다. 그래서 union 이 정본.
    죽은 팀 dir 은 런타임이 프로세스 사망 시 지우므로(실측), 재시작 후에는
    boot lead-only dir 만 남아 union 도 정확히 차단한다. 비정상 종료로 잔재가
    남으면 false-allow 가 가능하나 런타임 에러로 귀결될 뿐 — fail-open 방향.
    leadSessionId 는 resumed 세션 id 와 다른 내부 boot id 라 매칭에 못 쓴다.
    """
    cwd = os.environ.get("HARNESS_CTO_DIR") or os.getcwd()
    teams = os.path.expanduser("~/.claude/teams")
    try:
        entries = os.listdir(teams)
    except OSError:
        return None  # teams dir 자체를 못 읽음 = 미지 상태 → fail-open
    roster = None
    for entry in entries:
        cfg = os.path.join(teams, entry, "config.json")
        try:
            with open(cfg, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            continue
        members = [m for m in (data.get("members") or []) if isinstance(m, dict)]
        lead = next((m for m in members if m.get("agentType") == "team-lead"), None)
        if not lead or lead.get("cwd") != cwd:
            continue
        if roster is None:
            roster = set()
        roster |= {m.get("name") for m in members if isinstance(m.get("name"), str)}
    # cwd 매칭 config 이 하나도 없음 = 팀 자체가 없음(확정 상태) → 빈 roster.
    return roster if roster is not None else set()


def main():
    payload = read_payload()
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if tool != "SendMessage":
        allow()

    ti = _tool_input(payload)
    for raw in _recipients(ti):
        name = _bare_name(raw)
        if FORBIDDEN_RE.match(name):
            block(
                "PreToolUse", payload,
                f"SendMessage 차단 — '{raw}' 는 Claude teammate 가 아니다 "
                "(Codex developer 는 SendMessage 로 안 닿는다; 호출은 성공한 척하고 "
                "아무도 못 받는 환각 전달이 된다).\n"
                "Codex 에 보내려면 인박스 페어 브릿지를 쓰라: "
                "harness send --to codex-cto:<이 CTO 와 같은 이름> \"...\"\n"
                "designer 는 독립 세션이다: harness send --to designer-cto:<이 CTO 와 같은 이름>\n"
                "Claude 팀원 수신자는 planner/reviewer 뿐이다.",
            )

    # 죽은/미스폰 팀원에게 보내는 SendMessage 차단 — lead 재시작으로 팀원이
    # 소멸했는데 이전 대화 기억으로 메시징하면 "No agent reachable" 미궁에
    # 빠진다 (2026-07-29 rtsp-keypoint msg#552). roster 는 판단 가능할 때만
    # 검사한다 (None = fail-open).
    targets = [
        _bare_name(r) for r in _recipients(ti)
        if _bare_name(r).lower() in TEAMMATES
    ]
    if targets:
        roster = _current_roster()
        if roster is not None:
            missing = [t for t in targets if t not in roster]
            if missing:
                block(
                    "PreToolUse", payload,
                    f"SendMessage 차단 — {', '.join(missing)} 는 현 세션 팀 "
                    "roster 에 없다. in-process 팀원은 lead 재시작 시 프로세스와 "
                    "함께 소멸한다 — 이전 대화에 팀이 있었어도 지금은 없다.\n"
                    "재스폰이 필요하다 — 사용자에게 /start-project 를 치라고 하지 말고 "
                    "'reviewer 스폰할까요?' 로 묻고 턴을 끝내라. 승인 답이 시작 신호다 "
                    "(start_project_gate); 그 턴에 Agent 로 재스폰한 뒤 다시 보내라. "
                    f"(현 roster: {sorted(roster) or '없음'})",
                )
    allow()


if __name__ == "__main__":
    main()
