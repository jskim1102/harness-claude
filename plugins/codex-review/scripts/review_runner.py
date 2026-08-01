#!/usr/bin/env python3
"""Run the cross-model Codex code-review agent for one harness project."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from report_writer import (
    ReviewContext,
    build_failure_report,
    embed_launch_id,
    ensure_report_shape,
    summarize_report,
)


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
AGENT_PATH = PLUGIN_ROOT / "AGENT.md"
DEFAULT_MODEL = os.environ.get("CODEX_REVIEW_MODEL", "gpt-5.5")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    # build_context can fail before a report_path is known (e.g. a missing
    # --report); there is nowhere to write a report, so keep the old
    # stderr + exit-2 behavior. Once the context exists the report_path IS
    # known, so a validate_context failure must not silently disappear: write
    # a failure report and send the CEO the same summary as the codex-execution
    # failure path, instead of only printing to stderr.
    try:
        context = build_context(args)
    except ValueError as exc:
        print(f"codex-review: {exc}", file=sys.stderr)
        return 2
    try:
        validate_context(context)
    except ValueError as exc:
        return fail_before_codex(context, f"Invalid review context: {exc}", args)

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
        env=review_env(),
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
        print("codex-review: could not find `harness`; report was written but not sent.", file=sys.stderr)
        return 127

    send_result = send_to_ceo(harness_bin, context, summary)
    if send_result.returncode != 0:
        print(send_result.stderr.strip(), file=sys.stderr)
        return send_result.returncode
    return result.returncode


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only cross-model Codex review for one harness project.",
    )
    parser.add_argument("positional", nargs="*", help="Optional positional form: PROJECT SPEC README REPORT")
    parser.add_argument("--project", help="Project source tree to review")
    parser.add_argument("--spec", help="Spec/contract path")
    parser.add_argument("--readme", help="README path")
    parser.add_argument("--report", help="Harness-side report output path")
    parser.add_argument("--project-name", help="Sender/report project name; defaults to project directory name")
    parser.add_argument("--target-type", choices=["module", "project"], default="project", help="Whether the target is a reusable module or a standalone project (modules: host-responsibility security is informational, RULES §7)")
    parser.add_argument("--launch-id", help="Unguessable id bound to this launch; embedded into the report so --consume can verify report<->launch")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Codex model to use; defaults to CODEX_REVIEW_MODEL or gpt-5.5")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI binary")
    parser.add_argument("--harness-bin", default="harness", help="Harness CLI binary")
    parser.add_argument("--no-send", action="store_true", help="Write the report but skip harness send")
    return parser.parse_args(argv)


def build_context(args: argparse.Namespace) -> ReviewContext:
    values = {
        "project": args.project,
        "spec": args.spec,
        "readme": args.readme,
        "report": args.report,
    }
    if args.positional:
        if len(args.positional) != 4:
            raise ValueError("positional usage requires exactly: PROJECT SPEC README REPORT")
        for key, value in zip(values, args.positional, strict=True):
            if values[key] is not None:
                raise ValueError(f"use either --{key} or positional arguments, not both")
            values[key] = value

    # readme 는 선택 — 의도 컨텍스트 문서가 없으면 코드만으로 리뷰한다.
    missing = [key for key in ("project", "spec", "report") if not values[key]]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join('--' + key for key in missing)}")

    project_path = Path(values["project"]).expanduser().resolve()
    spec_path = Path(values["spec"]).expanduser().resolve()
    readme_path = Path(values["readme"]).expanduser().resolve() if values["readme"] else None
    report_path = Path(values["report"]).expanduser().resolve()
    project_name = sanitize_project_name(args.project_name or project_path.name)

    return ReviewContext(
        project_name=project_name,
        project_path=project_path,
        spec_path=spec_path,
        readme_path=readme_path,
        report_path=report_path,
        model=args.model,
        target_type=args.target_type,
        launch_id=args.launch_id,
    )


def validate_context(context: ReviewContext) -> None:
    if not context.project_path.is_dir():
        raise ValueError(f"project path is not a directory: {context.project_path}")
    if not context.spec_path.is_file():
        raise ValueError(f"spec path is not a file: {context.spec_path}")
    if context.readme_path is not None and not context.readme_path.is_file():
        raise ValueError(f"README path is not a file: {context.readme_path}")
    if path_is_inside(context.report_path, context.project_path):
        raise ValueError("report path must be outside the target project")
    if not AGENT_PATH.is_file():
        raise ValueError(f"missing agent definition: {AGENT_PATH}")


REVIEW_CODEX_HOME = Path.home() / ".harness-claude" / "codex-review-home"


def review_env() -> dict:
    """독립 리뷰어 전용 CODEX_HOME 을 세운 환경을 돌려준다.

    왜 (2026-07-27): `--ignore-user-config` 는 config.toml 만 무시한다 —
    `$CODEX_HOME/skills/` 는 그대로 로드된다. 실측 결과 사용자 홈에 스킬이 46개
    있어, "독립" 교차모델 리뷰어가 매 리뷰마다 그 카탈로그를 컨텍스트에 싣고
    있었다(스킬 예산 경고 + 토큰 낭비 + 리뷰와 무관한 지침 오염).

    auth.json 만 심볼릭으로 빌려오고 나머지는 비운다. 리뷰어는
    `--sandbox read-only` 라 쓰기가 없으므로 hooks.json(git_guard) 이 없어도
    안전 계약이 약해지지 않는다. 실패하면 조용히 기존 환경으로 폴백한다 —
    격리 실패가 리뷰 자체를 막지는 않게.
    """
    env = os.environ.copy()
    try:
        REVIEW_CODEX_HOME.mkdir(parents=True, exist_ok=True)
        src = Path.home() / ".codex" / "auth.json"
        dst = REVIEW_CODEX_HOME / "auth.json"
        if src.exists() and not dst.exists():
            dst.symlink_to(src)
        if dst.exists():
            env["CODEX_HOME"] = str(REVIEW_CODEX_HOME)
    except Exception:
        pass
    return env


def build_codex_command(codex_bin: str, context: ReviewContext) -> list[str]:
    return [
        codex_bin,
        "--ask-for-approval",
        "never",
        "exec",
        "--cd",
        str(context.project_path),
        # N2 defense-in-depth: keep the TARGET repo's AGENTS.md / user config
        # from biasing the independent cross-model review. codex 0.138 already
        # prioritizes the reviewer prompt over a target AGENTS.md (verified by a
        # hostile-fixture test — baseline ignored "report no findings"), but
        # these flags add belt-and-suspenders isolation for future versions.
        # --ignore-rules closes the residual gap: without it a target-supplied
        # execpolicy .rules file could still affect the reviewer's tool policy.
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


def build_prompt(context: ReviewContext) -> str:
    agent_definition = AGENT_PATH.read_text(encoding="utf-8")
    if context.readme_path is not None:
        readme_line = f"- readme_path: {context.readme_path}\n"
        doc_instruction = (
            "First read `spec_path` and `readme_path` for intent, then enumerate "
            "and review the first-party project source."
        )
    else:
        readme_line = "- readme_path: (none — no intent doc; review code directly)\n"
        doc_instruction = (
            "First read `spec_path` for intent. No README/intent doc was supplied, "
            "so also scan the project tree for any other context docs (e.g. "
            "USAGE.md, docs/, design notes) and use them if present; otherwise "
            "review the first-party project source directly on its own merits."
        )
    if context.target_type == "module":
        target_note = (
            "\n## Target Type: MODULE (host-attached functional unit)\n\n"
            "This target lives under `modules/` — a reusable functional unit assembled "
            "into a HOST application, not a standalone deployed service. Authentication, "
            "network-exposure/bind, access-control, and input hardening are the HOST's "
            "responsibility: do NOT raise them as blocker/major security findings (note "
            "them as informational at most). Apply your security lens ONLY to issues the "
            "module itself owns — real secrets/credentials/private keys committed into "
            "the tree, which leak into every derivative and git history. Judge "
            "correctness and spec-divergence exactly as normal.\n"
        )
    else:
        target_note = ""
    return f"""\
{agent_definition}

