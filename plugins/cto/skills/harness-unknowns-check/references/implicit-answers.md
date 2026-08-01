# Implicit answers — self-answer vs. relay decision tree

The opposite failure mode of the anti-pattern phrases: padding
`## Unknowns` with items the user already answered. This is the
**goal-padding** anti-pattern — listing items the goal already
answered so the spec looks thorough.

Walk this tree in order before adding any line to `## Unknowns`:

1. **Read the original goal verbatim.** Does it (or any parenthetical
   / tech-stack hint) contain the answer? → self-answer, emit a
   `<decision>` block, do NOT add to `## Unknowns`.

   *Example:* goal is `회원가입 페이지 만들어줘 (Next.js 14, Supabase)`.
   Framework and auth are settled facts. Do not list "framework?" or
   "auth provider?" under Unknowns.

2. **Does an existing repo file resolve it** (`DESIGN.md`,
   `package.json`, prior `decisions.md`)? → use the `read <file>`
   resolution path, resolve, log, do NOT add as open.

   *Example:* `DESIGN.md` at project root already names the color
   palette. Read it. Do not relay "what color scheme?"

3. **Does prior session context** (earlier user messages this
   session) resolve it? → self-answer, log, do NOT add. The lead has
   the same context — see `harness-relay-qa` gotcha #4 for the
   lead-side counterpart.

   *Example:* three messages ago the user said "use Postgres". A
   later teammate asking "which DB?" is wasting a round.

4. **Genuinely open with no resolvable source?** → add to
   `## Unknowns` with `relay to user` as the resolution path. This is
   where a real `[user-q]` round earns its keep.

## Litmus test

> Would the user be annoyed to be re-asked?

If yes, it's implicit-answered — self-answer it and emit a `<decision>`
block. Emitting it is what keeps it surfaceable at CTO check-in; padding
`## Unknowns` with it just makes the section noisy and signals you did
not read the goal.
