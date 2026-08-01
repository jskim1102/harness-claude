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


def role_alive(role: str) -> bool:
    return resolve_role(role) is not None


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


def logical_sessions() -> set[str]:
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
