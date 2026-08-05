#!/usr/bin/env python3
"""start_project_spawn_nudge — /start-project 후 hybrid team 완성을 압박.

start_project_gate 가 /start-project 프롬프트에서 마커(LOG_DIR/started/<cto>.started)를
쓴다. 그 마커가 살아있는 동안 CTO 는 Claude 팀원 2명(planner/reviewer)을
**upfront** 로 전부 스폰하고 외부 Codex 세션이 살아 있어야 한다. 마커만으로는 "1명만 스폰하고
멈춤" 을 못 막는다 — role.md 지시는 advisory 라 샌다.

이 Stop 훅(=CTO 턴 종료마다)이 결정론 압박을 건다:
  - 마커 없음 → allow (start-project 턴 아님).
  - 마커 있음 & in-process team config에 planner/reviewer 2명 + Codex tab 존재
    → 완료: 마커+카운터 청소.
  - 그 외 → LOOP-GUARD block: 세션별 block 카운터(~/.harness-claude/)를
    올리며 최대 3번까지 block("Stop", ...) 으로 "나머지 지금 spawn" 압박. 3번 이후엔
    FAIL-OPEN(allow) + giveup 로그 — 절대 무한 block 하지 않는다.

in-process 카운트: Claude team config의 `members`에서 planner/reviewer를
확인한다. `one_teammate_per_role_gate.py`가 developer·역할 중복을 Agent 호출 시 차단한다.

FAIL OPEN: Orca 없음(--print/test-cto)·tab 없음·어떤 예외든 allow. 가드는 트립와이어가
아니라 압박기다 — 절대 CTO 를 가두지 않는다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block, LOG_DIR  # noqa: E402
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from harness import orca_runtime  # noqa: E402

ROLES = ("planner", "reviewer")

# start_project_gate.py 와 동일한 마커 위치/키.
STARTED_DIR = os.path.join(LOG_DIR, "started")

# 루프가드 상태(block 카운터 + giveup 로그) — task 명세대로 ~/.harness-claude/ 하위.
STATE_DIR = os.path.join(os.path.expanduser("~"), ".harness-claude", "start-project-nudge")
MAX_BLOCKS = 3


def _safe(s):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s or "")


def _cto_name():
    """start_project_gate._cto_name 과 동일: HARNESS_ROLE=cto:<name> → <name>."""
    role = os.environ.get("HARNESS_ROLE", "")
    return role.split(":", 1)[1] if ":" in role else role


def _marker_path(name):
    return os.path.join(STARTED_DIR, _safe(name) + ".started")


def _session_from_cwd(cwd):
    if not cwd:
        return None
    name = os.path.basename(os.path.normpath(cwd))
    return f"cto-{name}" if name else None


def _native_teammate_count(name):
    """Count the two required in-process roster entries for this CTO."""
    # In-process mode keeps teammates in the lead view; Claude's team config is
    # the authoritative spawn roster instead of Orca leaf count.
    cwd = os.environ.get("HARNESS_CTO_DIR", "")
    teams_dir = os.path.expanduser("~/.claude/teams")
    try:
        for entry in os.listdir(teams_dir):
            config = os.path.join(teams_dir, entry, "config.json")
            with open(config, encoding="utf-8") as fh:
                data = __import__("json").load(fh)
            members = data.get("members", [])
            if cwd and any(m.get("cwd") == cwd for m in members if isinstance(m, dict)):
                roles = {m.get("agentType") for m in members if isinstance(m, dict)}
                if {"planner", "reviewer"}.issubset(roles):
                    return 2
    except (OSError, ValueError, TypeError):
        pass
    leaves = orca_runtime.tab_leaf_count(f"cto:{name}")
    if leaves is None:
        return None
    # ★정정 (2026-07-31 실측, orca 1.4.162): Orca list 는 rail split 을 같은
    # tabId 의 별도 레코드로 보여준다. 다만 rail pane 은 자기 쉘 OSC title 을
    # 달아 lead 의 durable title 과 안 겹치고, tab_records 는 title 매치라
    # leaves 는 사실상 lead 1개다 — 이 fallback 은 0 을 돌려주고 정본은 위의
    # team config roster 경로다.
    return max(0, leaves - 2)


def _counter_path(session):
    return os.path.join(STATE_DIR, _safe(session) + ".count")


def _read_counter(session):
    try:
        with open(_counter_path(session)) as fh:
            return int(fh.read().strip() or "0")
    except Exception:
        return 0


def _write_counter(session, n):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(_counter_path(session), "w") as fh:
            fh.write(str(n) + "\n")
    except Exception:
        pass


def _clear(path):
    try:
        os.remove(path)
    except Exception:
        pass


def _codex_alive(name):
    """외부 Codex developer Orca tab 생존 여부."""
    return bool(name) and orca_runtime.role_alive(f"codex-cto:{name}")


def _log_giveup(session, count, codex_alive):
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, "giveup.log"), "a") as fh:
            fh.write(
                f"{session}\torca_splits={count}/2\tcodex={int(codex_alive)}"
                f"\tgave_up_after={MAX_BLOCKS}\n"
            )
    except Exception:
        pass


def _inbox_isolated() -> bool:
    """이번 턴이 인박스 격리(RULES §6) 중인가 — inbox_isolation_guard 와 같은 키."""
    role = os.environ.get("HARNESS_ROLE", "")
    if not role:
        return False
    slug = role.replace(":", "-").replace("/", "-")
    return os.path.exists(
        os.path.join(os.path.expanduser("~"), ".harness-claude",
                     "inbox-isolation", f"{slug}.turn")
    )


def main():
    p = read_payload()

    # 1) 마커 없음 → start-project 턴 아님 → allow.
    name = _cto_name()
    marker = _marker_path(name)
    if not os.path.exists(marker):
        allow()

    # 1.5) 인박스 격리 턴이면 압박하지 않는다 (2026-08-04 실사고 — 교착).
    # add-cto 가 시작 마커를 시딩하게 된 뒤로, CTO 가 데몬 nudge 로 인박스를 읽은
    # 턴에서도 이 훅이 "팀 spawn 하라" 며 Stop 을 block 한다. 그런데 같은 턴의
    # Agent/Skill 호출은 inbox_isolation_guard 가 §6 으로 차단한다 — 즉 훅 둘이
    # 서로 반대를 요구해 CTO 가 빠져나갈 수 없다 (실측: perf-eval-gen 이 spawn
    # 2회 시도 → 2회 차단 → Stop 재발화 무한). §6(프롬프트 인젝션 방지)이 상위
    # 안전 규칙이므로 여기서 물러난다. 격리는 한 턴짜리라 다음 턴에 다시 압박한다.
    if _inbox_isolated():
        allow("Stop", p, reason="인박스 격리 턴 — §6 우선, spawn 압박 보류")

    # 2) in-process team roster 확인 (없으면 legacy Orca leaf fallback/fail-open).
    session = _session_from_cwd(p.get("cwd") or p.get("workingDirectory") or os.getcwd())
    if not session:
        allow()
    count = _native_teammate_count(name)
    if count is None:
        allow()  # Orca 없음(--print/test-cto) 또는 tab 없음 → fail-open
    codex_alive = _codex_alive(name)

    # 3) in-process Claude roster 2명 + 외부 Codex → 완료.
    if count >= 2 and codex_alive:
        _clear(marker)
        _clear(_counter_path(session))
        allow("Stop", p, reason=f"spawn 완료 Claude roster {count}/2 + Codex — 마커 청소")

    # 4) 미완 → 루프가드 block (최대 MAX_BLOCKS), 그 뒤 fail-open.
    c = _read_counter(session)
    if c < MAX_BLOCKS:
        _write_counter(session, c + 1)
        block(
            "Stop", p,
            f"hybrid spawn 미완 — Claude roster {count}/2, Codex tab "
            f"{'alive' if codex_alive else 'missing'}. planner→reviewer를 upfront "
            "spawn하고 codex-cto-<name>은 add-cto로 준비되어 있어야 한다. "
            "Codex를 여기서 자동 시작하지 마라.",
        )

    # 3번 압박했는데도 미완 → 무한 block 금지, fail-open + giveup 로그.
    _log_giveup(session, count, codex_alive)
    allow(
        "Stop", p,
        reason=f"loop-guard 소진({MAX_BLOCKS}) Claude roster {count}/2 "
        f"codex={int(codex_alive)} — fail-open",
    )


if __name__ == "__main__":
    main()
