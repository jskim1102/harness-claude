import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness.db import connect

# Directories under the repo root that may contain CTO project directories.
# Each direct subdirectory with a .claude/settings.json that references our
# harness hook is treated as a registered CTO.
REPO_ROOT = Path(__file__).resolve().parent.parent
CTO_SEARCH_DIRS = (
    REPO_ROOT / "claude-project",
    REPO_ROOT / "modules",   # 모듈 빌드 CTO (plans/harness.md)
)
HARNESS_HOOK_MARKER = "hooks/session_start.py"  # appears in our settings.json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _die(msg: str, code: int = 2) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _sanitize_preview(body: str, maxlen: int = 80) -> str:
    """Make an untrusted message-body preview safe to print to a terminal.
    Mirrors hooks/user_prompt_inbox_check.py: strip control chars + newlines,
    neutralize prompt-injection markers (angle-bracket tags, conversational
    role-line prefixes, code fences), then cap. Sender-controlled bodies must
    not be able to inject ANSI/control sequences or fake markers into operator
    output."""
    if not isinstance(body, str):
        body = str(body)
    cleaned = "".join(
        " " if ch in ("\n", "\r", "\t") else ch
        for ch in body
        if ch in ("\n", "\r", "\t") or ord(ch) >= 32
    )
    cleaned = re.sub(r"<\s*/?\s*[A-Za-z][^>]*>", "[redacted]", cleaned)
    for marker in ("system:", "assistant:", "user:", "human:", "```"):
        cleaned = re.sub(re.escape(marker), "[redacted]", cleaned, flags=re.I)
    if len(cleaned) > maxlen:
        cleaned = cleaned[:maxlen] + "…"
    return cleaned


# Allowlist of valid sender/role syntaxes. A role is the literal 'ceo' or
# 'harnessd', or a 'cto:'/'codex-review:' prefix followed by a kebab name
# (same kebab pattern run.sh enforces for CTO names). Anything else — newlines,
# control chars, prompt-injection markers — is rejected before it can be stored
# as from_role and later surfaced into CEO context.
_ROLE_RE = re.compile(
    r"^(ceo|cto:[a-z0-9]+(-[a-z0-9]+)*|codex-review:[a-z0-9]+(-[a-z0-9]+)*|harnessd)\Z"
)
# Mirror of daemon.py's _CTO_SESSION_RE — a live tmux session name must be a
# kebab cto-<name> before we trust it as a CTO. Without this the discover-roles
# fallback would surface a hostile session name (the daemon-group's injection
# defect class) into any consumer that interpolates it.
_CTO_SESSION_RE = re.compile(r"^cto-[a-z0-9]+(-[a-z0-9]+)*\Z")


def _role(explicit: str | None = None) -> str:
    env_role = os.environ.get("HARNESS_ROLE")
    if explicit and env_role and explicit != env_role:
        _die(
            f"error: --from={explicit!r} conflicts with HARNESS_ROLE={env_role!r}"
        )
    role = explicit or env_role
    if not role:
        _die("error: HARNESS_ROLE env not set — call from a configured shell")
    if not _ROLE_RE.match(role):
        _die(
            f"error: invalid role {role!r}; expected ceo, harnessd, "
            f"cto:<name>, or codex-review:<name> (kebab name)"
        )
    return role


def cmd_send(args: argparse.Namespace) -> int:
    from_role = _role(args.from_role)
    to_role = args.to
    # Validate to_role SYNTAX unconditionally against the role allowlist —
    # newlines/control/injection bytes must never reach the DB regardless of
    # --to-unknown. --to-unknown skips only the discovery/aliveness check
    # below, not this syntax gate.
    if not _ROLE_RE.match(to_role):
        _die(
            f"error: invalid target role {to_role!r}; expected ceo, harnessd, "
            f"cto:<name>, or codex-review:<name> (kebab name)"
        )
    if args.body_stdin and args.body is not None:
        _die("error: --body and --body-stdin are mutually exclusive")
    if not args.body_stdin and args.body is None:
        _die("error: must give exactly one of --body or --body-stdin")
    body = sys.stdin.read() if args.body_stdin else args.body
    if not body.strip():
        _die("error: empty body")
    # Validate target role against discovered roles, unless explicitly overridden.
    # 'ceo' is always a valid target (CEO-less mode has no on-disk registration).
    if not args.to_unknown and to_role != "ceo":
        roles = _discover_roles()
        known_names = {
            (f"cto:{r['name']}" if r["kind"] == "cto" else r["name"]) for r in roles
        }
        known_names.add("ceo")  # CEO-less mode tolerance
        if to_role not in known_names:
            _die(
                f"error: unknown target: {to_role}. known: {sorted(known_names)}"
            )
        # Dead-target warning: registered on disk but tmux session gone.
        for r in roles:
            r_name = f"cto:{r['name']}" if r["kind"] == "cto" else r["name"]
            if r_name == to_role and not r["alive"]:
                print(
                    f"warning: target {to_role} not alive; "
                    f"message queued for next session start",
                    file=sys.stderr,
                )
                break
    with connect() as c:
        cur = c.execute(
            "INSERT INTO msg (from_role, to_role, body) VALUES (?, ?, ?)",
            (from_role, to_role, body),
        )
        msg_id = cur.lastrowid
    print(f"sent id={msg_id} {from_role} -> {to_role}")
    return 0


