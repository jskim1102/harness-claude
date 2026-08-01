# Downgrade protocol: accepted-with-risk

When relay is impossible — lead unavailable, user explicitly said
"use your judgment", or the unknown is genuinely low-stakes — the
planner may downgrade an open unknown to "accepted-with-risk". This
is the escape valve. Without it, the 95% gate becomes impossible and
planners revert to silent guessing (the exact failure mode this skill
exists to prevent).

## When downgrade is legal

- **Lead unavailable.** SendMessage to the lead failed or has been
  unanswered past the relay timeout. See `harness-relay-qa`'s
  `references/lead-unavailable.md` for the fallback semantics.
- **User explicit license.** The user said something equivalent to
  "use your judgment on this" earlier in the session — the lead
  surfaces this when relaying back.
- **Low-stakes + reversible.** The decision is small, cheap to
  change, and not on a critical path. Email service provider with
  swappable connection string. Default copy voice that the designer
  can polish later.

## When downgrade is NOT legal

- The unknown is structural (auth provider, DB engine, data model).
  These shape the build; silent defaults compound.
- The user has not had a chance to weigh in and the lead is
  available. Try the relay first.
- You are the developer or designer. Only the planner downgrades.
  Other roles `[❓]` and surface.

## "Non-blocking 으로 만들었어요" — unilateral conversion of a pending question

The sharpest variant of silent downgrade, and the one most likely to
look like good work. Pattern:

- `[user-q]` relayed, user hasn't answered yet
- Teammate or lead engineers a clever workaround so progress can
  continue without the answer (theme-agnostic build, abstract layer,
  feature flag, default + "swap later")
- The original unknown quietly disappears from `## Unknowns` and never
  reaches `decisions.md`
- Reported to user as "안 줘도 default 로 진행" / "non-blocking 처리"

Looks helpful. Is a protocol violation — the user's choice was converted
to the agent's choice without consent.

Why it matters: even when the workaround is technically reversible
(token swap, flag flip), the *decision authority* shifts from user to
agent. Repeat occurrences train the team to bypass relay rounds on
"easy" questions, until a non-reversible one slips through the same
pattern.

How to apply:

- **Lead never accepts "made it non-blocking" as a resolution.** Either
  the user answers, or the lead explicitly downgrades and logs ("user
  has not answered; accepted-with-risk: default `<X>`; will revisit if
  user picks otherwise") in `decisions.md` — the lead owns that file, so
  this write is legal. Surface that log to the user; they may push back.
- Teammate engineering a reversible workaround is still useful — the
  *workaround* is fine, the *silent removal of the unknown* is not. Keep
  the entry in `## Unknowns` marked `pending user pick, default <X>
  applied with risk` until the user weighs in.
- If the user explicitly says "쓸어버려 / 알아서" → that IS consent; the
  lead logs it that way in `decisions.md`.

## The log format

Every downgrade lands in `decisions.md` with a one-line rationale
(two-line if the rationale needs context) — but the CTO files it, not
you. Emit it as a `<decision>` block in your completion `SendMessage`
(`agent-team-protocol.md` "Tagged Memory Blocks"); teammates have no
write access to `decisions.md`.

```markdown
## Decisions (planner — auth-signup, 2026-03-05)

- Email service: Resend — accepted-with-risk; reversible, low cost
  to swap. User did not specify; goal had no durability constraint.
- Default copy voice: friendly-direct — accepted-with-risk; designer
  can re-tune in design phase. Goal said "friendly" without specifics.
```

The format has three load-bearing parts:

1. **The decision** stated as if it were a normal commitment.
2. **The flag** (`accepted-with-risk`).
3. **The rationale**: why downgrade was legal (reversibility,
   low-stakes) and what the user didn't specify.

## Why downgrade differs from silent guess

A logged accepted-with-risk and a silent guess produce the same
artifact today. The difference shows up tomorrow:

- The user reads `decisions.md` on CTO check-in. They see "Resend —
  accepted-with-risk" and can say "no, use Postmark" or "fine".
- A silent guess produces a spec that says "Use Resend" with no
  rationale, no flag, no log. The user never sees it as a decision
  point; the build proceeds; the issue surfaces at deploy time when
  Resend is missing a domain DNS record they didn't know to set up.

The log is the surfaceability. Without it, the skill is doing nothing.

## Sweeping downgrades

If the planner downgrades several unknowns in one pass, the user is
about to scan a list of 5+ decisions at once. Group related ones,
keep rationales short, and put the highest-risk downgrade first so
the user sees it without scrolling.

```markdown
## Decisions (planner — auth-signup)

Highest-risk first:
- DB: Postgres — accepted-with-risk; required by goal's "scale to
  1k DAU" constraint; SQLite would fail durability.

Defaults (reversible):
- Email service: Resend.
- Session length: 7d.
- Form library: native HTML (no react-hook-form yet).
```

The user vetoes the top one if any. The defaults rarely get
challenged but they are still visible if anyone wants to.

## Downgrade audit at review time

The reviewer reads `decisions.md` as part of the verdict pass. Any
accepted-with-risk decision that turned out to be wrong (the build
hit it as a real problem) is a learning for the next planner cycle.
The reviewer flags it as "downgrade-cost: high" **in its verdict
message** — it writes no files — so future planners weight that class
of decision differently.

The reviewer does not retroactively veto a logged downgrade — that
power was the user's at CTO check-in. The reviewer's job is to
record the actual cost so the rule gets better.
