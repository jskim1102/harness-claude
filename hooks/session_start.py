#!/usr/bin/env python3
"""SessionStart hook. Reads HARNESS_ROLE env, prints role.md to stdout.

Claude Code feeds hook stdout into the session prompt (additional context),
which is how role information gets injected at session start.
"""
import json
import os
import re
import sys
from pathlib import Path

PLUGINS = Path(__file__).resolve().parent.parent / "plugins"
CEO_SESSION_ID_FILE = Path.home() / ".harness-claude" / "ceo-session.id"

_payload_cache: dict | None = None


def _payload() -> dict:
    """훅 stdin(JSON) 을 한 번만 읽어 캐시한다. stdin 은 한 번밖에 못 읽는다."""
    global _payload_cache
    if _payload_cache is None:
        try:
            raw = sys.stdin.read()
            parsed = json.loads(raw) if raw.strip() else {}
            _payload_cache = parsed if isinstance(parsed, dict) else {}
        except Exception:
            _payload_cache = {}
    return _payload_cache


def _record_session_id(role: str) -> None:
    """세션 id 를 파일로 남긴다 — `./run.sh ceo`/`add-cto` 가 이걸로 대화를 복원한다.

    (2026-07-28) pty 가 죽으면 대화가 통째로 날아갔다. 트랜스크립트는 디스크에
    그대로 남으므로 id 만 알면 `--resume` 로 잇는다. resume 로 뜬 세션도 id 가 같아
    파일 내용은 그대로 유지된다. CEO 는 `stop-ceo` 가 이 파일을 지워 "기억 소멸"
    의미를 지키고, CTO 는 `stop-cto` 가 재개 전제라 유지하며 `delete-cto` 만 지운다.
    실패해도 세션 시작을 막지 않는다(fail-open).
    """
    if role == "ceo":
        target = CEO_SESSION_ID_FILE
    else:
        # cto:<name> / designer-cto:<name> — 이름은 run.sh 가 kebab-case 로
        # 검증하지만, 파일명이 되므로 여기서도 화이트리스트로 다시 조인다
        # (경로 조작 방지).
        name = role.split(":", 1)[1] if ":" in role else ""
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            return
        if role.startswith("designer-cto:"):
            target = CEO_SESSION_ID_FILE.parent / f"cto-designer-session-{name}.id"
        else:
            target = CEO_SESSION_ID_FILE.parent / f"cto-session-{name}.id"
    sid = _payload().get("session_id")
    if not isinstance(sid, str) or not sid:
        return
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(sid + "\n", encoding="utf-8")
    except OSError as e:
        print(f"[harness] could not record session id for {role} ({e})", file=sys.stderr)


def _team_was_spawned(name: str) -> bool:
    """이 CTO 가 과거에 팀을 스폰한 적 있는지 — skill-activity.log 스캔."""
    log = CEO_SESSION_ID_FILE.parent / "skill-activity.log"
    try:
        with open(log, encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if f"[cto:{name}]" in line and "harness-team-spawn" in line:
                    return True
    except OSError:
        pass
    return False


def main() -> None:
    role = os.environ.get("HARNESS_ROLE")
    if not role:
        return
    if role == "ceo" or role.startswith(("cto:", "designer-cto:")):
        _record_session_id(role)
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
    # 분해→segment 루프 운영 흐름 (PROCESS.md 가 정본);
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

    # Final guard: PROCESS.md contains the later build stages for reference,
    # but `/start-project` is deliberately spawn-only. Put this instruction at
    # the end of injected context so it wins over descriptive stage procedures
    # earlier in role/PROCESS text.
    if role_dir == "cto":
        body += """

---

### STARTUP OVERRIDE (하네스 강제)

`/start-project` 턴에서는 팀 spawn만 수행한다. 이 턴에 plan.md, specs, tasks,
phase, ckpt, segment를 읽거나 생성·검증하지 말고, planner/designer/reviewer에게
업무·분해·orientation·review 메시지를 보내지 않는다. 세 teammate가 준비되면
상태만 보고하고 대기한다. 실제 작업은 사용자가 이후 CTO에게 명시적으로 지시하고
CTO가 해당 teammate에게 dispatch한 뒤에만 시작한다.
"""

    # CTO only: 재개(resume)된 세션은 in-process 팀원이 이전 lead 프로세스와
    # 함께 이미 소멸한 상태다. 이전 대화 컨텍스트가 "팀 있음"을 암시해 죽은
    # 팀에 SendMessage 하다 미궁에 빠진다 (2026-07-29 rtsp-keypoint msg#552).
    # 과거 스폰 이력이 있는 재개 세션에만 사실을 결정론으로 주입한다.
    if role_dir == "cto" and _payload().get("source") == "resume":
        cto_name = role.split(":", 1)[1] if ":" in role else ""
        if cto_name and _team_was_spawned(cto_name):
            body += """

---

### RESUMED SESSION — 팀원 소멸 (하네스 강제)

이 세션은 `--resume` 으로 재개됐다. in-process 팀원(planner/designer/reviewer)은
이전 lead 프로세스와 함께 **이미 소멸**했다 — 이전 대화에 팀이 살아 있었어도
지금은 없다. 팀 작업 전 `/start-project` 로 재스폰하라. 재스폰 전에는
SendMessage(planner|designer|reviewer) 가 전부 실패한다.
"""

    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": body}}
    print(json.dumps(out))


def _read_project_memory() -> str:
    """Return the project's accumulated harness-memory.md as injectable
    context, or "" if absent/empty. Derives the project root from the hook
    payload's cwd (falling back to os.getcwd()). Never raises.
    """
    cwd = _payload().get("cwd")
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