def cmd_inbox(args: argparse.Namespace) -> int:
    me = _role(None)
    with connect() as c:
        # Claim the unread rows atomically: connect() runs in autocommit mode,
        # so a bare SELECT-then-UPDATE lets two concurrent readers both read the
        # same rows before either marks them read → double-processing. Take a
        # write lock up front with BEGIN IMMEDIATE so the select+update is one
        # transaction and a row is claimed by exactly one reader. (--peek stays
        # read-only and needs no lock.)
        if not args.peek:
            c.execute("BEGIN IMMEDIATE")
        try:
            rows = c.execute(
                "SELECT id, from_role, body, created FROM msg "
                "WHERE to_role=? AND read_at IS NULL ORDER BY id",
                (me,),
            ).fetchall()
            if not rows:
                if not args.peek:
                    c.execute("COMMIT")
                print(f"(inbox empty for {me})")
                return 0
            ids = [r["id"] for r in rows]
            if not args.peek:
                now = _now()
                c.executemany(
                    "UPDATE msg SET read_at=? WHERE id=? AND read_at IS NULL",
                    [(now, i) for i in ids],
                )
                c.execute("COMMIT")
        except Exception:
            if not args.peek:
                c.execute("ROLLBACK")
            raise
    for r in rows:
        print(f"[{r['id']}] from={r['from_role']} at={r['created']}")
        print(r["body"])
        print("---")
    return 0


def _is_harness_dir(dir_path: Path) -> bool:
    s = dir_path / ".claude" / "settings.json"
    if not s.is_file():
        return False
    try:
        return HARNESS_HOOK_MARKER in s.read_text()
    except (OSError, UnicodeDecodeError):
        return False


