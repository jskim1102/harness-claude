# Bypass tokens

Two tokens disable two different gates. They are not interchangeable
and they should not be reached for casually — every bypass is a piece
of verification the team gives up.

## The two gates

| Token | Bypasses | When checked | Use case |
| :---- | :------- | :----------- | :------- |
| `[skip-format-check]` | `TaskCreated` shape check | At task creation | Coordination / research tasks with no runnable verification |
| `[skip-verify]` | `TaskCompleted` sentinel check | At task completion | Docs-only tasks where there is genuinely nothing to run (never on `[review]` — see below) |

The tokens are matched as literal substrings (case-insensitive) anywhere
in the task subject or description. They do not need any specific
position.

Matching is not the same as being honored: at the `TaskCompleted` gate
both tokens are **ignored** on a `[review]` task, no matter where they
appear. See "`[skip-verify]` — the `[review]` exception" below.

## `[skip-format-check]` — legitimate cases

Cases where the format genuinely does not apply:

- **Read-and-brief**: "read `docs/architecture.md` and prepare 3
  questions for grill-me round 2." No file output, no command to run.
- **Wait-for-other-teammate**: "block until designer publishes
  `DESIGN.md`, then claim the dependent UI tasks." Coordination only.
- **Env / scaffolding setup that produces no specific artifact**:
  "install team-shared dev dependencies as listed by developer."

Common pattern: the task is a step in the lifecycle but does not
produce a checkable artifact at the file level. The teammate's
self-report is the only signal available.

## `[skip-format-check]` — anti-cases

Cases where reaching for the token is the wrong move:

- A `[dev]` task that produces code. If there is code, there is
  something to test. Write the test, write the `Run:`, do not skip.
- A `[design]` task that produces a mockup. There is at minimum a file
  to `ls`. Skipping the format check means the reviewer has no idea
  what "done" means.
- "I don't know what acceptance to write yet." That is a sign the spec
  is underspecified — go back to the planner, not the bypass token.

The smell test: if a downstream teammate (reviewer, the next group's
developer) would not know how to tell whether the task succeeded
without reading the teammate's prose log, the bypass is being misused.

## `[skip-verify]` — legitimate cases

The completion sentinel exists because the hook cannot see the
teammate's transcript. The teammate's only attestation that
verification ran is the sentinel file. `[skip-verify]` exempts the
task from that attestation requirement — on every task type **except
`[review]`** (see the next section).

Legitimate cases:

- **CHANGELOG / docs edits**: nothing meaningful to run beyond "I
  changed the file."
- **README typo fixes**: no test, no build.
- **`decisions.md` log entries**: a planner-authored ADR row.

Even here, a cheap `Run:` is preferable when one exists. `Run: test -s
CHANGELOG.md` is better than `[skip-verify]` because it at least
proves the file is non-empty.

## `[skip-verify]` — the `[review]` exception

**On a `[review]` task, `[skip-verify]` is IGNORED.** The completion-gate
hook does not honor it there (a model must not be able to self-waive
mandatory review evidence by typing a token into `tasks.md`). Writing
the token on a `[review]` task does nothing: the sentinel and the
code-review evidence are still required, and completion is still
blocked. `[skip-format-check]` is ignored there too — it still exempts
a `[review]` task from the *creation* shape check, but it buys no
exemption at completion.

The ONLY way to waive review for a segment is a per-segment waiver FILE
— outside `tasks.md`, written by the CTO only when the user said "이번
segment 검토 필요없음":

```
~/.harness-claude/review-waivers/<project>/<ckpt-id>.waiver   # tasks.md path (e.g. phase3.ckpt1.waiver)
~/.harness-claude/review-waivers/<project>/task-<id>.waiver    # task-store TaskCompleted path
```

Otherwise it is always review + code-review. See `reviewer.md` for the
reviewer-side statement of the same rule.

## `[skip-verify]` — anti-cases

- A `[dev]` task that touched source files. Even if no tests exist
  yet, `Run: npm run build` proves the code compiles. Use it.
- A `[design]` task that should produce a preview directory. `Run: ls
  design-preview/<x>/ | wc -l` is a 30-second check.
- "Tests are flaky." That is a bug to fix or a `[❓]` to file, not a
  reason to skip verification.

The smell test: if you skip verification on a task that actually has
runnable artifacts, the protocol's "Run before complete" guarantee is
compromised — a teammate can mark `completed` without ever running
anything, and the reviewer learns of the gap only on FAIL.

## Audit trail when you use a bypass

The hook logs every allow / block decision to
`~/.claude/logs/team-hooks.jsonl`. When a bypass is used, the log line
records the bypass token. Future code-reviews of the team's behavior
can grep for `bypass token present` to find every place a gate was
skipped.

Best practice: when you use a bypass, add a short reason inline so a
later reader knows why:

```
[plan] [skip-format-check] read docs/architecture.md and brief team — coordination task, no artifact.
[plan] update CHANGELOG with auth-signup entry | CHANGELOG.md | [skip-verify] entry visible at top. Run: head -5 CHANGELOG.md
```

The inline reason does not affect the hook — but it is the only signal
to a reviewer that the bypass was deliberate.

## Why no other bypasses exist

There is no `[skip-claim]` or `[skip-role]`. The role tag and the
claim lifecycle are load-bearing for the entire teammate-routing
system; skipping them would mean tasks the wrong teammate claims, or
no teammate claims at all. The two bypasses cover the verification
gates only.
