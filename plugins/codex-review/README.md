# Codex Review Plugin

`codex-review` is a CEO-level, cross-model **real-use risk** review for builds
that already work. It invokes the local `codex` CLI with a GPT-5-family model,
reads the full project source, writes a structured report to a harness-side
path, and sends a short summary to `ceo`.

It does **not** check whether the build works or matches its spec. The CTO
team's in-build reviewer already did that (curl/pytest API tests, read-only SQL
integrity checks, netbind scan) and the user's browser gate confirmed it. This
review starts from "it works" and asks what it costs later, across four axes:

- `security` — auth/authz gaps, secret handling, input trust boundaries,
  injection, insecure defaults — judged against the target's **actual exposure**
- `scale` — what degrades as users and traffic grow (N+1, missing indexes,
  unbounded result sets, pool exhaustion, blocking I/O, no backpressure)
- `data-growth` — what breaks as data and time accumulate (tables that only
  grow, no retention, log/disk exhaustion, locking migrations, no backup)
- `operations` — whether a live incident can be diagnosed and recovered from
  (swallowed exceptions, silent failure, no state visibility, no rollback,
  leaks that surface only after long uptime)

Every finding must carry a `trigger` — the concrete condition that makes it
fire ("~50 concurrent users", "events table past 1M rows", "30 days uptime").
A finding with no trigger is not a real-use risk and is dropped.

The point is decorrelation plus reach: Claude built and self-reviewed the
project, and the in-build reviewer is bound to one segment at a time. A Codex
reviewer reads the finished tree independently, on axes nobody in the build
loop can observe.

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
  --report ~/.harness-claude/reviews/<project>/review-<timestamp>.md \
  --launch-id <unguessable-id>   # embedded into the report; --consume verifies report<->launch
```

Equivalent positional form:

```bash
plugins/codex-review/run-review.sh PROJECT_PATH SPEC_PATH README_PATH REPORT_PATH
```

Optional flags:

- `--project-name <name>`: sender/report project name. Defaults to the project
  directory name.
- `--target-type module|project`: defaults to `project`. `module` tells the reviewer
  the target is a component destined for an unknown host, so the question becomes
  whether host expectations (who validates input, who cleans up, is it concurrency-safe)
  are **stated as a contract** in `specs/USAGE.md` — an unstated assumption is the
  module's own risk because every derivative inherits it silently. Real secrets/keys
  committed into the tree stay blocking. Set automatically by `codex_review_launch.py`
  from the target's parent dir (`modules/` vs `claude-project/`). See RULES §7.
- `--model <model>`: Codex model. Defaults to `CODEX_REVIEW_MODEL` or `gpt-5.5` (reasoning effort `xhigh`).
- `--no-send`: write the report but skip `harness send`.

## Output

The report is Markdown with:

- Run header: project, paths, files reviewed, severity/category counts, overall
  risk.
- Findings with `severity`, `category`, `location`, `issue`, `why`, `trigger`,
  and `suggested_fix`.
- Optional notes for scope limitations.

The reviewer also receives an **Operational Context** block built by
`review_runner.py`: the project's `docs/PORT.md` row, docker-compose files
present, `.env` **key names only** (values are never sent — they hold real
secrets), and a static external-bind scan. Exposure is what separates a
`blocker` from a `minor` for the same code, so it is supplied as fact rather
than left to the model to guess.

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
