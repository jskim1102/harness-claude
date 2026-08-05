"""Small, fail-closed adapter around Orca's public terminal/project CLI.

The harness never persists terminal handles: Orca may replace them after a
runtime restart.  Durable identities are exact harness tab titles plus the
owning worktree path.  A Claude Agent Team creates native Orca splits under
the lead tab, so callers must resolve the tab's root leaf instead of assuming
that one title maps to one terminal record.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Any

from harness import orca_rpc

ORCA_TIMEOUT_SEC = 5.0
_KEBAB = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_TITLE_RE = re.compile(
    rf"^harness:(?:ceo|cto:(?P<name>{_KEBAB}):(?P<member>lead|codex|designer))$"
)

_cache_at = 0.0
_cache: list[dict[str, Any]] = []


def executable() -> str:
    configured = os.environ.get("ORCA_CLI_COMMAND", "")
    if configured:
        return configured
    if os.environ.get("ORCA_DEV_REPO_ROOT") and shutil.which("orca-dev"):
        return "orca-dev"
    if sys.platform.startswith("linux") and shutil.which("orca-ide"):
        return "orca-ide"
    return shutil.which("orca") or "orca"


def run(
    args: list[str],
    *,
    timeout: float = ORCA_TIMEOUT_SEC,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [executable(), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _json_result(args: list[str], *, timeout: float = ORCA_TIMEOUT_SEC) -> dict:
    try:
        proc = run([*args, "--json"], timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if proc.returncode != 0:
        return {}
    try:
        payload = json.loads(proc.stdout)
        result = payload.get("result")
    except (TypeError, ValueError):
        return {}
    return result if isinstance(result, dict) else {}


def invalidate_terminal_cache() -> None:
    global _cache_at
    _cache_at = 0.0


def _rpc_terminal_records() -> list[dict[str, Any]] | None:
    """런타임 유닉스 소켓으로 터미널 목록을 받는다. 실패하면 None → CLI 폴백.

    왜 (2026-07-28): `orca terminal list` 는 호출마다 AppImage(Electron) 를 새로
    마운트해서 뜬다 — 실측 706ms/회. harnessd 가 1초 주기로 폴링하므로 하루
    ~72,000 회, 코어 0.7개를 상시 태우고 있었다(journal 의 `mount_orca` 이벤트
    시간당 ~3,000건이 그 흔적). 같은 데이터가 런타임 소켓에서 0.4ms 에 온다
    (1,600x). RPC 가 안 되면 아무것도 바뀌지 않고 기존 CLI 경로로 내려간다.

    테스트 더블(ORCA_CLI_COMMAND/ORCA_DEV_REPO_ROOT)이 걸려 있으면 RPC 를 쓰지
    않는다 — 스텁 CLI 를 우회해 실 런타임 상태를 읽으면 스모크가 거짓말을 한다.
    """
    if os.environ.get("ORCA_CLI_COMMAND") or os.environ.get("ORCA_DEV_REPO_ROOT"):
        return None
    try:
        result = orca_rpc.call("terminal.list", {"limit": 500}, timeout=ORCA_TIMEOUT_SEC)
    except (orca_rpc.OrcaRpcError, OSError, ValueError):
        return None
    records = result.get("terminals")
    return records if isinstance(records, list) else None


def terminals(*, max_age: float = 0.25) -> list[dict[str, Any]]:
    global _cache_at, _cache
    now = time.monotonic()
    if now - _cache_at < max_age:
        return [dict(record) for record in _cache]
    records = _rpc_terminal_records()
    if records is None:
        result = _json_result(["terminal", "list", "--limit", "500"], timeout=20)
        records = result.get("terminals")
    if not isinstance(records, list):
        _cache_at = now
        _cache = []
        return []
    _cache = [record for record in records if isinstance(record, dict)]
    _cache_at = now
    return [dict(record) for record in _cache]


def _live(record: dict[str, Any]) -> bool:
    return (
        record.get("connected") is True
        and record.get("writable") is True
        and isinstance(record.get("handle"), str)
        and record["handle"].startswith("term_")
    )


# env seam: 훅·데몬은 별도 프로세스라 in-process 스텁이 안 닿는다. 가짜 Orca 로
# 도는 테스트가 keeper 도 같이 가짜로 놓을 수 있어야 판정이 vacuous 해지지 않는다.
KEEPER_DIR = os.environ.get("HARNESS_KEEPER_DIR") or os.path.expanduser(
    "~/.harness-claude/keeper"
)

# 세션 키(logical_sessions 반환값) → keeper 소켓 이름.
_KEEPER_SUFFIX = {"cto": "lead", "codex-cto": "codex", "designer-cto": "designer"}


def keeper_sock(session_key: str) -> str:
    """'cto-foo' → keeper/cto-foo-lead.sock 처럼 세션 키를 소켓 경로로 옮긴다."""
    if session_key == "ceo":
        name = "ceo"
    else:
        for prefix, suffix in _KEEPER_SUFFIX.items():
            head = prefix + "-"
            if session_key.startswith(head):
                name = f"cto-{session_key[len(head):]}-{suffix}"
                break
        else:
            return ""
    return os.path.join(KEEPER_DIR, f"{name}.sock")


def keeper_alive(session_key: str) -> bool:
    """그 역할의 keeper 소켓이 있는가 = 에이전트 프로세스가 실재하는가.

    **왜 Orca 레코드만으로는 부족한가 (2026-08-02 실사고).** Orca 런타임과 UI 가
    갈라지면 이미 죽은 세션의 탭이 런타임 목록에 `connected=true` 로 계속 남는다
    (`terminal close` 는 `tab_not_found` 로 거부, UI 엔 안 보임). 그 상태에서
    대시보드는 죽은 CTO 를 "활성" 으로 읽고 **`복구` 버튼까지 띄웠다** — 정지하려던
    CTO 를 되살리는 방향이다. keeper 소켓은 `stop-cto` 가 지우므로 그 유령과
    실재를 가른다.

    파일 존재만 본다(연결 시도 X). dtach 소켓에 붙었다 떼면 실 세션에 winch/redraw
    부작용이 생길 수 있어서, 살아있는 것을 건드리지 않는 쪽을 택했다. keeper 가
    비정상 종료해 파일만 남는 경우는 이 검사를 통과하지만, 그건 지금과 같은 수준일
    뿐 더 나빠지지 않는다.
    """
    sock = keeper_sock(session_key)
    return bool(sock) and os.path.exists(sock)


def role_title(role: str) -> str | None:
    if role == "ceo":
        return "harness:ceo"
    match = re.fullmatch(rf"cto:({_KEBAB})", role)
    if match:
        return f"harness:cto:{match.group(1)}:lead"
    match = re.fullmatch(rf"codex-cto:({_KEBAB})", role)
    if match:
        return f"harness:cto:{match.group(1)}:codex"
    match = re.fullmatch(rf"designer-cto:({_KEBAB})", role)
    if match:
        return f"harness:cto:{match.group(1)}:designer"
    return None


def tab_records(title: str) -> list[dict[str, Any]]:
    """Return the leaves for exactly one live tab with ``title``.

    Duplicate tabs with the same durable title are ambiguous and therefore
    resolve to an empty list.  Only the pane renamed by the harness carries the
    durable title: rail split panes get their own shell OSC title (실측
    2026-07-31, orca 1.4.162), so this normally returns exactly one leaf.
    """
    matches = [r for r in terminals() if _live(r) and r.get("title") == title]
    tab_ids = {r.get("tabId") for r in matches if isinstance(r.get("tabId"), str)}
    if len(matches) == 1 and not tab_ids:
        # Compatibility with runtimes/test doubles predating native split IDs.
        return matches
    if len(tab_ids) != 1:
        return []
    tab_id = next(iter(tab_ids))
    return [r for r in matches if r.get("tabId") == tab_id]


def role_record(title: str) -> dict[str, Any] | None:
    """The single live pane carrying ``title``, or None (fail closed).

    leafId==tabId 로 root leaf 를 고르던 판정 제거 (2026-07-31, orca 1.4.162
    실측): 단일 pane 탭도 leafId 가 tabId 와 다른 uuid 라 그 조건은 절대 참이
    되지 않는다 — 동작하는 가드처럼 읽히는 죽은 코드였고, 실제로 해석을
    성립시킨 것은 "타이틀 매치 leaf 가 정확히 1개" 뿐이었다.
    """
    records = tab_records(title)
    return records[0] if len(records) == 1 else None


def resolve_role(role: str) -> dict[str, Any] | None:
    title = role_title(role)
    return role_record(title) if title else None


def _session_key(role: str) -> str:
    """resolve_role 이 받는 role 표기 → logical_sessions 키 (keeper 조회용)."""
    if role == "ceo":
        return "ceo"
    for prefix in ("codex-cto:", "designer-cto:", "cto:"):
        if role.startswith(prefix):
            return prefix[:-1] + "-" + role[len(prefix):] if prefix != "cto:" \
                else "cto-" + role[len("cto:"):]
    return role


def role_alive(role: str) -> bool:
    """Orca 레코드 ∧ keeper 실재. 유령 탭을 살아있다고 세지 않는다 (keeper_alive 참조)."""
    return resolve_role(role) is not None and keeper_alive(_session_key(role))


def role_handle(role: str) -> str | None:
    record = resolve_role(role)
    return record.get("handle") if record else None


def role_worktree_path(role: str) -> str | None:
    record = resolve_role(role)
    if not record:
        return None
    path = record.get("worktreePath")
    if isinstance(path, str) and path:
        return path
    worktree_id = record.get("worktreeId")
    if isinstance(worktree_id, str) and "::" in worktree_id:
        candidate = worktree_id.split("::", 1)[1].split("::workspace:", 1)[0]
        if candidate.startswith("/"):
            return candidate
    return None


def tab_leaf_count(role: str) -> int | None:
    title = role_title(role)
    if not title:
        return None
    records = tab_records(title)
    return len(records) if records else None


def role_idle(role: str) -> bool:
    record = resolve_role(role)
    if not record:
        return False
    preview = record.get("preview")
    if not isinstance(preview, str):
        return False
    busy_markers = (
        "esc to interrupt",
        "Esc to interrupt",
        "Do you want",
        "Permission",
        "Working",
        "Cascading",
    )
    return not any(marker in preview for marker in busy_markers)


def send_role(role: str, text: str) -> bool:
    handle = role_handle(role)
    if not handle:
        return False
    try:
        proc = run(
            ["terminal", "send", "--terminal", handle, "--text", text, "--enter", "--json"],
            timeout=ORCA_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def orca_sessions() -> set[str]:
    """Orca 레코드**만** 본 세션 키 (keeper 게이트 전). 유령 탐지용 원재료."""
    return _scan_titles()


def drift() -> dict[str, list[str]]:
    """탭과 프로세스가 어긋난 것들 — 두 방향 다 낸다.

    `ghost_tab`   Orca 엔 있는데 keeper 없음 = 죽은 세션의 탭 껍데기.
                  대시보드가 이걸 "활성" 으로 읽어 죽은 CTO 에 복구 버튼을 띄웠다
                  (2026-08-02). 지금은 판정에서 걸러지지만, 걸러진다고 사라지진
                  않는다 — Orca 재시작 전까지 목록에 남는다.
    `orphan_agent` keeper 는 있는데 Orca 탭 없음 = **화면 없이 도는 에이전트**.
                  이쪽이 더 위험하다: 사용자 눈에 안 보이는데 파일을 쓰고 토큰을
                  태운다. 붙을 화면이 없으니 정지도 대시보드로 안 된다.
    """
    tabs = orca_sessions()
    keepers = set()
    try:
        for entry in os.listdir(KEEPER_DIR):
            if not entry.endswith(".sock"):
                continue
            base = entry[: -len(".sock")]
            if base == "ceo":
                keepers.add("ceo")
            elif base.startswith("cto-"):
                stem = base[len("cto-"):]
                for suffix, prefix in (("-lead", "cto-"), ("-codex", "codex-cto-"),
                                       ("-designer", "designer-cto-")):
                    if stem.endswith(suffix):
                        keepers.add(prefix + stem[: -len(suffix)])
                        break
    except OSError:
        pass
    return {
        "ghost_tab": sorted(tabs - keepers),
        "orphan_agent": sorted(keepers - tabs),
    }


def _scan_titles() -> set[str]:
    """Orca 터미널 목록 → 세션 키. keeper 게이트는 여기서 걸지 않는다."""
    alive: set[str] = set()
    seen_tabs: set[str] = set()
    for record in terminals():
        if not _live(record):
            continue
        title = record.get("title")
        handle = record.get("handle")
        tab_id = record.get("tabId") or handle
        if not isinstance(title, str) or not isinstance(tab_id, str) or tab_id in seen_tabs:
            continue
        match = _TITLE_RE.fullmatch(title)
        if not match and title != "harness:ceo":
            continue
        seen_tabs.add(tab_id)
        if title == "harness:ceo":
            alive.add("ceo")
        elif match and match.group("member") == "lead":
            alive.add(f"cto-{match.group('name')}")
        elif match and match.group("member") == "designer":
            alive.add(f"designer-cto-{match.group('name')}")
        elif match:
            alive.add(f"codex-cto-{match.group('name')}")
    return alive


def logical_sessions() -> set[str]:
    """살아있는 하네스 세션 = **Orca 레코드 ∧ keeper 실재**.

    유령 탭(런타임엔 남아있고 프로세스는 죽은 것)을 "살아있음" 으로 세면 대시보드가
    죽은 CTO 에 복구·정지 버튼을 띄운다 (2026-08-02 실사고).
    """
    return {key for key in _scan_titles() if keeper_alive(key)}
