# Resolution gates by role

Each role has a specific point at which open unknowns become
disqualifying. The gates exist because unknowns left open at a phase
boundary become assumptions the next phase silently inherits — and
silent inheritance is what produces wrong builds.

## Planner gate: cannot author `tasks.md` while `spec.md` has open unknowns

`tasks.md` is the contract between the planner and the build phase.
Every task references files, acceptance criteria, and verification
commands derived from `spec.md`. If `spec.md` still says
`- [ ] auth provider — relay to user`, the planner cannot write a
`[dev] implement /api/auth/signup` task — that task would inherit the
"auth provider" unknown into code.

The planner has three legal moves:

1. **Resolve the unknown.** Read the file, ask the teammate, send the
   relay round. Tick the checkbox.
2. **Downgrade to accepted-with-risk.** Emit a one-line rationale as a
   `<decision>` block for the CTO to file in `decisions.md`, and remove
   the line from `## Unknowns`. The unknown is closed; the risk lands
   where the user will see it.
3. **`[❓]` the spec authoring task.** If the unknown cannot be
   resolved or downgraded right now, mark the planner's own task as
   blocked and surface to the CTO. Do NOT proceed to `tasks.md`.

The forbidden move is to write `tasks.md` anyway with the unknown
still open and "we'll figure it out in build." That is exactly the
failure mode this whole skill exists to prevent.

## Designer gate: cannot hand off `design.md` with open visual/interaction unknowns

The designer's gate is narrower than the planner's — they're not
blocked by every spec unknown, only the ones in their domain (visual
language, interaction model, layout, motion, copy voice).

```markdown
## Unknowns
- [ ] should the signup form be one-step or two-step? — relay to user
- [ ] color palette — design-shotgun to produce variants
```

A two-step vs one-step signup form is a visual / interaction
question. The designer cannot hand off `design.md` to the developer
without resolving it (relay or shotgun).

Backend unknowns ("which auth provider?") still appear in `spec.md`
but the designer's hand-off is not blocked by them — that's the
planner's gate.

The exception is when a backend unknown has visual consequences. If
"auth provider" turns out to be "magic link" vs "password", the
signup form changes. The designer must flag this dependency in
`design.md`'s own `## Unknowns` (`- [ ] signup form depends on auth
provider — depends on spec.md unknown`) and wait for the planner to
resolve it.

## Developer gate: cannot claim a `[dev]` task with open acceptance unknowns

The developer's gate is at task-claim time, not at end-of-phase.
Before `TaskUpdate(owner=<self>, status=in_progress)`, the developer
reads the task and its referenced spec sections. If acceptance
criteria contain language like "should look polished" or "use the
appropriate library", that is an unknown leaking into the task — the
planner did not actually specify what success means.

The legal move: `[❓]` the task with a specific blocker:

```markdown
- [❓] [dev] implement /api/auth/signup | src/api/auth.ts | passes
      smoke test. Run: npm test -- auth
      > BLOCKED: acceptance says "use appropriate auth library" —
      > spec.md does not specify which. Need clarification from planner.
```

`SendMessage` the planner. Do NOT silently pick "the appropriate
library" — the planner has to either resolve and update the task or
downgrade and document.

## Reviewer gate: any open unknown at verdict time = FAIL

This is the strictest gate. The reviewer's job is to produce a verdict
(PASS / FAIL) on a build group; that verdict travels as a report message,
not a file (`reviewer.md`: `disallowedTools: Write, Edit` — "You WRITE
nothing"). If the reviewer still holds an open unknown when the verdict
is due, it cannot honestly say PASS — something it reviewed had an
undetermined property.

```markdown
## Unknowns
- [ ] does the /signup endpoint return 201 or 200? — run `curl ...`
```

If this is open at verdict time, FAIL. The reviewer can't sign off on
status code behavior they didn't observe.

Why this gate is the strictest: the reviewer is the last guard before
the build is considered done. Any unknown they pass through becomes
a fact-by-omission in the project history. "We shipped it, review
passed, so it works" — except review passed with an open unknown
that nobody resolved.

The legal moves for the reviewer:

1. **Resolve before verdict** (preferred). Run the command, read the
   file, ask the teammate. Most reviewer unknowns are `run`-shaped
   and cheap to close.
2. **Verdict = FAIL** with the unknown listed as a finding. The
   developer fixes it, the reviewer re-runs.
3. **Escalate to CTO** if the unknown is structural — the planner
   or designer left something open that should have been closed in
   their phase. The reviewer's verdict is FAIL with a note that the
   root cause is upstream.

The reviewer never downgrades an unknown to accepted-with-risk. That
power belongs to the planner. The
reviewer's job is to surface, not to absolve.

## Why role-specific gates instead of one global gate

A single "no unknowns at all, ever, anywhere" rule would be cheaper
to enforce but would prevent honest in-phase work. The designer
needs to write down a `design.md` with the backend unknowns flagged
in `## Unknowns` — that's exactly what the section is for. They're
not in violation just because something elsewhere is unresolved.

The role-specific gates encode the actual phase boundaries: who
hands what to whom, and at which point unresolved facts become
dangerous to pass through.

## Cross-cutting: when a teammate notices another team's unknown leaking

If the developer notices `spec.md` has an unresolved unknown that
affects their task, the developer does NOT resolve it themselves
(scope leak). They `[❓]` and message the planner. Same for designer
noticing a planner unknown — flag, don't resolve.

The corollary: each role's gate is theirs to defend, not someone
else's to silently patch. Patching across role boundaries hides the
fact that an earlier phase shipped with an open unknown.
