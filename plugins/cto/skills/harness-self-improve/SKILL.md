---
name: harness-self-improve
description: Use to run a retrospective that turns accumulated, recurring session facts into promotion PROPOSALS — never auto-edits. Triggers when the user says "retro", "회고", "self-improve", "돌아보고 개선해", once per build at close-out (all segments PASS + the user's final visual check) just before TeamDelete, or when you notice the same gotcha/decision recurring across specs and want to decide whether it has earned a higher memory surface. It reads project memory + per-spec learnings/decisions, finds what recurred across >=2 surfaces, and hands each candidate to harness-remember for routing through its promotion gate. This is the recurrence DETECTOR that feeds the router — it does not write RULES/PROCESS/role/AGENTS/CLAUDE/user-MEMORY itself, and it never adjudicates conflicts.
---

# harness-self-improve

The memory system has three rungs and this skill is the middle one:

1. **`hooks/project_memory.py`** silently CAPTURES mechanical facts (build/test
   commands actually run, runtime versions, missing deps, hot paths) into
   `.claude/harness-memory.md`. It never reflects — it only accumulates.
2. **harness-self-improve** (this skill) REFLECTS: it scans what accumulated
   plus the per-spec `learnings.md`/`decisions.md`, finds the facts that
   *recurred across more than one surface*, and proposes what has earned a
   higher home. It writes nothing on its own authority.
3. **`harness-remember`** ROUTES each proposal to the right surface and, for
   anything rules-tier, enforces the promotion gate (explicit user/CTO sign-off).

harness-remember already parks items as "candidate for RULES if it recurs" —
but nothing measures recurrence across sessions and specs. That measurement is
the only job this skill exists to do. **Do not duplicate harness-remember's
routing or its gate here; produce candidates and hand them over.**

## When to run

- **빌드 마감(close-out)** — once per build, after all segments PASS + the
  user's final visual check, just before `TeamDelete`. NOT per segment — it
  runs once on the whole completed build, so a cross-segment pattern is
  visible at the point everything is done (and a build's hard-won gotchas
  are filed instead of evaporating when the team is torn down).
- **On demand** — "retro" / "회고" / when you feel a fact repeating.

It is a once-per-build reflection, not a per-tool-call hook and not per-segment.
Running it more than once per build is noise.

## What it does

1. **Scan (read-only).** Run the advisory scanner from the project root:

   ```bash
   bash ${CLAUDE_SKILL_DIR}/scripts/scan_recurrence.sh .
   ```

   It reports three buckets, deciding nothing:
   - **recurrence** — a fact appearing on >=2 surfaces (two specs, or a spec
     and the project-memory file), with its count. This is the promotion
     signal.
   - **unresolved conflicts** — `[conflict?]` markers still open.
   - **low-confidence parks** — `[unverified]` items awaiting re-test.

   The scanner is advisory and lossy (it matches normalized text, so paraphrased
   recurrences slip past it). Read the surfaces yourself for anything it can only
   half-see; it is a starting point, not the verdict.

2. **Triage each recurrence into a candidate.** For every recurring fact decide:
   - Is it a *rule* (a standing instruction/constraint) or still just a *fact*?
     Only rules are RULES/AGENTS/CLAUDE candidates — and only with the gate met.
   - Is it tied to one feature (stays in that spec) or genuinely cross-project
     (the user's call, never yours)?
   - Has it recurred enough, and consistently enough, that promoting it would
     save future sessions more than a wrong promotion would cost? Rules files are
     read by every role every session — over-promotion is the most expensive
     memory mistake. When unsure, leave it one tier down and say so.

3. **Hand candidates to harness-remember.** Invoke `harness-remember` with the
   triaged candidates. That skill owns the four surfaces, the routing tree, and
   the promotion gate. This skill's output is its input — do not re-implement its
   logic.

4. **Surface conflicts, never resolve them.** An `[conflict?]` marker means two
   observations disagree and one session cannot tell which is stale. Report it
   to the user/CEO for resolution — do not pick a winner.

## Hard boundaries (the reason this is a detector, not a writer)

- **Never auto-edit an authority surface.** `RULES.md`, `PROCESS.md`, `role.md`,
  `AGENTS.md`, `CLAUDE.md`, and the user's `MEMORY.md` are NEVER written by this
  skill. It proposes; harness-remember routes; the user/CTO approves rules-tier
  promotions. Promoting on your own authority is the same consent violation as
  silently downgrading an unknown — the decision moves from the user to the
  agent without sign-off.
- **Never run git** (RULES §1). Read-only scan only.
- **Never adjudicate a conflict.** Surface it; let a human resolve it.
- **Bound the output.** Propose the few candidates that genuinely earned it, not
  every line in memory. Refusing to dump everything is the same discipline
  harness-remember enforces on the routing side.

## Output

Report four lines, mirroring harness-remember so the two compose cleanly:

1. **Promoting:** candidates handed to harness-remember, each with its evidence
   (`Nx across <surfaces>`) and the surface you proposed.
2. **Parked:** recurrences not yet strong enough, left one tier down with the
   reason (so the next retro can reconsider).
3. **Conflicts:** open `[conflict?]` markers routed to the user.
4. **Retested/dropped:** `[unverified]` parks you confirmed or discarded.

## Relationship to the other two rungs

- It **reads** `project_memory.py`'s output; it never writes that file or alters
  the hook. The hook keeps accumulating regardless.
- It **feeds** `harness-remember`; it never bypasses the gate to write a higher
  surface directly. If you find yourself about to edit RULES.md from here, stop —
  that is harness-remember's gated path, run through it with approval.