def _alive_sessions() -> set[str]:
    r = subprocess.run(
        ["tmux", "list-sessions", "-F", "#{session_name}"],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        return set()
    # One session per line: split on newlines (NOT whitespace) so a session
    # name bearing internal whitespace can't tokenize into multiple fake
    # names. Then keep only names we trust — 'ceo' or a kebab cto-<name>
    # (tmux allows quotes/semicolons/spaces in session names, and these are
    # later interpolated downstream; reject anything else at the source).
    return {
        name
        for line in r.stdout.splitlines()
        if (name := line.strip()) and (name == "ceo" or _CTO_SESSION_RE.match(name))
    }


def _discover_roles() -> list[dict]:
    """Scan known directories for harness-registered roles.
    Returns list of {kind, name, dir, session, alive} dicts."""
    found: list[dict] = []
    alive = _alive_sessions()
    seen_dirs = set()
    for base in CTO_SEARCH_DIRS:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            if not child.is_dir() or not _is_harness_dir(child):
                continue
            real = child.resolve()
            if real in seen_dirs:
                continue
            seen_dirs.add(real)
            # naming: directory basename. 'ceo' is CEO; everything else is CTO.
            base_name = child.name
            if base_name == "ceo":
                kind = "ceo"
                role_name = "ceo"
                session = "ceo"
            else:
                kind = "cto"
                # strip 'cto-' prefix if present (sandbox convention)
                role_name = base_name[4:] if base_name.startswith("cto-") else base_name
                session = f"cto-{role_name}"
                # Defense-in-depth: reject a non-kebab disk dir name at the
                # source so `harness roles` never emits a CTO name that could
                # break tmux send-keys quoting downstream (role.md/cto-pick
                # validate too, but the source should not emit it at all).
                if not _CTO_SESSION_RE.match(session):
                    continue
            found.append({
                "kind": kind,
                "name": role_name,
                "dir": str(child),
                "session": session,
                "alive": session in alive,
            })
    # Fallback: live cto-* tmux sessions whose on-disk marker is missing.
    # The daemon routes wakes by live cto-* sessions, so a CTO can be alive
    # and reachable even after its .claude/settings.json (the disk marker)
    # is removed. Without this, `harness send` rejects such a live CTO as an
    # "unknown target" even though messages would still reach it. Add any
    # cto-<name> session not already discovered via disk.
    discovered_sessions = {r["session"] for r in found}
    for session in sorted(alive):
        if not _CTO_SESSION_RE.match(session) or session in discovered_sessions:
            continue
        role_name = session[4:]  # strip 'cto-'
        if not role_name:
            continue
        found.append({
            "kind": "cto",
            "name": role_name,
            "dir": "(tmux session; .claude marker missing)",
            "session": session,
            "alive": True,
        })
    return found


def cmd_roles(args: argparse.Namespace) -> int:
    roles = _discover_roles()
    if args.format == "json":
        print(json.dumps(roles, indent=2, ensure_ascii=False))
        return 0
    # table
    if not roles:
        print("(no registered roles found)")
        return 0
    print(f"{'kind':5} {'name':16} {'session':24} {'alive':5} dir")
    print("-" * 80)
    for r in roles:
        alive = "yes" if r["alive"] else "no"
        print(f"{r['kind']:5} {r['name']:16} {r['session']:24} {alive:5} {r['dir']}")
    return 0


# ── status: cross-CTO operator rollup ─────────────────────────────────────────
# Per CTO: 현재 ckpt (specs/tasks.md 의 첫 미완료 ### phaseN.ckptN 헤딩 —
# cto_statusline.py 와 동일 규칙), task counts ([x]/[!]/[ ]), 최근 msg 타임라인.
# Everything best-effort: a missing/garbled file yields "unknown", never an
# exception — an operator view must never crash on a half-written specs dir.
_CKPT_RE = re.compile(r"^###\s+(phase\d+\.ckpt\d+)\s*(.*)$")
_BOX_RE = re.compile(r"^\s*[-*]\s*\[(✅| |x|X|!)\]")


def _current_ckpt(tasks_path: Path) -> dict:
    """첫 미완료 ckpt 헤딩 (체크박스 전부 [x] 가 아닌 첫 ###). 새 체계
    (plans/harness.md): 상태 = specs/tasks.md 체크박스만, 상태파일 없음."""
    out = {"ckpt": None, "title": None, "all_done": False}
    try:
        text = tasks_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return out
    sections: list[dict] = []
    cur = None
    for line in text.splitlines():
        m = _CKPT_RE.match(line)
        if m:
            cur = {"id": m.group(1), "title": m.group(2).strip(), "boxes": []}
            sections.append(cur)
            continue
        if cur is not None:
            b = _BOX_RE.match(line)
            if b:
                cur["boxes"].append(b.group(1) in ("x", "X", "✅"))
    for s in sections:
        if not s["boxes"] or not all(s["boxes"]):
            out["ckpt"], out["title"] = s["id"], s["title"]
            return out
    if sections:
        out["all_done"] = True
    return out


def _task_counts(specs_dir: Path) -> dict:
    """Count `- [x]` / `- [!]` / `- [ ]` task lines in specs/tasks.md.
    Returns done/blocked/open/total."""
    f = specs_dir / "tasks.md"
    counts = {"done": 0, "blocked": 0, "open": 0, "total": 0}
    if not f.is_file():
        return counts
    try:
        text = f.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return counts
    for line in text.splitlines():
        m = re.match(r"\s*-\s*\[(✅| |x|!)\]", line)
        if not m:
            continue
        box = m.group(1)
        if box in ("x", "✅"):
            counts["done"] += 1
        elif box == "!":
            counts["blocked"] += 1
        else:
            counts["open"] += 1
        counts["total"] += 1
    return counts


def _recent_events(conn, cto_name: str, limit: int) -> list[dict]:
    """Last `limit` msgs touching this CTO (as sender or recipient), newest first.
    cto_name is the bare kebab name; the stored role is `cto:<name>`."""
    role = f"cto:{cto_name}"
    rows = conn.execute(
        "SELECT id, from_role, to_role, body, created FROM msg "
        "WHERE from_role=? OR to_role=? ORDER BY id DESC LIMIT ?",
        (role, role, limit),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "from": r["from_role"],
            "to": r["to_role"],
            "body": r["body"],
            "created": r["created"],
        }
        for r in rows
    ]


