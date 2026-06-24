import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from harness.cli import _discover_roles
from harness.db import HARNESS_HOME, connect

# TIMEOUT BUDGET: every subprocess.run() in this module uses timeout=2.0 to
# prevent a single hung tmux call from blocking the daemon forever. On
# TimeoutExpired we log a warning and return a safe default (False / empty / None).
POLL_INTERVAL_SEC = 1.0
WAKE_COOLDOWN_SEC = 10.0  # base re-wake window per role
MAX_WAKE_BACKOFF_SEC = 300.0  # cap per-role backoff when an inbox never drains
TMUX_TIMEOUT_SEC = 2.0
BUSY_MARKERS = (
    "esc to interrupt",
    "Esc to interrupt",
    "Do you want",
    "Permission",
    "❯ 1.",
)

CEO_INBOX_FLAG = HARNESS_HOME / "inbox-ceo.flag"

# Autopilot stall detector (spec: docs/superpowers/specs/2026-06-19-harnessd-stall-detector-design.md).
# A CTO session is "stalled" when its pane is idle AND no project file changed AND
# the CTO sent no surface message AND tasks.md still has incomplete items — for
# STALL_SEC. Busy pane / recent file change / recent outbound msg all reset it, so
# slow-but-working builds and gate-waits are never flagged. Surface-only to CEO.
STALL_SEC = 300.0                 # idle+무진행 임계 (5분)
STALL_SCAN_THROTTLE_SEC = 30.0    # find 진행스캔 최소 간격
STALL_SCAN_WINDOW_SEC = 60.0      # find -mmin 창 (≥ throttle 라 스캔 사이 변경 안 놓침)
STALL_BACKOFF_MAX_SEC = 1200.0    # 재알림 backoff 상한 (20분)
STALL_EXCLUDE_DIRS = (".venv", "node_modules", ".git", "dist", "__pycache__", ".pytest_cache")
_TASK_INCOMPLETE_RE = re.compile(r"^\s*-\s*\[[ !]\]")

# Module-level state for CEO-less mode warning suppression and pane caching.
_ceo_warned = False
_claude_pane_cache: dict[str, str] = {}
# Suppress repeat "skip" log spam per role.
_skip_logged: set[str] = set()

# Parse the cto name out of a [system] discovery notification body.
_CTO_NAME_RE = re.compile(r"이름:\s*(\S+)")

# kebab-case slug (matches run.sh add-cto validation: ^[a-z0-9]+(-[a-z0-9]+)*$).
# Session names and roles that fail this are never trusted into a tmux -t arg
# or relayed into the CEO's shell template — a hostile session name like
# 'cto-x";touch /tmp/PWN;"' must not survive enumeration.
_KEBAB = r"[a-z0-9]+(?:-[a-z0-9]+)*"
_CTO_SESSION_RE = re.compile(rf"^cto-{_KEBAB}\Z")
_ROLE_RE = re.compile(rf"^(?:ceo|cto:{_KEBAB})\Z")


def _setup_log() -> logging.Logger:
    HARNESS_HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
    log = logging.getLogger("harnessd")
    log.setLevel(logging.INFO)
    h = RotatingFileHandler(
        HARNESS_HOME / "daemon.log", maxBytes=10 * 1024 * 1024, backupCount=3
    )
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    # echo to stderr so it shows up in the tmux window too
    log.addHandler(logging.StreamHandler(sys.stderr))
    return log


def _find_by_pane_title(role: str, session: str | None = None) -> str | None:
    """Look for a pane whose title matches `role`.
    Returns the tmux target 'session:window.pane' or None.

    SECURITY: pane titles are attacker-settable (`tmux select-pane -T`), so any
    teammate could title its own pane 'cto:victim' to hijack the victim's wakes
    if we matched titles across ALL sessions. When `session` is given, only
    panes inside that session are considered, so a title match can't cross the
    session boundary; the caller scopes cto:<name> to its own 'cto-<name>'."""
    cmd = ["tmux", "list-panes"]
    if session is not None:
        cmd += ["-t", session]
    else:
        cmd += ["-a"]
    cmd += ["-F", "#{session_name}:#{window_index}.#{pane_index}\t#{pane_title}"]
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logging.getLogger("harnessd").warning("tmux list-panes timed out")
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        target, _, title = line.partition("\t")
        if title.strip() == role:
            return target
    return None


