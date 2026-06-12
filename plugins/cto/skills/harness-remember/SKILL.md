---
name: harness-remember
description: Use when a session has surfaced a fact worth keeping and you must decide WHERE it belongs — the durable project memory file, a spec's decisions.md/learnings.md, a RULES/AGENTS/CLAUDE instructions file, or the user's MEMORY.md. Triggers when the user says "remember this", "잊지마", "메모해둬", "save this for later", when a teammate emits a `<learning>` / `<decision>` / `<issue>` block the CTO must file, when you catch a durable build/env/decision fact mid-session that the auto-accumulator won't catch on its own, or when two memory surfaces seem to disagree and you need to route rather than overwrite. This is a routing classifier, not a writer of last resort — its job is picking the right surface and refusing to dump everything into one.
---

# harness-remember

A session produces facts at four different lifetimes, and they belong on
four different surfaces. The failure mode this skill prevents is the lazy
one: dumping everything into whatever file is open, so durable team
knowledge rots in a spec dir that gets archived, or a one-off working note
pollutes a global rules file every future session has to read.

This is the routing layer. The `project_memory.py` PostToolUse hook already
captures the *mechanical* facts automatically (build/test commands actually
run, runtime versions, missing deps, hot paths) into the project memory
file — you do not re-file those. This skill handles the facts a hook
*can't* infer: decisions, learnings, conventions, operator preferences. It
mirrors the confidence discipline of `harness-unknowns-check` — uncertain
items are marked uncertain, and conflicts are FLAGGED, never silently
overwritten.

## The four surfaces

| Surface | Path | Lifetime | What belongs here |
| :------ | :--- | :------- | :---------------- |
| **Project memory** | `<project>/.claude/harness-memory.md` | durable, per-project | mechanical env/build facts. **Mostly auto-written by the hook.** Hand-append only a durable fact the hook structurally cannot see (e.g. "staging API requires `X-Tenant` header", "the flaky test is `test_payments::race` — rerun, don't trust first red"). |
| **Spec decisions / learnings** | `specs/decisions.md`, `.../learnings.md` | the life of this spec | choices made *for this feature* and gotchas discovered *while building it*. Default home for anything tied to the current work. |
| **Rules / AGENTS / CLAUDE** | `plugins/_shared/RULES.md`, project `CLAUDE.md`/`AGENTS.md` | durable, every session | a standing instruction or convention that should govern *all future sessions* — not a fact, a *rule*. The highest bar; see gate below. |
| **User MEMORY.md** | the user's auto-memory `MEMORY.md` | cross-project, personal | the operator's standing preferences and cross-project lessons. Only the **user** or an explicit user instruction writes here — never self-promote. |

## Routing decision tree

For each fact, ask in order — stop at the first match:

1. **Is it the user's standing preference or a cross-project lesson?**
   ("나는 항상 X 스타일로", "in every project, do Y") → **user MEMORY.md**,
   but only with explicit user intent. If the user did not ask you to
   remember it for them, do NOT write here — surface it and let them
   decide.

2. **Is it a *rule* that should govern every future session of this
   project** (a convention, a hard constraint, a "never do Z")? → a
   **rules/AGENTS/CLAUDE** file. This is the highest bar — see the
   promotion gate. When in doubt, it is NOT a rule yet; file it as a spec
   decision and let it earn promotion.

3. **Is it a decision or learning tied to the feature you are building
   right now?** → the spec's **decisions.md** (a choice + rationale) or
   **learnings.md** (a gotcha + what to do about it). This is the default
   bucket — most session facts land here.

4. **Is it a durable mechanical project fact the hook structurally cannot
   capture** (an env quirk, a non-obvious command, a flaky-test
   fingerprint)? → hand-append to **project memory**
   (`.claude/harness-memory.md`). Keep it to one line, `- [category]
   content` shape, so it reads like the hook's own entries.

If nothing matches, it is probably a transient working note — do not
persist it at all. Not everything deserves a surface.

## decisions.md vs learnings.md (the common confusion)

- **decisions.md** = a fork in the road you took. "Chose Postgres over
  SQLite — need concurrent writers." Has a rationale. Reviewable by the
  user at CTO check-in (this is also where `harness-unknowns-check`
  accepted-with-risk downgrades land).
- **learnings.md** = something the codebase/environment taught you the
  hard way. "Vite HMR drops the auth cookie on `:5173` — test on the
  proxied `:3000`." Has a symptom and a workaround. Non-Googleable and
  specific to THIS project (same bar as OMC's learner: would someone find
  this via a 5-minute search? if yes, don't file it).

A decision is a choice *you* made; a learning is a fact *the project*
revealed. If a single item is both (you chose X *because* the project
does Y), split it: the choice → decisions.md, the discovered constraint →
learnings.md.

## Confidence discipline (mirrors harness-unknowns-check)

- **Mark uncertain items uncertain.** If you are not sure a fact is true
  or durable, write it with an explicit hedge —
  `- [unverified] staging may rate-limit at 100 req/min (saw one 429, not
  reproduced)` — never as settled fact. A confidently-wrong memory entry
  is worse than no entry: every future session inherits the error. Same
  rule as a `## Unknowns` line: surfaceable beats invisible.

- **FLAG conflicts, do not overwrite.** If a new fact contradicts an
  existing entry on any surface, do NOT silently replace it. Append a
  conflict marker next to the existing line and surface it to the user /
  CTO for resolution:

  ```
  - [build-cmd] npm run build
  - [conflict?] saw `pnpm build` succeed this session — which is canonical? (unresolved)
  ```

  The existing entry may be the stale one or the new observation may be a
  fluke; you cannot tell from inside one session. Routing's job is to make
  the disagreement visible, not to adjudicate it. (This is the memory-side
  analog of the unknowns gotcha "don't let design.md and spec.md disagree
  about what's unknown.")

- **Never self-promote to a higher surface.** Spec learning → RULES, or
  anything → user MEMORY.md, requires explicit user/CTO sign-off. A fact
  earns promotion by recurring across specs and the user agreeing it is a
  rule. Promoting on your own authority is the same protocol violation as
  silently downgrading an unknown — the decision authority shifts from the
  user to the agent without consent.

## Promotion gate to RULES / AGENTS / CLAUDE

Before writing to a rules-tier file, ALL must hold:

- It is a **rule** (an instruction/constraint), not a fact or a one-off
  decision.
- It should apply to **every future session**, not just this feature.
- The user or CTO has **explicitly approved** elevating it (or it
  restates an instruction the user just gave as standing policy).

If any fails, file it one tier down (spec decisions.md) and note "candidate
for RULES if it recurs". Rules files are read at the start of *every*
session by *every* role — a wrong or over-specific entry there is the most
expensive memory mistake in the system.

## Output (what to report after routing)

Keep it to four lines:

1. **Filed:** what you wrote, one line each, with its surface.
2. **Skipped:** anything you judged transient and did not persist (and
   why), so the user can override.
3. **Conflicts:** any `[conflict?]` markers you raised, needing
   resolution.
4. **Promotion candidates:** anything you parked one tier down that may
   deserve a rule later.

## Relationship to the auto-accumulator

`hooks/project_memory.py` runs on every CTO tool call and is the *default*
writer of project memory — it never asks, never narrates, just folds
mechanical facts into `.claude/harness-memory.md` with a 20-note FIFO cap.
This skill is the *deliberate* path for everything the hook can't infer.
Do not duplicate the hook's job: if a build command was actually run this
session, the hook already has it — don't hand-file it too. Check the file
first (`cat .claude/harness-memory.md`) before appending, both to avoid
duplicates and to spot conflicts.