def _collect_status(limit: int) -> list[dict]:
    """One rollup record per (CTO, slug). CTOs with no spec dirs still appear
    (with an empty missions list) so the operator sees every registered CTO."""
    roles = [r for r in _discover_roles() if r["kind"] == "cto"]
    out: list[dict] = []
    with connect() as conn:
        for r in roles:
            events = _recent_events(conn, r["name"], limit)
            dir_str = r["dir"]
            cto_dir = Path(dir_str) if dir_str and dir_str.startswith("/") else None
            missions: list[dict] = []
            if cto_dir is not None:
                specs_dir = cto_dir / "specs"
                if specs_dir.is_dir():
                    cur = _current_ckpt(specs_dir / "tasks.md")
                    missions.append({
                        "slug": cto_dir.name,
                        "ckpt": cur["ckpt"] or ("DONE" if cur["all_done"] else "분해 전"),
                        "title": cur["title"],
                        "tasks": _task_counts(specs_dir),
                    })
            out.append({
                "cto": r["name"],
                "session": r["session"],
                "alive": r["alive"],
                "missions": missions,
                "events": events,
            })
    return out


def cmd_status(args: argparse.Namespace) -> int:
    rollup = _collect_status(args.limit)
    if args.format == "json":
        print(json.dumps(rollup, indent=2, ensure_ascii=False))
        return 0
    if not rollup:
        print("(no registered CTOs found)")
        return 0
    for r in rollup:
        alive = "alive" if r["alive"] else "dead"
        print(f"━━ cto:{r['cto']}  ({r['session']}, {alive})")
        if not r["missions"]:
            print("   (no specs)")
        for m in r["missions"]:
            t = m["tasks"]
            bar = f"{t['done']}✓ {t['blocked']}! {t['open']}☐ / {t['total']}"
            print(f"   {m['slug']:24} {m['ckpt']:18} {bar}")
        if r["events"]:
            print("   recent:")
            for e in r["events"]:
                body = e["body"].replace("\n", " ")[:60]
                print(f"     {e['created']}  {e['from']}→{e['to']}: {body}")
        print()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    with connect() as c:
        rows = c.execute(
            "SELECT id, from_role, to_role, body, created, read_at FROM msg "
            "ORDER BY id DESC LIMIT ?",
            (args.limit,),
        ).fetchall()
    for r in rows:
        status = "read" if r["read_at"] else "unread"
        # body (and roles) are sender-controlled/UNTRUSTED — sanitize before
        # printing so they can't inject control/ANSI sequences or fake markers.
        print(
            f"[{r['id']}] {_sanitize_preview(r['from_role'])} -> "
            f"{_sanitize_preview(r['to_role'])} "
            f"({status}) {r['created']}: {_sanitize_preview(r['body'])}"
        )
    return 0


# ── ports: scan project .env files → regenerate docs/PORT.md ──────────────────
# Source of truth = each project's .env. offset = BACKEND_PORT - 8000.
PORT_SCAN_BASES = ("claude-project", "modules")  # all under $REPO
PORT_COLS = [
    ("Backend", "BACKEND_PORT"),
    ("Frontend", "FRONTEND_PORT"),
    ("MTX API", "MEDIAMTX_API_PORT"),
    ("MTX HLS", "MEDIAMTX_HLS_PORT"),
    ("MTX RTSP", "MEDIAMTX_RTSP_PORT"),
    ("PostgreSQL", "POSTGRES_PORT"),
    ("Redis", "REDIS_PORT"),
    ("MinIO API", "MINIO_API_PORT"),
    ("MinIO Console", "MINIO_CONSOLE_PORT"),
]


