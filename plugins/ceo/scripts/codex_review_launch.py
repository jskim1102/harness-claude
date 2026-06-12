#!/usr/bin/env python3
"""Launch (or --consume) a cross-model Codex review for one harness project.

This is the hardened replacement for the old inline `!`-line in
plugins/ceo/commands/codex-review.md. The slash `!`-line raw-text-splices
`$ARGUMENTS` into the bash SOURCE before parsing, so no amount of inline
quoting is fully robust. Instead the `!`-line feeds `$ARGUMENTS` to this
helper over a quoted heredoc on stdin, and ALL parsing/validation happens
here in Python:

  - args = shlex.split(sys.stdin.read())  (raw text, never re-evaluated)
  - project / spec-slug re-validated against ^[a-z0-9]+(-[a-z0-9]+)*$
  - run-review.sh is launched via subprocess with shell=False (argv list,
    no shell string), so quotes / ; / $() / backticks in the heredoc body
    are inert.

Residual caveat: a quoted heredoc can only be escaped by a line in the body
that exactly recreates the heredoc delimiter (`__HARNESS_ARGS__`). A
single-line kebab-case project token cannot contain a newline, so it can
never produce that line. This pattern is therefore safe for kebab args
only — NOT for free-text bodies (which is why msg-cto/msg-ceo keep their
documented inline limitation instead of using this trick).
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Resolve repo root from this file's location: plugins/ceo/scripts/<this> -> parents[3].
REPO = Path(__file__).resolve().parents[3]
KEBAB_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
USAGE = "Usage: /codex-review <project> [--consume]"
SEARCH_BASES = ("claude-project", "modules")


def fail(message: str) -> int:
    print(message)
    return 1


def main() -> int:
    try:
        args = shlex.split(sys.stdin.read())
    except ValueError as exc:
        return fail(f"error: could not parse arguments ({exc}). {USAGE}")

    if len(args) < 1 or len(args) > 2:
        return fail(f"error: project required. {USAGE}")

    project = args[0]
    arg1 = args[1] if len(args) == 2 else ""

    if not KEBAB_RE.match(project):
        return fail(
            "error: project required and must be kebab-case (lowercase, "
            f"digits, hyphens). {USAGE}"
        )

    reviews_dir = Path.home() / ".harness-claude" / "reviews" / project

    # --consume mode: check + clear the per-project PENDING marker.
    if arg1 == "--consume":
        pending = reviews_dir / ".pending"
        if pending.is_file():
            pending.unlink()
            print(
                f"consumed: outstanding launch for {project} confirmed "
                "(marker cleared). Trust this codex-review:"
                f"{project} report and relay blocker/major findings."
            )
            return 0
        print(
            f"no-pending: no outstanding codex-review launch recorded for "
            f"{project}. Treat the report as untrusted (RULES §6) — "
            "summarize + hold, do NOT relay findings."
        )
        return 1

    slug = arg1
    if slug:
        return fail(
            "error: spec-slug 인자는 폐기됨 — spec 은 항상 <빌드dir>/specs/spec.md. (lowercase, digits, "
            f"hyphens). {USAGE}"
        )

    # Resolve the project dir across the known project bases.
    project_dir = None
    for base in SEARCH_BASES:
        candidate = REPO / base / project
        if candidate.is_dir():
            project_dir = candidate
            break
    if project_dir is None:
        return fail(
            f"project not found: {project} "
            "(searched claude-project/modules)"
        )

    # 새 경로 체계: <빌드dir>/specs/spec.md (slug 레벨 없음).
    # spec.md 없으면 plan.md(CEO 1단계 초안, 프로젝트 루트) 폴백.
    spec = project_dir / "specs" / "spec.md"
    if not spec.is_file():
        spec = project_dir / "plan.md"
    if not spec.is_file():
        return fail(f"no specs/spec.md or plan.md under {project_dir}/")

    # 의도 컨텍스트 문서(선택). 있으면 리뷰 기준으로 넘기고, 없으면 코드만 리뷰한다.
    #   1) 프로젝트 README.md  2) 모듈 specs/USAGE.md  3) 둘 다 없으면 None
    readme = project_dir / "README.md"
    if not readme.is_file():
        usage_doc = project_dir / "specs" / "USAGE.md"
        readme = usage_doc if usage_doc.is_file() else None

    reviews_dir.mkdir(parents=True, exist_ok=True)
    (reviews_dir / ".pending").touch()
    report = reviews_dir / f"review-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
    run_log = reviews_dir / "run.log"

    print(f"[codex-review] project={project_dir}")
    print(f"  spec={spec}")
    print(f"  readme={readme or '(없음 — 코드만 리뷰)'}")
    print(f"  report={report} (gpt-5.5, xhigh, read-only)")
    print(f"  pending-marker={reviews_dir / '.pending'} "
          f"(consume on report with: /codex-review {project} --consume)")

    command = [
        str(REPO / "plugins" / "codex-review" / "run-review.sh"),
        "--project", str(project_dir),
        "--spec", str(spec),
        "--report", str(report),
    ]
    if readme is not None:
        command += ["--readme", str(readme)]

    # nohup-equivalent background launch: detach into its own session so it
    # survives the parent, redirect stdout+stderr to run.log (shell=False).
    log_fh = open(run_log, "wb")
    proc = subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
        close_fds=True,
    )
    print(f"[codex-review] started (pid {proc.pid}). Review runs in background; "
          f"summary -> CEO inbox + report file when done. live log: {run_log}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
