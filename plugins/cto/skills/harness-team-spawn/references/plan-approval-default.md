# Plan approval — on by default for every teammate

This reference applies only after the CTO explicitly dispatches work. The
`/start-project` spawn-only turn performs no teammate action and requires no
plan approval.

This file is about why, and how to run the gate efficiently so it does
not become a bottleneck.

## Why default-on

In `harness-claude` the CTO is the only quality gate between teammate
output and the user. Three properties of the harness make up-front
approval cheaper than after-the-fact rework:

1. **Teammates run in in-process mode (`teammateMode: in-process`).** The
   lead is a plain `claude` session; the Orca tab keeps the fixed cockpit
   rail — CTO left, right rail of skill activity plus read-only teammate
   transcript viewers.

2. **The 95% confidence rule for `tasks.md`.** The planner cannot
   finalize `tasks.md` below 95% confidence. Approval at the spec
   stage is where that confidence gets calibrated — if you reject a
   plan with "this skips the auth scope", the planner re-grills,
   producing a higher-confidence final spec.

3. **`TaskCompleted` hooks verify by sentinel file.** Once a teammate
   marks a task done, the hook checks
   `~/.claude/logs/verified/<team>/task-<id>.verified` exists. If the
   underlying plan was wrong, the sentinel still gets written; the
   wrong work passes verification and lands. Plan approval catches
   the wrong plan before any sentinel ever gets near being written.

## What "approve a plan" looks like in practice

The teammate's plan arrives as a SendMessage. You respond with one of:

- **`APPROVED`** — single word, teammate proceeds.
- **`APPROVED with note: <note>`** — teammate proceeds, and carries the
  note back as a `<decision>` block for you to file in `decisions.md`.
- **`REJECTED — <reason>`** — teammate revises and re-submits.

Approval criteria (in order — bail at first failure):

1. **spec.md alignment.** Does the plan match the spec? If the spec
   says SQLite for local dev and the developer's plan uses Postgres,
   reject with the discrepancy.
2. **Scope.** Anything the user did not ask for? No silent expansion,
   no "while I'm here" cleanups.
3. **Open unknowns.** Does the plan's `## Unknowns` section name any
   actual open decisions? If so, reject — those should have been
   relayed to the user via `harness-relay-qa`, not buried.
4. **Destructive work explicit.** Is every destructive operation
   (DB migration, mass file delete, external API write) listed in a
   `## Destructive` section? If hidden inside a "refactor" bullet,
   reject and ask for it surfaced.

## When approval becomes a rubber-stamp

If you find yourself approving every plan in 5 seconds without
reading, two possibilities:

- **Teammates are well-calibrated.** Their plans are consistently
  scoped, unknowns surfaced, destructive work labeled. This is the
  win condition. Keep the gate — it costs nothing when plans pass.
- **You are skimming.** This is the risk. Set yourself a forcing
  question per plan: "what is one thing this plan does that the spec
  does not require?" If you can answer in <10 seconds it is well
  scoped; if you cannot answer, you did not read carefully.

The gate exists to catch the rare disaster, not to slow down the
common case. Approval should be fast when the plan is good; the gate
itself does not need to feel heavy.

## When to relax it

Rare cases where you may approve in bulk:

- **Tiny tasks (single file, single function).** A developer plan that
  reads "edit `src/foo.ts` to flip the boolean per spec.md line 47"
  does not need a full review.
- **Mechanical task groups.** Five `[review]` tasks generated from a
  template, each identical except for the file path.

The pattern: scan the first one carefully, approve the batch with a
note like `APPROVED batch — same shape as first, reviewed once`.

Do not relax it for:

- The planner's first spec (always full review).
- The designer's design-shotgun gate (variants are a user decision).
- Anything labeled destructive.
- Any teammate's first plan in a fresh team (calibration moment).