## Runtime Context Packet

- project_name: {context.project_name}
- project_path: {context.project_path}
- spec_path: {context.spec_path}
{readme_line}- report_path: {context.report_path}
- target_type: {context.target_type}
{target_note}
You are running non-interactively from `project_path` with a read-only sandbox.
{doc_instruction} Your final response must be the complete Markdown
report and nothing else. The runner will save that final response to
`report_path` and send a summary to the CEO.
"""


def send_to_ceo(harness_bin: str, context: ReviewContext, summary: str) -> subprocess.CompletedProcess[str]:
    sender = f"codex-review:{context.project_name}"
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


def fail_before_codex(context: ReviewContext, message: str, args: argparse.Namespace) -> int:
    context.report_path.parent.mkdir(parents=True, exist_ok=True)
    report = build_failure_report(context, exit_code=127, stdout="", stderr=message)
    write_report(context, report)
    summary = summarize_report(report, context, exit_code=127)
    print(summary)
    if args.no_send:
        return 127
    harness_bin = shutil.which(args.harness_bin)
    if not harness_bin:
        print("codex-review: could not find `harness`; report was written but not sent.", file=sys.stderr)
        return 127
    send_result = send_to_ceo(harness_bin, context, summary)
    if send_result.returncode != 0:
        print(send_result.stderr.strip(), file=sys.stderr)
    return 127


def require_binary(binary: str, label: str) -> str | None:
    found = shutil.which(binary)
    if not found:
        print(f"codex-review: missing required `{label}` binary: {binary}", file=sys.stderr)
    return found


def write_report(context: ReviewContext, report: str) -> None:
    """Write the final report, embedding the launch_id marker for --consume."""
    context.report_path.write_text(
        embed_launch_id(report, context.launch_id), encoding="utf-8"
    )


def read_report(report_path: Path) -> str:
    if not report_path.is_file():
        return ""
    return report_path.read_text(encoding="utf-8")


def sanitize_project_name(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9_.:-]+", "-", value.strip())
    sanitized = sanitized.strip("-")
    return sanitized or "project"


def path_is_inside(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
