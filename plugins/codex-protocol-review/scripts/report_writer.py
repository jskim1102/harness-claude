#!/usr/bin/env python3
"""Report shaping and CEO summary helpers for Codex protocol review."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import textwrap


SEVERITIES = ("blocker", "major", "minor", "nit")
CATEGORIES = (
    "instruction-drift",
    "enforcement-gap",
    "trust-boundary",
    "workflow-risk",
    "test-gap",
    "quality",
)


@dataclass(frozen=True)
class ProtocolReviewContext:
    repo_path: Path
    report_path: Path
    model: str


def ensure_report_shape(report_text: str, context: ProtocolReviewContext) -> str:
    body = report_text.strip()
    if not body:
        return build_failure_report(
            context,
            exit_code=2,
            stdout="",
            stderr="Codex completed without producing a report.",
        )
    if body.startswith("# Codex Protocol Review Report") and "## Findings" in body:
        return body + "\n"

    header = textwrap.dedent(
        f"""\
        # Codex Protocol Review Report

        - Target: harness-claude
        - Repo path: {context.repo_path}
        - Reviewer: Codex protocol-review agent
        - Files reviewed: see report body
        - Counts by severity: {format_counts(count_terms(body, SEVERITIES), SEVERITIES)}
        - Counts by category: {format_counts(count_terms(body, CATEGORIES), CATEGORIES)}
        - Overall risk: unknown - Codex did not emit the standard header.

        """
    )
    return header + body + "\n"


def build_failure_report(
    context: ProtocolReviewContext,
    *,
    exit_code: int,
    stdout: str,
    stderr: str,
) -> str:
    return textwrap.dedent(
        f"""\
        # Codex Protocol Review Report

        - Target: harness-claude
        - Repo path: {context.repo_path}
        - Reviewer: Codex protocol-review agent
        - Files reviewed: 0
        - Counts by severity: blocker 1, major 0, minor 0, nit 0
        - Counts by category: instruction-drift 0, enforcement-gap 0, trust-boundary 0, workflow-risk 0, test-gap 0, quality 1
        - Overall risk: critical - the protocol review runner failed before producing findings.

        ## Findings

        ### 1. Codex protocol review did not complete

        - severity: blocker
        - category: quality
        - location: n/a
        - issue: The Codex CLI protocol-review process exited with status {exit_code}.
        - why: The CEO did not receive an independent protocol-review result, so the harness still lacks the requested cross-model audit signal.
        - suggested_fix: Check Codex CLI authentication/configuration, confirm the harness repo is readable, then rerun this agent.
        - authority_ref: `plugins/ceo/commands/codex-protocol-review.md`

        ## Runner Diagnostics

        stdout:

        ```text
        {tail_text(stdout)}
        ```

        stderr:

        ```text
        {tail_text(stderr)}
        ```
        """
    )


def summarize_report(report_text: str, context: ProtocolReviewContext, *, exit_code: int) -> str:
    severity_counts = count_terms(report_text, SEVERITIES)
    category_counts = count_terms(report_text, CATEGORIES)
    risk = extract_overall_risk(report_text)
    status = "complete" if exit_code == 0 else f"failed with exit {exit_code}"

    return textwrap.dedent(
        f"""\
        Codex protocol review {status} for harness-claude.
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
