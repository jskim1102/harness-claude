---
name: harness-unknowns-check
description: Use when authoring or reviewing any harness-claude spec doc — planner about to finalize specs/spec.md + specs/tasks.md, designer handing off the phase2 design, reviewer evaluating spec or a verification report for invented facts or a missing `## Unknowns` section. Triggers any time you catch yourself reaching for "assume the user wants...", "typical pattern is...", or "the framework usually..." — hallucination tells this skill is the antidote to. Also triggers when CTO is reviewing teammate output for invented facts, a spec file is missing its `## Unknowns` section, or a planner is below 95% confidence and about to ship anyway.
---

# harness-unknowns-check

Spec, design, and review docs in our harness all share one failure
mode: a teammate hits an unanswered question, doesn't want to burn a
relay round, and silently fills the gap with a plausible-sounding
guess. The plan reads as if everything is known; the build proceeds;
the user discovers at handoff that "auth provider" was never actually
decided — the planner just wrote "Supabase" because it was top-of-mind.

This skill is the self-check that prevents that. Every spec / design /
review file carries a `## Unknowns` section, every unknown carries a
resolution path, anti-pattern phrases trigger an immediate stop, and
the 95% confidence rule keeps planners honest. This file is the
overview — depth lives in `references/`.

## The `## Unknowns` section

`specs/spec.md` reserves a top-level
`## Unknowns` section. Empty is the goal — if everything is resolved,
write `(none — all assumptions resolved during interview)`. A missing
section is itself a hallucination signal (CTO review treats it as
automatic FAIL).

When unknowns are open, each line is a markdown checkbox with a
resolution path:

```markdown
## Unknowns
- [ ] auth provider (Supabase / Auth0 / roll-our-own) — relay to user
- [ ] does the existing repo have a DESIGN.md? — read ./DESIGN.md
- [ ] does `lint` pass on the current main? — run `npm run lint`
```

Resolution paths are concrete: `relay to user` (via `[user-q]`),
`ask <teammate>`, `read <file>`, `run <command>`. "TBD" is not a
resolution path. Full taxonomy plus bad examples in
`references/resolution-paths.md`.

## Resolution gates per role

Different roles have different points at which open unknowns become
disqualifying:

- `planner` — cannot author `tasks.md` while `spec.md` has open
  unknowns. Either resolve or downgrade-and-log.
- `designer` — cannot pass 게이트2 (라이브 디자인 루프 승인) while
  visual / interaction unknowns are open. Use `design-shotgun` to
  resolve via variants rather than text Q&A.
- `developer` — cannot claim a `[dev]` task whose acceptance criteria
  contain unknowns. `[!]` the task and message the planner.
- `reviewer` — any open unknown in the verification report (SendMessage)
  at verdict time is automatic FAIL.

The role-by-role rationale (and why the reviewer gate is hardest)
lives in `references/resolution-gates.md`.

## Anti-pattern phrases — STOP signals

Four canonical phrases trigger an immediate stop: `"assume the user
wants ..."`, `"typical pattern is ..."`, `"standard convention says
..."`, `"the framework usually ..."`. These are the tells a model
leaves when papering over a missing fact. Convert to a `## Unknowns`
entry with a resolution path instead.

Run `${CLAUDE_SKILL_DIR}/scripts/scan_for_hallucination_phrases.sh` against your spec
dir before finalizing — it greps for the four phrases and exits
non-zero with file:line hits. Full phrase list, near-synonyms, and
conversion recipe in `references/anti-pattern-phrases.md`.

## 95% confidence rule (planner)

The planner cannot finalize `spec.md` below 95% confidence. Send
another `[user-q]` relay round (batch if independent). See
`references/confidence-rule.md` for the check protocol and the
Decisions-section format.

## Downgrade path: accepted-with-risk

When relay is impossible — lead unavailable, user said "use your
judgment", or the unknown is genuinely low-stakes and reversible —
the planner may downgrade an unknown to "accepted-with-risk" and log
it in `decisions.md` with a one-line rationale. The user reads
`decisions.md` at CTO check-in and can veto. The difference between
a logged downgrade and a silent guess is surfaceability — silent
inventions ship wrong. Full protocol (when downgrade is legal vs
not, log format, sweeping multiple downgrades) is in
`references/downgrade-protocol.md`.

## Gotchas

The lessons in this section are the ones we have actually been burned
by. Read them before reaching for the protocol.

### 1. Missing `## Unknowns` section is itself a hallucination signal

A spec without an Unknowns section is not "a spec with zero unknowns"
— it is "a spec that did not self-check". The CTO cannot tell from
outside whether the author resolved everything or skipped the
section. Treat it as FAIL on review. If everything is genuinely
resolved, write `(none — all assumptions resolved during interview)`.
The literal "none" is much cheaper than the ambiguity of an absent
section.

### 2. "TBD" is not a resolution path

"TBD" / "decide later" / "figure out in <phase>" push the unknown
forward without specifying who resolves it, how, or when. The whole
point of the resolution path is to make the next action concrete and
assignable. The unknown gets listed but doesn't get resolved — the
build proceeds with the same ambiguity. See
`references/resolution-paths.md` for the full bad-path taxonomy
(TBD, "decide later", "do research", "depends on X") with worked
examples of each.

### 3. Gates catch open unknowns, not silent assumptions

The gates check `## Unknowns` for open `- [ ]` lines — they do not
catch assumptions that were never written down. A planner who
silently decides "auth provider = Supabase" and skips both the
unknowns entry AND the `decisions.md` log passes every gate cleanly.

