#!/usr/bin/env python3
"""PostToolUse hook — silently accumulates DURABLE project facts.

Concept ported from oh-my-claudecode's project-memory learner
(references/oh-my-claudecode/src/hooks/project-memory/learner.ts), re-implemented
in harness idioms: stdlib-only, fail-open, a flat per-project markdown file
(matching the one-flat-file MEMORY.md convention) instead of a JSON store.

WHAT IT CAPTURES (durable, low-noise project facts):
  - Bash build/test/lint commands actually run (the real invocation, not
    the model's guess) — the highest-signal thing OMC tracks.
  - Runtime hints from tool output: python/node/rust version banners.
  - Missing-module / missing-env-var errors (ModuleNotFoundError, "Cannot
    find module", "Required env var X") — recurring environment gotchas.
  - Hot file paths: files touched 3+ times via Read/Edit/Write.

WHAT IT DOES NOT CAPTURE (deliberately — see report caveat):
  - Arbitrary command output, stdout/stderr text, logs, diffs.
  - One-off file reads (a path must be touched 3+ times to count as hot).
  - Anything from non-CTO roles (CEO is a meta-manager, not a builder).
  - Secrets: env-var NAMES are kept, values never are.

STORE: <project_root>/.claude/harness-memory.md — project-local, bounded FIFO
(20 notes), shared by every CTO working that project. flock serializes the
read-modify-write so concurrent CTOs/teammates don't clobber each other.

CONTRACT: fail-open. Any error → exit 0, no output. This hook must never
break a tool call. It is silent on the happy path too (PostToolUse stdout is
not injected as context here — the accumulated file is surfaced separately by
session_start.py). Per RULES §1 it runs NO git commands.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

# Per-project FIFO cap. Matches OMC's 20-note customNotes limit.
MAX_NOTES = 20
# A file must be touched this many times before it is recorded as a hot path,
# so a single incidental Read never pollutes durable memory.
HOT_PATH_THRESHOLD = 3

MEM_FILENAME = "harness-memory.md"
HEADER = "# Harness project memory (auto-accumulated)\n"

# Build/test/lint command fingerprints. A note is only filed when the model
# actually RAN one of these — the real invocation is far higher signal than a
# guessed command. Ported from OMC BUILD/TEST_COMMAND_PATTERNS, plus lint.
CMD_PATTERNS = [
    ("build", re.compile(r"\b(npm run build|pnpm build|yarn build|bun run build|cargo build|go build|tsc\b|make build|mvn package|gradle build|poetry build)")),
    ("test", re.compile(r"\b(npm test|pnpm test|yarn test|bun test|cargo test|go test|pytest\b|jest\b|vitest\b|make test|poetry run pytest|python -m pytest)")),
    ("lint", re.compile(r"\b(npm run lint|pnpm lint|yarn lint|eslint\b|ruff check|ruff\b|cargo clippy|golangci-lint|flake8\b|mypy\b)")),
]

# Directories that never belong in hot-path memory (ported from OMC
# shouldIgnorePath). Substring match on the relative path.
IGNORE_DIR_TOKENS = (
    "node_modules", ".git/", "dist/", "build/", ".cache", ".next",
    ".nuxt", "coverage", "__pycache__", ".venv", "site-packages",
)


def read_payload():
    """Read+parse the PostToolUse stdin JSON. {} on empty/invalid."""
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def find_project_root(start):
    """Walk up from `start` to the nearest dir containing .claude/ or .git/.
    Falls back to `start` itself. Never raises.
    """
    try:
        cur = Path(start).resolve()
    except Exception:
        return None
    if not cur.exists():
        return None
    for d in [cur, *cur.parents]:
        try:
            if (d / ".claude").is_dir() or (d / ".git").exists():
                return d
        except Exception:
            continue
    return cur


def _output_str(payload):
    """Best-effort flatten of tool_response into a string for hint scanning.
    Claude Code delivers tool_response as a dict (stdout/stderr) or string.
    """
    resp = payload.get("tool_response")
    if isinstance(resp, str):
        return resp
    if isinstance(resp, dict):
        parts = []
        for k in ("stdout", "stderr", "output", "content"):
            v = resp.get(k)
            if isinstance(v, str):
                parts.append(v)
        return "\n".join(parts)
    return ""


def _rel(path_str, root):
    """Relative path under root, or None if outside / ignorable."""
    try:
        p = Path(path_str)
        if not p.is_absolute():
            rel = path_str
        else:
            rel = os.path.relpath(str(p), str(root))
    except Exception:
        return None
    rel = rel.replace("\\", "/")
    if rel.startswith(".."):
        return None
    if any(tok in rel for tok in IGNORE_DIR_TOKENS):
        return None
    return rel


_ENV_ASSIGN_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _redact_inline_env(cmd):
    """Redact the VALUE of any `NAME=value` env-assignment token, anywhere in
    the command, so an inline secret (`DATABASE_URL=...`, `STRIPE_KEY=sk_live_...`,
    a non-leading `pytest TOKEN=secret`, or a quoted `API_KEY='a b' pytest`) is
    never stored verbatim (the secrets-never-stored contract above). Tokenizes
    shell-aware so quoted values with spaces are one token; falls back to a plain
    split on a parse error. Returns a single normalized line.
    """
    try:
        tokens = shlex.split(cmd)
    except ValueError:
        tokens = cmd.split()
    out = []
    for tok in tokens:
        if _ENV_ASSIGN_RE.match(tok):
            out.append(tok.split("=", 1)[0] + "=<redacted>")
        else:
            out.append(tok)
    return " ".join(out)


def derive_facts(payload, root):
    """Return a list of (category, content) durable facts from this one tool
    call. Empty list = nothing worth remembering. Hot-path facts are deferred
    to file-merge time (they need the running count), so they are emitted here
    as a sentinel ("hotpath-candidate", relpath).
    """
    tool = payload.get("tool_name") or ""
    tin = payload.get("tool_input") or {}
    if not isinstance(tin, dict):
        tin = {}
    facts = []

    if tool == "Bash":
        cmd = (tin.get("command") or "").strip()
        if cmd:
            for label, pat in CMD_PATTERNS:
                if pat.search(cmd):
                    # Store the actual single-line invocation, capped — but
                    # redact inline `NAME=secret` env-prefixes first so a
                    # command like `DATABASE_URL=... pytest` never stores the
                    # value (the secrets-never-stored contract above).
                    one = _redact_inline_env(cmd)[:160]
                    facts.append((label + "-cmd", one))
                    break  # one category per command is enough
            facts.extend(_env_hints(_output_str(payload)))
        return facts

    if tool in ("Read", "Edit", "Write"):
        fp = tin.get("file_path") or tin.get("filePath")
        if fp:
            rel = _rel(fp, root)
            if rel:
                facts.append(("hotpath-candidate", rel))
        return facts

    return facts


def _env_hints(output):
    """Durable environment hints from tool output. Ported from OMC
    extractEnvironmentHints — versions, missing modules, required env vars.
    Values are never captured (only the var NAME), so no secret leakage.
    """
    if not output:
        return []
    hints = []
    m = re.search(r"\bPython\s+(\d+\.\d+\.\d+)", output)
    if m:
        hints.append(("runtime", "Python " + m.group(1)))
    nm = re.search(r"\bNode(?:\.js)?\s+v?(\d+\.\d+\.\d+)", output, re.I)
    if nm:
        hints.append(("runtime", "Node.js " + nm.group(1)))
    m = re.search(r"\brustc\s+(\d+\.\d+\.\d+)", output)
    if m:
        hints.append(("runtime", "Rust " + m.group(1)))
    m = re.search(r"ModuleNotFoundError: No module named ['\"]([\w\.\-]+)['\"]", output)
    if m:
        hints.append(("missing-dep", m.group(1)))
    m = re.search(r"Cannot find module ['\"]([^'\"]+)['\"]", output)
    if m:
        hints.append(("missing-dep", m.group(1)))
    m = re.search(r"(?:Missing|Required)\s+(?:environment\s+)?(?:variable|env(?:\s*var)?)[:\s]+([A-Z][A-Z0-9_]{2,})", output, re.I)
    if m:
        hints.append(("env-var", m.group(1)))
    return hints


# --- File format -----------------------------------------------------------
# One note per line:  - [category] content    (#hits for hotpath)
# Parsing is line-oriented and forgiving so a hand-edit never crashes us.
NOTE_RE = re.compile(r"^- \[([a-z\-]+)\] (.*?)(?:  \(x(\d+)\))?\s*$")


def _parse(text):
    """-> (list_of_notes, hotpath_counts). note = (category, content)."""
    notes = []
    hot = {}
    for line in text.splitlines():
        m = NOTE_RE.match(line)
        if not m:
            continue
        cat, content, hits = m.group(1), m.group(2), m.group(3)
        if cat == "hotpath":
            hot[content] = int(hits) if hits else 1
        else:
            notes.append((cat, content))
    return notes, hot


def _render(notes, hot):
    lines = [HEADER, "\n"]
    # Hot paths first (most queried at a glance), then categorized notes.
    for path, hits in sorted(hot.items(), key=lambda kv: -kv[1]):
        lines.append("- [hotpath] {}  (x{})\n".format(path, hits))
    for cat, content in notes:
        lines.append("- [{}] {}\n".format(cat, content))
    return "".join(lines)


def merge(existing_text, new_facts):
    """Fold new_facts into the existing file text. Returns (text, changed).
    - Non-hotpath facts: dedup by (category, content); FIFO cap to MAX_NOTES.
    - hotpath-candidate: increment a per-path counter; only surface as a
      [hotpath] note once it crosses HOT_PATH_THRESHOLD.
    """
    notes, hot = _parse(existing_text)
    changed = False

    # Pending (sub-threshold) hot counts are tracked invisibly in a comment
    # line so they survive across calls without showing until they qualify.
    pending = {}
    m = re.search(r"<!-- pending-hot: (.*?) -->", existing_text)
    if m:
        try:
            pending = json.loads(m.group(1))
        except Exception:
            pending = {}

    for cat, content in new_facts:
        if cat == "hotpath-candidate":
            if content in hot:
                hot[content] += 1
                changed = True
            else:
                pending[content] = pending.get(content, 0) + 1
                changed = True
                if pending[content] >= HOT_PATH_THRESHOLD:
                    hot[content] = pending.pop(content)
        else:
            if (cat, content) not in notes:
                notes.append((cat, content))
                changed = True

    if not changed:
        return existing_text, False

    # FIFO cap on categorized notes (hot paths are separately bounded below).
    if len(notes) > MAX_NOTES:
        notes = notes[-MAX_NOTES:]
    # Keep hot paths bounded too (top 10 by hits).
    if len(hot) > 10:
        hot = dict(sorted(hot.items(), key=lambda kv: -kv[1])[:10])

    # Bound `pending` like `hot` — sub-threshold candidates must not grow
    # unboundedly (the file is re-parsed under flock on every tool call;
    # a project touches thousands of files once).
    if len(pending) > 50:
        pending = dict(sorted(pending.items(), key=lambda kv: -kv[1])[:50])

    text = _render(notes, hot)
    if pending:
        text += "\n<!-- pending-hot: {} -->\n".format(json.dumps(pending))
    return text, True


def main():
    payload = read_payload()
    if not payload:
        return

    # Only accumulate for CTO sessions — the CEO is a meta-manager, not a
    # builder, and would pollute project memory with harness-repo facts.
    role = os.environ.get("HARNESS_ROLE", "")
    if not (role == "cto" or role.startswith("cto:")):
        return

    root = find_project_root(payload.get("cwd") or os.getcwd())
    if root is None:
        return

    facts = derive_facts(payload, root)
    if not facts:
        return

    claude_dir = root / ".claude"
    mem_path = claude_dir / MEM_FILENAME
    lock_path = claude_dir / (MEM_FILENAME + ".lock")

    try:
        claude_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    import fcntl  # POSIX-only; harness is Linux (see env). Imported late so a
    # non-POSIX host fails open at the try/except in __main__ rather than here.

    try:
        lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o644)
    except Exception:
        return
    try:
        # Block briefly for the cross-CTO concurrent case; the critical
        # section is a tiny read-modify-write so contention is rare.
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
        try:
            existing = mem_path.read_text(encoding="utf-8")
        except Exception:
            existing = HEADER + "\n"
        text, changed = merge(existing, facts)
        if changed:
            tmp = mem_path.with_suffix(".md.tmp{}".format(os.getpid()))
            tmp.write_text(text, encoding="utf-8")
            os.replace(str(tmp), str(mem_path))  # atomic
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(lock_fd)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # FAIL OPEN — a memory hook must never break a tool call.
        print("[harness] project_memory hook error (fail-open): {}".format(e), file=sys.stderr)
        sys.exit(0)
