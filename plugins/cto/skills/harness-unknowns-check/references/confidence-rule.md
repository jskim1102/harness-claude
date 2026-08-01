# Confidence rule (95%) — how to actually estimate it

The planner cannot finalize `spec.md` or write `tasks.md` below 95%
confidence. "95%" is not a vibe — it's the answer to a specific
checkable question:

> If I handed `spec.md` and `tasks.md` to the developer right now,
> how likely is it that they would build exactly what the user
> wanted, with zero further clarification rounds?

If your answer is "very likely, modulo some small detail" — you are
at 95%. If your answer is "probably, but I'd want to be available
for questions" — you are below 95%.

## Concrete checks (do these in order)

### Check 1: Can you predict every developer question?

Read `tasks.md` as if you were a developer who knows nothing about
this user. For each task, write down the questions you would have
to ask the planner before starting.

If your list has more than 1–2 small clarifications, you are below
95%. Resolve them in `spec.md` before finalizing.

### Check 2: Is every acceptance criterion observable?

Each task has acceptance criteria after the second pipe. Walk each
one and ask: "What command or observation tells me this is satisfied?"

If any acceptance criterion is subjective ("looks polished",
"handles the edge cases", "uses appropriate library"), you are
below 95%. The unknown is in the acceptance language itself.

### Check 3: Did you avoid every anti-pattern phrase?

Run `scripts/scan_for_hallucination_phrases.sh` against your spec
dir. If it exits non-zero, you are below 95% by definition — there
is a documented hallucination in the spec.

### Check 4: Is `## Unknowns` empty (or contains only logged
accepted-with-risk callouts)?

If `## Unknowns` has any open `- [ ]` entries with `relay to user`
as the resolution path, you are below 95% — there is a question
you know you need answered and haven't answered yet.

### Check 5: Could you defend each major decision in one sentence to the user?

For each non-obvious decision in the spec, can you write a single
sentence justifying it that the user would accept? If you find
yourself writing "well, it seemed reasonable because..." that is
below 95%.

## What to do when you're below 95%

Send another relay round. Batch the open `[user-q]` items if they
are independent; one at a time if they cascade. The cost of one
more round is much smaller than the cost of building the wrong
thing — empirically the planner who pushes one extra round saves
the user more time than they spend.

## What to do at 95%

In `spec.md`, add a Decisions section that states:

```markdown
## Decisions (planner confidence: 95%)

Self-resolved (logged):
- DB: Postgres — implied by goal ("scale to 1k DAU"); SQLite would
  fail durability. Reversible (one connection string).
- Email service: Resend — defaulted; low cost to swap.

Open accepted-with-risk:
- Color palette: deferred to designer's design-shotgun. Risk: design
  cycle adds 1 day if user vetoes all variants.

Resolved via relay:
- Auth provider: Supabase (user confirmed round 2).
- Email confirmation: yes, 60s cooldown (user confirmed round 3).
```

The CTO surfaces this section at handoff so the user can scan it
and veto anything they want re-decided. The user almost never
vetoes — but the surfaceability is what makes the 95% rule honest.

## Why 95% specifically and not 99% or 80%

99% is impossible in practice — there is always some interpretation
the user reserves for "I'll know it when I see it". Holding to 99%
makes the planner relay forever and the user disengage.

80% lets too much through. At 80%, a fifth of the decisions in
`tasks.md` are guesses, and a fifth of the developer's work will be
based on wrong assumptions. Re-work cost dominates.

95% is empirically the threshold where (a) the planner can defend
their choices to the user with brief rationale and (b) the build
phase produces the right artifact with at most one mid-flight
revision. It's a working number, not a derivation.

## The 95% rule and `## Unknowns` interaction

These are not redundant — they interact:

- `## Unknowns` is the workspace where open questions live during
  planning.
- The 95% rule is the gate at which `## Unknowns` must be empty
  (or only contain logged accepted-with-risk items).

You can finalize `spec.md` with `(none — all assumptions resolved
during interview)` in `## Unknowns`. You cannot finalize with even
one open `- [ ]` entry — you are by definition below 95% if you do.

## Estimating confidence on a project you have NOT seen before

The 95% rule applies even when you are brand new to the user's
codebase. The mechanism is the same:

- The goal contains some answers (read it carefully — Gotcha #5).
- The existing repo files contain other answers (`read <file>`
  resolution path).
- The user's relay answers contain the rest.

The 95% bar is about whether the answers exist somewhere you have
captured, not about whether you knew them on day one.
