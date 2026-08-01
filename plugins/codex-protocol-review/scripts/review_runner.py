#!/usr/bin/env python3
"""Run the cross-model Codex protocol-review agent for harness-claude."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

from report_writer import (
    ProtocolReviewContext,
    build_failure_report,
    embed_launch_id,
    ensure_report_shape,
    summarize_report,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = PLUGIN_ROOT / "AGENT.md"
DEFAULT_MODEL = os.environ.get("CODEX_PROTOCOL_REVIEW_MODEL", "gpt-5.5")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        context = build_context(args)
        validate_context(context)
    except ValueError as exc:
        print(f"codex-protocol-review: {exc}", file=sys.stderr)
        return 2

    codex_bin = require_binary(args.codex_bin, "codex")
    harness_bin = shutil.which(args.harness_bin) if not args.no_send else None
    if not codex_bin:
        return fail_before_codex(context, "Could not find the `codex` CLI.", args)

    context.report_path.parent.mkdir(parents=True, exist_ok=True)
    prompt = build_prompt(context)
    command = build_codex_command(codex_bin, context)
    result = subprocess.run(
        command,
        input=prompt,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    if result.returncode != 0:
        report = build_failure_report(
            context,
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
        write_report(context, report)
    else:
        raw_report = read_report(context.report_path)
        report = ensure_report_shape(raw_report, context)
        write_report(context, report)

    summary = summarize_report(report, context, exit_code=result.returncode)
    print(summary)

    if args.no_send:
        return result.returncode
    if not harness_bin:
        print("codex-protocol-review: could not find `harness`; report was written but not sent.", file=sys.stderr)
        return 127

    send_result = send_to_ceo(harness_bin, summary)
    if send_result.returncode != 0:
        print(send_result.stderr.strip(), file=sys.stderr)
        return send_result.returncode
    return result.returncode


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only cross-model Codex protocol review for harness-claude.",
    )
    parser.add_argument("--repo", required=True, help="harness-claude repo root")
    parser.add_argument("--report", required=True, help="Harness-side report output path")
    parser.add_argument("--launch-id", help="Unguessable id bound to this launch; embedded into the report so --consume can verify report<->launch")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Codex model to use; defaults to CODEX_PROTOCOL_REVIEW_MODEL or gpt-5.5")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI binary")
    parser.add_argument("--harness-bin", default="harness", help="Harness CLI binary")
    parser.add_argument("--no-send", action="store_true", help="Write the report but skip harness send")
    return parser.parse_args(argv)


def build_context(args: argparse.Namespace) -> ProtocolReviewContext:
    return ProtocolReviewContext(
        repo_path=Path(args.repo).expanduser().resolve(),
        report_path=Path(args.report).expanduser().resolve(),
        model=args.model,
        launch_id=args.launch_id,
    )


def validate_context(context: ProtocolReviewContext) -> None:
    if not context.repo_path.is_dir():
        raise ValueError(f"repo path is not a directory: {context.repo_path}")
    required = [
        context.repo_path / "plugins" / "_shared" / "RULES.md",
        context.repo_path / "plugins" / "_shared" / "PROCESS.md",
        context.repo_path / "plugins" / "ceo" / "role.md",
        context.repo_path / "plugins" / "cto" / "role.md",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"repo path is missing required harness files: {', '.join(missing)}")
    if path_is_inside(context.report_path, context.repo_path):
        raise ValueError("report path must be outside the harness repo")
    if not AGENT_PATH.is_file():
        raise ValueError(f"missing agent definition: {AGENT_PATH}")


def build_codex_command(codex_bin: str, context: ProtocolReviewContext) -> list[str]:
    return [
        codex_bin,
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(context.repo_path),
        "--ignore-user-config",
        "--ignore-rules",
        "-c",
        "project_doc_max_bytes=0",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--ephemeral",
        "--color",
        "never",
        "--model",
        context.model,
        "-c",
        'model_reasoning_effort="xhigh"',
        "--output-last-message",
        str(context.report_path),
        "-",
    ]


def build_prompt(context: ProtocolReviewContext) -> str:
    agent_definition = AGENT_PATH.read_text(encoding="utf-8")
    return f"""\
{agent_definition}

## Runtime Context Packet

- repo_path: {context.repo_path}
- report_path: {context.report_path}

You are running non-interactively from `repo_path` with a read-only sandbox.
First read the required authority and role files, then inspect the relevant
enforcers and tests. Your final response must be the complete Markdown report
and nothing else. The runner will save that final response to `report_path` and
send a summary to the CEO.
"""


def send_to_ceo(harness_bin: str, summary: str) -> subprocess.CompletedProcess[str]:
    sender = "codex-protocol-review:harness"
    env = os.environ.copy()
    env["HARNESS_ROLE"] = sender
    return subprocess.run(
        [
            harness_bin,
            "send",
            "--from",
            sender,
            "--to",
            "ceo",
            "--body-stdin",
        ],
        input=summary,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )


def fail_before_codex(context: ProtocolReviewContext, message: str, args: argparse.Namespace) -> int:
    context.report_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_failure_report(context, exit_code=127, stdout="", stderr=message)
    write_report(context, report)
    summary = summarize_report(report, context, exit_code=127)
    print(summary)
    if args.no_send:
        return 127
    harness_bin = shutil.which(args.harness_bin)
    if not harness_bin:
        print("codex-protocol-review: could not find `harness`; report was written but not sent.", file=sys.stderr)
        return 127
    send_result = send_to_ceo(harness_bin, summary)
    if send_result.returncode != 0:
        print(send_result.stderr.strip(), file=sys.stderr)
    return 127


def require_binary(binary: str, label: str) -> str | None:
    found = shutil.which(binary)
    if not found:
        print(f"codex-protocol-review: missing required `{label}` binary: {binary}", file=sys.stderr)
    return found


def write_report(context: ProtocolReviewContext, report: str) -> None:
    """Write the final report, embedding the launch_id marker for --consume."""
    context.report_path.write_text(
        embed_launch_id(report, context.launch_id), encoding="utf-8"
    )


def read_report(report_path: Path) -> str:
    if not report_path.is_file():
        return ""
    return report_path.read_text(encoding="utf-8")


def path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
