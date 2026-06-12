# Codex Review Agent — Cross-Model Code Review (Design + Build Spec)

> **Date**: 2026-06-09
> **Status**: design approved, pending user spec-review → handoff to Codex
> **Supersedes**: the earlier dogfood/black-box UAT design (dropped — user
> pivoted from browser dogfooding to **code review**).
> **Dual purpose**: (1) design record, (2) **build spec that Codex consumes to
> author the agent itself**. Claude writes this MD; **Codex builds the agent
> body**. Claude does NOT write the agent implementation.

## 1. Intent

When a harness project finishes (build PASS + deployed), add an independent
agent that **reviews the finished project's code with a different model** and
reports findings for a human to triage.

The reviewer's runtime brain is **Codex (GPT-5 family via the `codex` CLI)**,
NOT Claude. Rationale: the project was built and self-reviewed by Claude, so
Claude's own review inherits Claude's blind spots (correlated errors). A
*different* model reading the same code flags bugs, security issues, and
spec-divergence that Claude's self-review is structurally blind to. This lifts
the adversarial-verify pattern from cross-instance to **cross-model**.

This is **white-box**: Codex reads the full source. (The earlier dogfood design
was black-box; that constraint is gone — for code review, reading the code is
the point.)

## 2. Decorrelation rationale

The single load-bearing property: **the reviewer is a different model than the
builder.** Claude built and self-reviewed the code; Codex reviews it
independently. Plus a secondary layer:

- **Agent body authored by Codex** (bonus). Even the reviewer's own
  instructions are not Claude-written, so Claude's framing of "what counts as a
  bug / what to look for" does not leak into the review apparatus.
- **Independent of the build team.** It is a CEO-level agent, not a CTO
  teammate, so it does not share the build team's rationalizations.

Honest scoping: cross-model runtime is the real win; Codex-authored agent body
is a cheaper second-order bonus the user chose to keep.

## 3. Placement & lifecycle

- **CEO-level independent agent**, beside (not inside) the CTO build team.
- Invoked **after** a project is complete — manual trigger by the CEO, e.g. a
  `/codex-review <project>` command (working name `codex-review`; rename freely).
- One project per run, v1.

## 4. Minimal harness integration

The agent only **sends a report TO the CEO** — it never receives messages.
Therefore zero session/daemon/discovery integration:

- No tmux session registration, no `.claude/settings.json` hooks.
- The only harness touchpoint is the language-agnostic message bus:
  ```
  harness send --from codex-review:<project> --to ceo --body-stdin
  ```
  (`ceo` is always an allowed target; confirm exact flags with
  `harness send --help`.)

## 5. CEO responsibilities (per invocation)

The CEO assembles a per-run context packet and hands it to the agent:

- **Project path** (the codebase to review, e.g.
  `claude-module/<project>` or `claude-project/<project>`).
- **The spec/contract**: `.claude/specs/<slug>/spec.md` + `README.md` — so the
  reviewer can check **code-vs-intent divergence**, not just intrinsic bugs.
- **Report output path** — a harness-side path outside the target project
  (e.g. `~/.harness-claude/reviews/<project>/review-<timestamp>.md`), so the
  target is never written to.

The CEO launches Codex on the agent definition + this packet, then reads the
report and relays a triage summary to the user.

## 6. The review method (what Codex executes)

1. **Read** the full project source (backend + frontend) and the spec/contract.
2. **Review** across these categories:
   - **Correctness** — logic bugs, off-by-one, error handling, edge cases,
     race conditions, resource leaks.
   - **Security** — injection, authz/authn gaps, secret handling, unsafe input.
   - **Spec divergence** — where the code does not do what `spec.md`/README
     claims, or silently omits an acceptance criterion.
   - **Quality** — maintainability smells, dead code, dangerous shortcuts,
     misleading names/comments.
3. **Produce** structured findings (§7). Read-only: **never modify the target
   source, never commit.**
4. (Scope note) Full-codebase review via a custom prompt, NOT native diff
   review — harness projects are greenfield with no git base to diff against.
   Codex MAY internally use `codex review` tooling if it can review the whole
   tree, but the deliverable is the structured report.

## 7. Report schema (the deliverable)

Structured markdown (or JSON) to the report path + a short
`harness send --to ceo` summary. Each finding:

| field | meaning |
|---|---|
| `severity` | blocker / major / minor / nit |
| `category` | correctness / security / spec-divergence / quality |
| `location` | `file:line` (or range) |
| `issue` | what is wrong |
| `why` | impact / why it matters |
| `suggested_fix` | concrete remediation |
| `spec_ref` | violated spec/README claim, if any |

Plus a run header: project, files reviewed, counts by severity/category,
overall risk read. **No gate, no auto-fix loop in v1** — the human triages.

## 8. Open choices (decided for v1)

- **Review scope** → **full project codebase** (custom prompt), not native
  diff-review (no git base on greenfield harness projects).
- **Reads the spec** → yes. Unlike the dropped dogfood design, the reviewer
  SHOULD read `spec.md`/README to assess code-vs-intent divergence.
- **No auto-fix.** Findings are advisory; the human (and possibly a follow-up
  CTO task) acts on them.

## 9. What Codex must BUILD from this spec (the recursion)

Claude stops here. Codex consumes this MD and authors the agent under
`plugins/codex-review/`, following the conventions above:

1. **AGENT.md** — the reviewer's definition/prompt run at review time (Codex
   runtime): role, the §6 method + categories, the §7 report schema, the
   read-only / no-commit constraints.
2. **scaffolding** (e.g. `scripts/` or `drivers/`) — a review runner + report
   writer. Implementation is Codex's call (it may shell to its own `codex`
   review tooling or use a structured prompt); keep it runnable.
3. **run-review.sh** — the entry the CEO calls with the §5 context packet
   (project path, spec/README paths, report output path). It runs the review,
   writes the §7 report to the harness-side path, and
   `harness send --from codex-review:<project> --to ceo` a summary. Verify exact
   flags with `harness send --help`.
4. **README.md** — how to invoke, what it produces, the cross-model rationale.

Codex must NOT: modify the target project's source, commit anything, or write
outside `plugins/codex-review/` (except the report, which goes to the
harness-side report path in §5).

## 10. Success criteria

- A run produces a structured, triable review of the live project codebase
  across the §6 categories, checking code against the spec.
- The report reaches the CEO via the message bus and a report file.
- Bonus signal: it surfaces ≥1 real issue that Claude's own review/QA missed
  (the cross-model decorrelation payoff).

## 11. Explicit non-goals (v1)

- No automated gate blocking "done".
- No auto-fix / auto-feedback loop spawning CTO tasks.
- No multi-project parallelism.
- No browser / runtime dogfooding (that was the dropped design).
- Not a replacement for Claude-side `/review` / `/code-review` — this is the
  independent cross-model layer on top.