def _read_env_ports(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except (OSError, UnicodeDecodeError):
        pass
    return out


def _docker_published_ports() -> set[str]:
    """Host ports published by running containers (best-effort; empty if docker absent)."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Ports}}"],
            capture_output=True, text=True, timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return set()
    return set(re.findall(r":(\d+)->", r.stdout)) if r.returncode == 0 else set()


def _scan_port_projects() -> list[dict]:
    """Projects (anywhere in PORT_SCAN_BASES) whose root .env has a numeric BACKEND_PORT."""
    bases = [REPO_ROOT / b for b in PORT_SCAN_BASES]
    found: list[dict] = []
    seen: set[str] = set()
    for base in bases:
        if not base.is_dir():
            continue
        for child in sorted(base.iterdir()):
            env = child / ".env"
            if not child.is_dir() or not env.is_file() or child.name in seen:
                continue
            ports = _read_env_ports(env)
            be = ports.get("BACKEND_PORT", "")
            if not be.isdigit():
                continue
            seen.add(child.name)
            found.append({"name": child.name, "offset": int(be) - 8000, "ports": ports})
    found.sort(key=lambda r: (r["offset"], r["name"]))
    return found


def _next_free_offset(projects: list[dict]) -> int:
    used = {pj["offset"] for pj in projects}
    n = 1
    while n in used:
        n += 1
    return n


def _render_ports_md(projects: list[dict]) -> str:
    pub = _docker_published_ports()
    header = ["프로젝트", "offset"] + [c[0] for c in PORT_COLS] + ["상태"]
    out = [
        "# PORT.md — 포트 레지스트리 (하드룰 4 source of truth)",
        "",
        "> **자동 생성** — `./run.sh ports` 또는 add-cto / delete-cto 가 각 프로젝트",
        "> 의 `.env` 를 스캔해 재생성한다. **직접 편집 금지** (재생성 시 덮어씀).",
        "> 진실원천 = 각 프로젝트 `.env`. offset = `BACKEND_PORT − 8000`.",
        "> MinIO 등 `.env` 에 없는 포트(docker-compose 하드코딩)는 `—` 로 나온다.",
        "",
        "## 현황",
        "",
        "| " + " | ".join(header) + " |",
        "|" + "---|" * len(header),
    ]
    for pj in projects:
        ports = pj["ports"]
        running = False
        cells = [pj["name"], str(pj["offset"])]
        for _label, var in PORT_COLS:
            v = ports.get(var, "")
            cells.append(v or "—")
            if v and v in pub:
                running = True
        cells.append("컨테이너 가동중" if running else ".env만")
        out.append("| " + " | ".join(cells) + " |")
    out += [
        "",
        "## 시스템 예약 (offset 무관, 건드리지 말 것)",
        "",
        "| 항목 | 포트 | 비고 |",
        "|---|---|---|",
        "| 시스템 PostgreSQL | 5432 | localhost only |",
        "| SSH | 8164 | — |",
        "",
        f"> **다음 free offset = {_next_free_offset(projects)}**",
    ]
    return "\n".join(out)


def cmd_ports(args: argparse.Namespace) -> int:
    projects = _scan_port_projects()
    if args.next:
        print(_next_free_offset(projects))
        return 0
    md = _render_ports_md(projects)
    (REPO_ROOT / "docs").mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "docs" / "PORT.md").write_text(md + "\n", encoding="utf-8")
    if not args.quiet:
        print(md)
    return 0


def main() -> None:
    p = argparse.ArgumentParser(prog="harness")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("send", help="send a message")
    s.add_argument(
        "--from",
        dest="from_role",
        default=None,
        help="sender role; must match HARNESS_ROLE if both are set",
    )
    s.add_argument("--to", required=True)
    s.add_argument("--body", default=None, help="message body (argv); see --body-stdin")
    s.add_argument(
        "--body-stdin",
        action="store_true",
        help="read body from stdin instead of --body (use with heredoc to avoid shell expansion)",
    )
    s.add_argument(
        "--to-unknown",
        action="store_true",
        help="skip target role validation (for testing)",
    )
    s.set_defaults(func=cmd_send)

    s = sub.add_parser("inbox", help="show unread for HARNESS_ROLE and mark read")
    s.add_argument("--peek", action="store_true", help="do not mark read")
    s.set_defaults(func=cmd_inbox)

    s = sub.add_parser("list", help="recent messages (any role)")
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("roles", help="list registered CEO/CTO roles on disk + alive status")
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.set_defaults(func=cmd_roles)

    s = sub.add_parser(
        "status",
        help="cross-CTO operator rollup: per-slug phase, task counts, recent events",
    )
    s.add_argument("--format", choices=["table", "json"], default="table")
    s.add_argument("--limit", type=int, default=5, help="recent events per CTO")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("ports", help="scan project .env files → regenerate docs/PORT.md")
    s.add_argument("--next", action="store_true", help="print only the next free offset")
    s.add_argument("--quiet", action="store_true", help="regenerate PORT.md without printing")
    s.set_defaults(func=cmd_ports)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
