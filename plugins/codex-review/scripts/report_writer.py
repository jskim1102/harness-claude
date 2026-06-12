#!/usr/bin/env python3
"""Report shaping and CEO summary helpers for the Codex review runner."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import textwrap


SEVERITIES = ("blocker", "major", "minor", "nit")
CATEGORIES = ("correctness", "security", "spec-divergence", "quality")


@dataclass(frozen=True)
class ReviewContext:
    project_name: str
    project_path: Path
    spec_path: Path
    readme_path: Path | None
    report_path: Path
    model: str


def ensure_report_shape(report_text: str, context: ReviewContext) -> str:
    """Keep a valid report readable even if Codex omits the standard header."""
    body = report_text.strip()
    if not body:
        return build_failure_report(
            context,
            exit_code=2,
            stdout="",
            stderr="Codex completed without producing a report.",
        )

    # A title alone is not enough. A title-only / empty body would summarize as
    # "0 findings" and masquerade as a clean PASS to the CEO. Require the
    # standard `## Findings` section too; otherwise fall through to header
    # re-synthesis below (which sets risk "unknown"), so a malformed report
    # reads as malformed, not clean.
    if body.startswith("# Codex Review Report") and "## Findings" in body:
        return body + "\n"

    header = textwrap.dedent(
        f"""\
        # Codex Review Report

        - Project: {context.project_name}
        - Project path: {context.project_path}
        - Spec path: {context.spec_path}
        - README path: {context.readme_path or "(없음 — 코드만 리뷰)"}
        - Reviewer: Codex cross-model review agent
        - Files reviewed: see report body
        - Counts by severity: {format_counts(count_terms(body, SEVERITIES), SEVERITIES)}
        - Counts by category: {format_counts(count_terms(body, CATEGORIES), CATEGORIES)}
        - Overall risk: unknown - Codex did not emit the standard header.

        """
    )
    return header + body + "\n"


def build_failure_report(
    context: ReviewContext,
    *,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> str:
    """Create a triageable report when the Codex invocation itself fails."""
    stdout_tail = tail_text(stdout)
    stderr_tail = tail_text(stderr)
    return textwrap.dedent(
        f"""\
        # Codex Review Report

        - Project: {context.project_name}
        - Project path: {context.project_path}
        - Spec path: {context.spec_path}
        - README path: {context.readme_path or "(없음 — 코드만 리뷰)"}
        - Reviewer: Codex cross-model review agent
        - Files reviewed: 0
        - Counts by severity: blocker 1, major 0, minor 0, nit 0
        - Counts by category: correctness 0, security 0, spec-divergence 0, quality 1
        - Overall risk: critical - the review runner failed before producing findings.

        ## Findings

        ### 1. Codex review did not complete

        - severity: blocker
        - category: quality
        - location: n/a
        - issue: The Codex CLI review process exited with status {exit_code}.
        - why: The CEO did not receive an independent code-review result, so the project still lacks the requested cross-model review signal.
        - suggested_fix: Check Codex CLI authentication/configuration, confirm the project/spec/README paths are readable, then rerun this agent.
        - spec_ref: Codex review agent design section 9 requires a structured report and CEO summary.

        ## Runner Diagnostics

        stdout:

        ```text
        {stdout_tail}
        ```

        stderr:

        ```text
        {stderr_tail}
        ```
        """
    )


def summarize_report(report_text: str, context: ReviewContext, *, exit_code: int) -> str:
    severity_counts = count_terms(report_text, SEVERITIES)
    category_counts = count_terms(report_text, CATEGORIES)
    risk = extract_overall_risk(report_text)
    status = "complete" if exit_code == 0 else f"failed with exit {exit_code}"

    return textwrap.dedent(
        f"""\
        Codex review {status} for {context.project_name}.
        Report: {context.report_path}
        Model: {context.model}
        Severity counts: {format_counts(severity_counts, SEVERITIES)}
        Category counts: {format_counts(category_counts, CATEGORIES)}
        Overall risk: {risk}
        """
    ).strip()


def count_terms(report_text: str, terms: tuple[str, ...]) -> dict[str, int]:
    counts = {term: 0 for term in terms}
    for term in terms:
        patterns = [
            rf"(?im)^\s*-\s*(severity|category):\s*{re.escape(term)}\b",
            rf"(?im)\|\s*{re.escape(term)}\s*\|",
        ]
        counts[term] = sum(len(re.findall(pattern, report_text)) for pattern in patterns)
    return counts


def format_counts(counts: dict[str, int], ordered_terms: tuple[str, ...]) -> str:
    return ", ".join(f"{term} {counts.get(term, 0)}" for term in ordered_terms)


def extract_overall_risk(report_text: str) -> str:
    match = re.search(r"(?im)^\s*-\s*Overall risk:\s*(.+)$", report_text)
    if match:
        return match.group(1).strip()
    return "not reported"


def tail_text(value: str, *, max_chars: int = 4000) -> str:
    stripped = value.strip()
    if len(stripped) <= max_chars:
        return stripped
    return stripped[-max_chars:]