def _find_claude_pane(session: str) -> str | None:
    """Find pane in `session` running the 'claude' command.
    Returns target string 'session:window.pane' or None. Cached per session."""
    if session in _claude_pane_cache:
        cached = _claude_pane_cache[session]
        # Quick validation: if pane is still alive, use it.
        if _target_alive(cached):
            return cached
        # Stale cache — drop it.
        _claude_pane_cache.pop(session, None)
    try:
        r = subprocess.run(
            ["tmux", "list-panes", "-t", session, "-F",
             "#{window_index}.#{pane_index}\t#{pane_current_command}"],
            capture_output=True, text=True, timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logging.getLogger("harnessd").warning(
            "tmux list-panes timed out session=%s", session
        )
        return None
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        pane_addr, _, cmd = line.partition("\t")
        if cmd.strip() == "claude":
            target = f"{session}:{pane_addr}"
            _claude_pane_cache[session] = target
            return target
    return None


def _resolve_target(role: str) -> str | None:
    """Resolve role to a tmux target, or None if the role is not a valid
    routable identity. Order:
       1. env override HARNESS_TMUX_MAP_<safe-role>
       2. for cto:<name>: resolve to session 'cto-<name>', preferring the pane
          actually running 'claude' (_find_claude_pane); a title lookup is only
          used as a fallback and is SCOPED to that session so an attacker can't
          steal the wake by titling its own pane 'cto:victim'. The bare-session
          fallback is returned as an EXACT target ('=cto-<name>') so tmux prefix
          matching can't misroute the wake to 'cto-<name>-extra'.
       3. for ceo: pane title lookup, else session 'ceo'.

    SECURITY: role is a DB-stored, partly attacker-influenceable to_role. It is
    validated against ^(ceo|cto:[a-z0-9]+(-[a-z0-9]+)*)$ before any tmux -t use,
    so a dash-leading target like '-X' (which tmux would otherwise silently
    treat as a flag and fall back to the active pane) can never reach a -t arg.
    """
    if not _ROLE_RE.match(role):
        return None
    safe = role.upper().replace(":", "_").replace("-", "_")
    env_key = f"HARNESS_TMUX_MAP_{safe}"
    if env_key in os.environ:
        return os.environ[env_key]
    if role.startswith("cto:"):
        session = "cto-" + role[len("cto:"):]
        claude_pane = _find_claude_pane(session)
        if claude_pane:
            return claude_pane
        # Fallback: a pane explicitly titled with the role, but ONLY inside that
        # CTO's own session (never a cross-session match).
        by_title = _find_by_pane_title(role, session=session)
        if by_title:
            return by_title
        # Exact-match prefix ('='): tmux prefix-matches a bare session name, so
        # an absent 'cto-name' would otherwise route wakes to 'cto-name-extra'.
        return "=" + session
    # role == 'ceo'
    by_title = _find_by_pane_title(role)
    if by_title:
        return by_title
    return "ceo"


def _target_alive(target: str) -> bool:
    """Check that target (session or session:window.pane) exists.
    tmux display-message returns rc=0 even for a missing -t target (silently
    falls back to the current/active pane). The actual existence signal is
    whether stdout contains a real pane id (starts with '%').

    SECURITY: a dash-leading target (e.g. '-X') is parsed by tmux's getopt as a
    flag, and the unresolved -t then silently falls back to the active pane
    (rc=0, real '%id') — making this 'alive' check wrongly pass and misrouting
    /inbox keystrokes. Reject '-'-leading (and empty) targets up front so such a
    string can never reach a tmux -t argument."""
    if not target or target.startswith("-"):
        return False
    try:
        r = subprocess.run(
            ["tmux", "display-message", "-t", target, "-p", "#{pane_id}"],
            capture_output=True, text=True, timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logging.getLogger("harnessd").warning(
            "tmux display-message timed out target=%s", target
        )
        return False
    return r.returncode == 0 and r.stdout.strip().startswith("%")


def _pane_idle(session: str) -> bool:
    if not session or session.startswith("-"):
        return False
    try:
        r = subprocess.run(
            ["tmux", "capture-pane", "-t", session, "-p", "-S", "-30"],
            capture_output=True,
            text=True,
            timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logging.getLogger("harnessd").warning(
            "tmux capture-pane timed out session=%s", session
        )
        return False
    if r.returncode != 0:
        return False
    tail = r.stdout
    return not any(m in tail for m in BUSY_MARKERS)


def _send_inbox(session: str, log: logging.Logger) -> bool:
    if not session or session.startswith("-"):
        log.warning("refusing send-keys to dash-leading target=%s", session)
        return False
    try:
        r = subprocess.run(
            ["tmux", "send-keys", "-t", session, "/inbox", "Enter"],
            capture_output=True,
            text=True,
            timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        log.warning("send-keys timed out session=%s", session)
        return False
    if r.returncode != 0:
        log.warning("send-keys failed session=%s err=%s", session, r.stderr.strip())
        return False
    return True


def _list_cto_sessions() -> set[str]:
    """Return set of tmux session names matching 'cto-<kebab>'.
    Only kebab-case names (^cto-[a-z0-9]+(-[a-z0-9]+)*$) are returned: tmux
    accepts session names containing quotes/semicolons/spaces, and these names
    are later parsed into a cto_name that the CEO interpolates into a shell
    `tmux ... attach -t cto-<NAME>` command. A name that can break out of that
    quoting = command injection in the CEO's context, so reject it here at the
    source rather than trusting any 'cto-*' session."""
    try:
        r = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True, text=True, timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logging.getLogger("harnessd").warning("tmux list-sessions timed out")
        return set()
    if r.returncode != 0:
        return set()
    return {
        name
        for line in r.stdout.splitlines()
        if (name := line.strip()) and _CTO_SESSION_RE.match(name)
    }


def _session_cwd(session: str) -> str:
    """Best-effort fetch of pane_current_path for the session's active pane."""
    try:
        r = subprocess.run(
            ["tmux", "display-message", "-t", session, "-p", "#{pane_current_path}"],
            capture_output=True, text=True, timeout=TMUX_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        logging.getLogger("harnessd").warning(
            "tmux display-message (cwd) timed out session=%s", session
        )
        return "(unknown)"
    return r.stdout.strip() if r.returncode == 0 else "(unknown)"


def _ceo_target_alive() -> bool:
    """True iff a CEO target exists (pane titled 'ceo' or session 'ceo')."""
    by_title = _find_by_pane_title("ceo")
    if by_title and _target_alive(by_title):
        return True
    return _target_alive("ceo")


def _ceo_already_notified(cto_name: str) -> bool:
    """Idempotent guard: has harnessd already inserted a [system] discovery
    notification for this cto in the msg table? Survives daemon restarts."""
    with connect() as c:
        row = c.execute(
            "SELECT 1 FROM msg "
            "WHERE from_role='harnessd' AND to_role='ceo' "
            "  AND body LIKE ? LIMIT 1",
            (f"%이름: {cto_name}\n%",),
        ).fetchone()
    return row is not None


def discover_ctos(log: logging.Logger) -> None:
    """Detect cto-* sessions; insert a [system] notification to CEO for any
    that haven't been announced yet. Idempotent across daemon restarts by
    checking the msg table itself — no separate 'known' set needed."""
    current = _list_cto_sessions()
    for session in sorted(current):
        cto_name = session[len("cto-"):]
        if _ceo_already_notified(cto_name):
            continue
        cwd = _session_cwd(session)
        body = (
            f"[system] 새 CTO 감지됨\n"
            f"  이름: {cto_name}\n"
            f"  tmux 세션: {session}\n"
            f"  디렉토리: {cwd}\n"
            f"\n"
            f"보시려면 사용자가 새 터미널에서:\n"
            f"  ./run.sh attach {session}\n"
            f"(CEO/CTO 터미널 독립 운영 — observe 폐기)"
        )
        with connect() as c:
            c.execute(
                "INSERT INTO msg (from_role, to_role, body) VALUES (?, ?, ?)",
                ("harnessd", "ceo", body),
            )
        log.info("new CTO discovered: %s (cwd=%s)", session, cwd)


def reap_stale_cto_notifications(log: logging.Logger) -> None:
    """Reconcile the add-only discovery flow with CTO removal: mark-read any
    unread [system] discovery notification whose CTO is gone (directory removed
    AND tmux session not alive). Without this, deleting a CTO leaves its
    discovery notification orphaned in the CEO inbox forever. Mark-read keeps
    the row (audit) and is consistent with how `harness inbox` drains."""
    present = {r["name"] for r in _discover_roles() if r["kind"] == "cto"}
    alive = _list_cto_sessions()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as c:
        rows = c.execute(
            "SELECT id, body FROM msg "
            "WHERE from_role='harnessd' AND to_role='ceo' AND read_at IS NULL "
            "  AND body LIKE '[system] 새 CTO 감지됨%'"
        ).fetchall()
        for row in rows:
            m = _CTO_NAME_RE.search(row["body"])
            if not m:
                continue
            name = m.group(1)
            if name in present or f"cto-{name}" in alive:
                continue  # dir present or session alive -> still real, keep
            c.execute(
                "UPDATE msg SET read_at=? WHERE id=? AND read_at IS NULL",
                (now, row["id"]),
            )
            log.info(
                "reaped stale CTO discovery notif: %s (dir gone, session dead)",
                name,
            )


def _update_ceo_flag(has_unread: bool) -> None:
    """Touch ~/.harness-claude/inbox-ceo.flag while CEO has unread messages;
    remove it once drained. Lets a human (or external script) detect at a
    glance whether CEO-less mode has pending work."""
    try:
        if has_unread:
            HARNESS_HOME.mkdir(parents=True, exist_ok=True, mode=0o700)
            CEO_INBOX_FLAG.touch(exist_ok=True)
        else:
            try:
                CEO_INBOX_FLAG.unlink()
            except FileNotFoundError:
                pass
    except OSError:
        # Flag file is best-effort; never let it crash the daemon.
        pass


def _parse_tasks_incomplete(text: str) -> int:
    """Count incomplete task lines ('- [ ]' or '- [!]'). Completed '[✅]'/'[x]'
    excluded. Pure — unit-tested in smoke."""
    return sum(1 for line in text.splitlines() if _TASK_INCOMPLETE_RE.match(line))


def _first_incomplete_line(text: str) -> str:
    """First '- [ ]'/'- [!]' line (trimmed, capped) for the alert body; '(불명)' if none."""
    for line in text.splitlines():
        if _TASK_INCOMPLETE_RE.match(line):
            return line.strip()[:120]
    return "(불명)"


def _stall_verdict(idle: bool, has_surface: bool, incomplete: int, elapsed: float) -> bool:
    """Deterministic stall decision from resolved signals. Pure — unit-tested.
    Stall = pane idle AND no recent surface AND tasks incomplete AND idle ≥ STALL_SEC.
    (Busy pane / recent file change feed `elapsed` upstream by resetting last_progress.)"""
    return idle and not has_surface and incomplete > 0 and elapsed >= STALL_SEC


def _project_recent_change(cwd: str, log: logging.Logger) -> bool:
    """True if any project file (excluding heavy dirs) changed within
    STALL_SCAN_WINDOW_SEC. FAIL-OPEN to True (assume progress) on any error so a
    broken scan never falsely flags a stall."""
    if not cwd or cwd == "(unknown)" or cwd.startswith("-") or not os.path.isdir(cwd):
        return True
    mins = max(1, int(STALL_SCAN_WINDOW_SEC // 60))
    names: list[str] = []
    for d in STALL_EXCLUDE_DIRS:
        if names:
            names.append("-o")
        names += ["-name", d]
    cmd = (
        ["find", cwd, "("] + names + [")", "-prune", "-o",
         "-type", "f", "-mmin", f"-{mins}", "-print", "-quit"]
    )
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TMUX_TIMEOUT_SEC)
    except (OSError, subprocess.TimeoutExpired):
        log.warning("stall find scan failed/timeout cwd=%s", cwd)
        return True
    if r.returncode != 0:
        return True
    return bool(r.stdout.strip())


def _cto_recent_surface(name: str, cutoff_utc: str) -> bool:
    """True if cto:<name> sent any message after cutoff (UTC 'YYYY-MM-DD HH:MM:SS').
    FAIL-OPEN to True (assume surfaced) on error → never falsely flag."""
    try:
        with connect() as c:
            row = c.execute(
                "SELECT 1 FROM msg WHERE from_role=? AND created > ? LIMIT 1",
                (f"cto:{name}", cutoff_utc),
            ).fetchone()
        return row is not None
    except Exception:
        return True


def _stall_already_alerted(name: str) -> bool:
    """Unread stall alert for this cto already in CEO inbox? Dedup guard (survives
    daemon restarts). FAIL-OPEN to True → never double-insert."""
    try:
        with connect() as c:
            row = c.execute(
                "SELECT 1 FROM msg WHERE from_role='harnessd' AND to_role='ceo' "
                "AND read_at IS NULL AND body LIKE ? LIMIT 1",
                (f"[system] cto:{name} 무진행 의심%",),
            ).fetchone()
        return row is not None
    except Exception:
        return True


def _detect_one_stall(session, now, stall_state, log):
    name = session[len("cto-"):]
    st = stall_state.setdefault(
        session, {"last_progress": now, "last_scan": 0.0, "next_alert": 0.0, "count": 0}
    )

    cwd = _session_cwd(session)
    tasks_text = ""
    if cwd and cwd != "(unknown)":
        tp = os.path.join(cwd, "specs", "tasks.md")
        if os.path.isfile(tp):
            try:
                tasks_text = Path(tp).read_text(encoding="utf-8")
            except OSError:
                tasks_text = ""
    incomplete = _parse_tasks_incomplete(tasks_text)

    def _reset():
        st["last_progress"] = now
        st["count"] = 0
        st["next_alert"] = 0.0

    # No tasks.md or build complete → no stall possible.
    if incomplete <= 0:
        _reset()
        return
    # Busy pane = actively working.
    if not _pane_idle(session):
        _reset()
        return
    # Idle: throttled file-change scan; any recent change = progress.
    if now - st["last_scan"] >= STALL_SCAN_THROTTLE_SEC:
        st["last_scan"] = now
        if _project_recent_change(cwd, log):
            _reset()
            return

    elapsed = now - st["last_progress"]
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=STALL_SEC)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )
    has_surface = _cto_recent_surface(name, cutoff)
    if not _stall_verdict(True, has_surface, incomplete, elapsed):
        return

    # Stall confirmed — backoff + dedup before surfacing.
    if now < st["next_alert"]:
        return
    next_backoff = min(STALL_SEC * (2 ** st["count"]), STALL_BACKOFF_MAX_SEC)
    if _stall_already_alerted(name):
        st["next_alert"] = now + next_backoff  # already unread; don't duplicate
        return

    body = (
        f"[system] cto:{name} 무진행 의심\n"
        f"  {int(elapsed // 60)}분간 pane idle + 파일변경 0 + surface 없음. "
        f"tasks.md 미완 {incomplete}개.\n"
        f"  다음 미완: {_first_incomplete_line(tasks_text)}\n"
        f"  의도된 대기면 무시. 아니면 확인:\n"
        f"    ./run.sh attach {session}"
    )
    try:
        with connect() as c:
            c.execute(
                "INSERT INTO msg (from_role, to_role, body) VALUES ('harnessd', 'ceo', ?)",
                (body,),
            )
    except Exception:
        log.exception("stall insert failed cto=%s", name)
        return
    st["count"] += 1
    st["next_alert"] = now + next_backoff
    log.info("stall surfaced: cto=%s elapsed=%.0fs incomplete=%d", name, elapsed, incomplete)


def detect_stalls(log: logging.Logger, stall_state: dict) -> None:
    """Per active CTO session, surface a silent autopilot stall to CEO inbox.
    FAIL-OPEN per session — any error skips that session, never crashes the daemon."""
    sessions = _list_cto_sessions()
    for gone in [s for s in stall_state if s not in sessions]:
        stall_state.pop(gone, None)
    now = time.monotonic()
    for session in sorted(sessions):
        try:
            _detect_one_stall(session, now, stall_state, log)
        except Exception:
            log.exception("stall check error session=%s", session)


def tick(
    log: logging.Logger,
    last_woken: dict[str, float],
    last_unread: dict[str, int],
    backoff: dict[str, float],
) -> int:
    """One poll iteration. Returns number of wakes sent."""
    global _ceo_warned
    sent = 0
    now = time.monotonic()
    with connect() as c:
        rows = c.execute(
            "SELECT to_role, COUNT(*) AS n FROM msg "
            "WHERE read_at IS NULL GROUP BY to_role"
        ).fetchall()
    unread = {r["to_role"]: r["n"] for r in rows}
    targets = list(unread.keys())

    # Drop wake/backoff state for roles whose inbox is now empty (drained or
    # gone) so a healthy role never carries a stale backoff.
    for stale in list(last_woken):
        if stale not in unread:
            last_woken.pop(stale, None)
            last_unread.pop(stale, None)
            backoff.pop(stale, None)

    _update_ceo_flag("ceo" in unread)

    for role in targets:
        # CEO-less mode short-circuit: if CEO target doesn't exist, don't
        # spam send_keys / skip-logs. Log once, then stay silent.
        if role == "ceo" and not _ceo_target_alive():
            if not _ceo_warned:
                log.info(
                    "ceo target absent (CEO-less mode); messages will sit "
                    "unread until a CEO process drains them"
                )
                _ceo_warned = True
            continue
        # If a previously-absent CEO comes back, allow future warnings again.
        if role == "ceo" and _ceo_warned:
            _ceo_warned = False

        # Per-role exponential backoff: a role whose inbox never drains (e.g. a
        # wedged session that can't run /inbox) would otherwise be woken every
        # WAKE_COOLDOWN_SEC forever. Back off until it drains.
        cooldown = min(WAKE_COOLDOWN_SEC * backoff.get(role, 1.0), MAX_WAKE_BACKOFF_SEC)
        if now - last_woken.get(role, 0.0) < cooldown:
            continue  # within (backed-off) cooldown, stay quiet
        target = _resolve_target(role)
        if target is None:
            if role not in _skip_logged:
                log.info("skip: invalid/unroutable role=%s", role)
                _skip_logged.add(role)
            continue
        if not _target_alive(target):
            if role not in _skip_logged:
                log.info("skip: tmux target not alive: role=%s target=%s", role, target)
                _skip_logged.add(role)
            continue
        if not _pane_idle(target):
            if role not in _skip_logged:
                log.info("skip: pane busy: role=%s target=%s", role, target)
                _skip_logged.add(role)
            continue
        # Once we successfully wake, clear suppression so future skips re-log.
        _skip_logged.discard(role)
        if _send_inbox(target, log):
            # If the prior wake didn't reduce this role's unread count, the
            # session isn't consuming — grow the backoff; otherwise reset it.
            prev = last_unread.get(role)
            if prev is not None and unread[role] >= prev:
                backoff[role] = min(backoff.get(role, 1.0) * 2.0,
                                    MAX_WAKE_BACKOFF_SEC / WAKE_COOLDOWN_SEC)
            else:
                backoff[role] = 1.0
            last_unread[role] = unread[role]
            last_woken[role] = now
            log.info("wake sent role=%s -> %s (unread=%d backoff=%.0fx)",
                     role, target, unread[role], backoff.get(role, 1.0))
            sent += 1
    return sent


def main() -> None:
    log = _setup_log()
    log.info("harnessd starting, poll=%ss cooldown=%ss",
             POLL_INTERVAL_SEC, WAKE_COOLDOWN_SEC)
    last_woken: dict[str, float] = {}
    last_unread: dict[str, int] = {}
    backoff: dict[str, float] = {}
    stall_state: dict[str, dict] = {}
    try:
        while True:
            try:
                discover_ctos(log)
                reap_stale_cto_notifications(log)
                detect_stalls(log, stall_state)
                tick(log, last_woken, last_unread, backoff)
            except Exception:
                log.exception("tick error")
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        log.info("harnessd stopped (KeyboardInterrupt)")


if __name__ == "__main__":
    main()
