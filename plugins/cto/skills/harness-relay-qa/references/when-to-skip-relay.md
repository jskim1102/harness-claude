# When to skip relay (sub-agent side)

Every relay round costs the user attention. Spend them on real open
decisions, not on questions the goal or the spec already answers.

## Decision tree

Before sending `[user-q]`, walk this in order:

1. **Is the answer in the original goal?**
   The CTO's first SendMessage to you contains the user's goal verbatim.
   Re-read it. "Build a Next.js 14 + Supabase signup page" already
   answers framework, auth provider, and probably theme.
   → Yes: answer yourself and emit the resolution as a `<decision>` block.

2. **Is the answer in `spec.md` or `design.md`?**
   These files are explicitly the project's source of truth. If you
   are about to ask about something a previous teammate already
   decided, you have not read the file carefully enough.
   → Yes: re-read, then proceed.

3. **Is the answer in a file you can read yourself?**
   `package.json`, existing config, the project's `DESIGN.md` at root.
   If you can resolve the unknown by reading instead of asking, read.
   → Yes: read the file.

4. **Can the answer be a sensible default that you flag?**
   "Defaulting to SQLite for local dev; revisit if the spec calls for
   Postgres later" is often acceptable. Emit it as a `<decision>` block
   and proceed.
   → Yes if low-cost to change later; no if the choice is sticky
   (auth provider, primary language, framework).

5. **None of the above?**
   Relay the question.

## What counts as "already answered"

A specific phrase in the goal counts. A vague gesture does not.

- "Use Next.js 14" → answers framework ✅
- "Make it modern" → does not answer typography ❌
- "Add signup with Supabase" → answers auth provider ✅
- "Add auth" → does not answer auth provider ❌

When in doubt, err toward asking the first time you encounter a
sticky decision, but answer yourself on cosmetic / late-reversible
ones.

## Logging self-answers

`decisions.md` is CTO-owned — you have no write access to it
(`agent-team-protocol.md` "Tagged Memory Blocks"). Emit each self-answer
as a one-line `<decision>` block **inline in your completion
`SendMessage`**, and the CTO files it for you:

```
<decision>DB: Postgres — implied by goal ("scale to 1k DAU"); SQLite would fail the durability ask</decision>
<decision>Theme: dark — DESIGN.md at project root already specified</decision>
<decision>Email service: Resend — defaulted; reversible, low cost to swap</decision>
```

One fact per tag, single line, with the *why*. No tag → nothing is filed.
The lead reads the filed `decisions.md` when reporting to the user, so a
wrong self-answer gets caught there instead of after the build.

## Anti-pattern: defensive relaying

It is tempting to relay every borderline question to be "safe". This
is a mistake — the user reads each relay as the team needing
direction, and burnt-out users stop engaging. A spec built from 20
clarifying rounds is worse than one built from 5 rounds plus 15
logged defaults.

## Anti-pattern: relaying preference questions

"Do you want this button blue or red?" almost never belongs in
relay. Use `design-shotgun` to produce variants and surface those
to the user — they pick visually, not via a Q&A round. Relay is for
decisions with text answers (framework, provider, scope).