This is what the scanner and anti-pattern phrases backstop: silent
assumptions leave a verbal fingerprint ("typical pattern is...")
even when they leave no structural one. A clean scanner + empty
Unknowns + no Decisions log is the suspicious state — usually
means the author self-resolved without leaving a trail. CTO review
should ask "what did you decide and why?" on any spec shaped like
that.

### 4. The anti-pattern phrases are a model fingerprint, not a style choice

These phrases sound like professional writing, which is why they slip
past self-review. Do not rewrite to soften (`"a common pattern is..."`
is the same hallucination with a fig leaf) — convert to an unknown.
Full near-synonym list ("best practice is", "we'll likely want",
"should probably", etc.) and the conversion recipe is in
`references/anti-pattern-phrases.md`.

### 5. Implicit answers from the goal — self-answer, do not pad `## Unknowns`

The opposite failure mode of #4: listing things the user already
answered so the spec looks "thorough". This is the **goal-padding**
anti-pattern — listing items the goal already answered so the spec
looks thorough. `회원가입 페이지 만들어줘 (Next.js 14, Supabase)`
already answers framework and auth — those are settled facts, not
open questions.

Litmus test: would the user be annoyed to be re-asked? If yes, it's
implicit-answered — self-answer it and log in `decisions.md`. Full
self-answer-vs-relay decision tree (with worked examples) lives in
`references/implicit-answers.md`.

### 6. Downgrades must be logged, never silent

Downgrading to accepted-with-risk is the legal escape valve; silent
guessing is not. A `decisions.md` line ("DB: Postgres —
accepted-with-risk; goal said 'scale to 1k DAU'") is reviewable at
CTO check-in. A spec that just says "Use Postgres" with no Unknowns
entry, no Decisions entry, no rationale is invisible until the build
ships wrong. Always log.

### 7. Don't let the design hand-off and `spec.md` disagree about what's unknown

Each file has its own `## Unknowns` scoped to its own domain, but the
same underlying ambiguity can appear in both — "auth provider"
affects spec (which API) and design (which UI flow). If spec resolves
it and design doesn't update, design ships with a stale unknown and
the developer gets conflicting signals.

When an unknown in one doc resolves, sweep the other docs in the same
spec slug for the same underlying question. The scanner's
`--cross-check` flag helps spot this (see
`references/anti-pattern-phrases.md`).

### 8. "Non-blocking 으로 만들었어요" — pending question 의 unilateral 전환

Variant of silent downgrade. Pattern looks like:
- `[user-q]` relayed, user hasn't answered yet
- Teammate or lead engineers a clever workaround so progress can
  continue without the answer (theme-agnostic build, abstract layer,
  feature flag, default + "swap later")
- The original unknown quietly disappears from `## Unknowns` and
  never appears in `decisions.md`
- Reported to user as "안 줘도 default 로 진행" / "non-blocking 처리"

Looks helpful. Is a protocol violation. The user's choice was
converted to the agent's choice without consent.

Why it matters: even when the workaround is technically reversible
(token swap, flag flip), the *decision authority* shifts from user to
agent. Repeat occurrences train the team to bypass relay rounds on
"easy" questions, until a non-reversible one slips through the same
pattern.

How to apply:
- Lead never accepts "made it non-blocking" as a resolution. Either
  the user answers, or the lead explicitly downgrades and logs
  ("user has not answered; accepted-with-risk: default <X>; will
  revisit if user picks otherwise") in `decisions.md`. Surface that
  log to the user — they may push back.
- Teammate engineering a reversible workaround is still useful —
  the *workaround* is fine, the *silent removal of the unknown* is
  not. Keep the entry in `## Unknowns` marked `pending user pick,
  default <X> applied with risk` until the user weighs in.
- If user explicitly says "쓸어버려 / 알아서" → that IS consent;
  log it that way in `decisions.md`.

## Files in this skill

- `SKILL.md` — this overview (always loaded when skill triggers).
- `references/resolution-paths.md` — full taxonomy of resolution
  paths (`relay` / `ask` / `read` / `run`) with bad examples.
- `references/resolution-gates.md` — role-by-role gate rationale,
  including why the reviewer gate is the hardest to honor.
- `references/anti-pattern-phrases.md` — the phrase list, why each
  is dangerous, and how to convert each to an unknown.
- `references/confidence-rule.md` — how to actually estimate your
  own confidence (it's not a vibe).
- `references/downgrade-protocol.md` — when accepted-with-risk
  downgrades are legal, log format, and review-time audit.
- `references/implicit-answers.md` — self-answer-vs-relay decision
  tree for the goal-padding anti-pattern (gotcha #5).
- `${CLAUDE_SKILL_DIR}/scripts/scan_for_hallucination_phrases.sh` — grep helper. Run
  against a spec dir; exits 0 clean / 1 hits / 2 usage error /
  3 cross-doc drift — see script header for the full table. Run
  before finalizing any spec doc.

## On-demand hook hint

If teammates keep finalizing specs without the `## Unknowns` section
or keep slipping anti-pattern phrases through, wire a `PreToolUse`
matcher on `Write` / `Edit` for paths matching `specs/`
that runs `${CLAUDE_SKILL_DIR}/scripts/scan_for_hallucination_phrases.sh`. Reject the
write on exit 1 (phrase hits) or 3 (cross-doc drift); bail rather
than reject on exit 2 (usage error — the hook is misconfigured, not
the author's mistake). The skill does not install the hook by
default — it is a tightening you apply only if you see drift in
practice. Same shape as the relay-prefix hook in `harness-relay-qa`.
