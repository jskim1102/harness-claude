#!/usr/bin/env python3
"""SessionStart hook. Reads HARNESS_ROLE env, prints role.md to stdout.

Claude Code feeds hook stdout into the session prompt (additional context),
which is how role information gets injected at session start.
"""
import json
import os
import sys
from pathlib import Path

PLUGINS = Path(__file__).resolve().parent.parent / "plugins"


def main() -> None:
    role = os.environ.get("HARNESS_ROLE")
    if not role:
        return
    role_dir = role.split(":")[0]  # 'cto:foo' -> 'cto'
    role_md = PLUGINS / role_dir / "role.md"
    if not role_md.exists():
        print(f"[harness] role.md not found for {role}", file=sys.stderr)
        return

    try:
        body = role_md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        # Fail-open: matching sibling hooks' contract (skill_announce,
        # team_hook_common). A noisy traceback at session start would
        # surface to the user and looks worse than a silent degrade.
        print(f"[harness] could not read role.md ({e})", file=sys.stderr)
        return

    if ":" in role:
        body = body.replace("{{name}}", role.split(":", 1)[1])

    # Prepend the harness-wide hard rules (shared across CEO + CTO + every
    # sub-agent). Same fail-open contract — if RULES.md is missing or
    # unreadable, role.md still ships.
    rules_md = PLUGINS / "_shared" / "RULES.md"
    if rules_md.exists():
        try:
            rules_body = rules_md.read_text(encoding="utf-8")
            body = rules_body + "\n\n---\n\n" + body
        except (OSError, UnicodeDecodeError) as e:
            print(f"[harness] could not read RULES.md ({e})", file=sys.stderr)

    # CTO only: append the build-process flow spec. PROCESS.md owns the
    # 분해→segment 루프 운영 흐름 (정본 plans/harness.md 의 운영 추출본);
    # the CEO is a meta-manager and does not build, so it is not injected
    # there. INJECT-END marker 가 있으면 그 앞까지만, 없으면 전체 주입.
    # Same fail-open contract.
    if role_dir == "cto":
        process_md = PLUGINS / "_shared" / "PROCESS.md"
        if process_md.exists():
            try:
                ptext = process_md.read_text(encoding="utf-8")
                marker = "<!-- INJECT-END"
                if marker in ptext:
                    ptext = ptext.split(marker)[0].rstrip()
                body = body + "\n\n---\n\n" + ptext
            except (OSError, UnicodeDecodeError) as e:
                print(f"[harness] could not read PROCESS.md ({e})", file=sys.stderr)

    # CTO only: surface accumulated durable project memory (written by the
    # project_memory.py PostToolUse hook) so the next session starts knowing
    # the real build/test commands, runtime, missing deps, and hot paths
    # instead of re-discovering them. Same fail-open contract — a missing or
    # unreadable memory file just degrades to no extra context.
    if role_dir == "cto":
        mem_body = _read_project_memory()
        if mem_body:
            body = body + "\n\n---\n\n" + mem_body

    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": body}}
    print(json.dumps(out))


def _read_project_memory() -> str:
    """Return the project's accumulated harness-memory.md as injectable
    context, or "" if absent/empty. Derives the project root from the hook
    payload's cwd (falling back to os.getcwd()). Never raises.
    """
    cwd = None
    try:
        raw = sys.stdin.read()
        if raw.strip():
            cwd = json.loads(raw).get("cwd")
    except Exception:
        cwd = None
    try:
        start = Path(cwd) if cwd else Path.cwd()
        if not start.exists():
            start = Path.cwd()
        root = None
        for d in [start.resolve(), *start.resolve().parents]:
            if (d / ".claude").is_dir() or (d / ".git").exists():
                root = d
                break
        if root is None:
            root = start.resolve()
        mem = root / ".claude" / "harness-memory.md"
        if not mem.exists():
            return ""
        text = mem.read_text(encoding="utf-8").strip()
        # Strip the invisible pending-hot bookkeeping comment before injection.
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("<!-- pending-hot:")]
        text = "\n".join(lines).strip()
        return text if text and text != "# Harness project memory (auto-accumulated)" else ""
    except (OSError, UnicodeDecodeError, ValueError):
        return ""


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Fail-open at top level too.
        print(f"[harness] session_start hook error: {e}", file=sys.stderr)
        sys.exit(0)
