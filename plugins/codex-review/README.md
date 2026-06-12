# Codex Review Plugin

`codex-review` is a CEO-level, cross-model code-review agent for completed
harness projects. It invokes the local `codex` CLI with a GPT-5-family model,
reviews the full project source against the spec and README, writes a structured
report to a harness-side path, and sends a short summary to `ceo`.

The point is decorrelation: Claude may have built and self-reviewed the
project, so a Codex reviewer reads the same code independently and reports
bugs, security issues, spec divergence, and quality risks for human triage.

## Files

- `AGENT.md`: runtime reviewer definition and report schema.
- `run-review.sh`: CEO entrypoint.
- `scripts/review_runner.py`: validates the context packet, invokes `codex exec`
  in read-only mode, and sends the CEO summary.
- `scripts/report_writer.py`: normalizes the report and extracts summary counts.

## Invocation

Named arguments:

```bash
plugins/codex-review/run-review.sh \
  --project /path/to/project \
  --spec /path/to/project/specs/spec.md \
  --readme /path/to/project/README.md \
  --report ~/.harness-claude/reviews/<project>/review-<timestamp>.md
```

Equivalent positional form:

```bash
plugins/codex-review/run-review.sh PROJECT_PATH SPEC_PATH README_PATH REPORT_PATH
```

Optional flags:

- `--project-name <name>`: sender/report project name. Defaults to the project
  directory name.
- `--model <model>`: Codex model. Defaults to `CODEX_REVIEW_MODEL` or `gpt-5.5` (reasoning effort `xhigh`).
- `--no-send`: write the report but skip `harness send`.

## Output

The report is Markdown with:

- Run header: project, paths, files reviewed, severity/category counts, overall
  risk.
- Findings with `severity`, `category`, `location`, `issue`, `why`,
  `suggested_fix`, and `spec_ref`.
- Optional notes for scope limitations.

After writing the report, the runner sends:

```bash
harness send --from codex-review:<project> --to ceo --body-stdin
```

The runner sets `HARNESS_ROLE` to the same sender for that subprocess so the
message bus accepts the explicit `--from` role.

## Safety

- Codex runs with `--sandbox read-only`, `--ask-for-approval never`, and
  `--ephemeral`.
- The report path must be outside the target project.
- The agent never modifies target source, commits, pushes, creates PRs, or
  auto-fixes findings.
- This is a full-codebase prompt-based review, not native diff review.
