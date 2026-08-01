# Lead-side surfacing format

You are the team lead (CTO). A teammate sent you a SendMessage that
begins with `[user-q]`. This file is how you surface that question to
the user.

## Standard surfacing format

Pass the question body verbatim. Add attribution above it as a header
line. Use the project slug and the CTO name from `HARNESS_ROLE`.

```
<teammate> (<cto-name> / <slug>) asks:
> <question body verbatim, including any context lines below it>
```

Example:

```
planner (testbed / auth-signup) asks:
> Which DB engine — Postgres or SQLite for local dev?
> Context: spec.md does not say, and the goal is silent on durability.
```

Why verbatim: the planner phrased the question in a specific way. If
you paraphrase to "which DB?" you strip the context. The user's answer
to "which DB" is different from the answer to "Postgres or SQLite for
local dev" — the latter constrains the choice, the former invites
"MongoDB" answers the planner cannot use.

## Batched questions

An independent set (`plan.md` Open Questions, a `design-consultation`
questionnaire) arrives as one message. Pass it through as a numbered
list, attribution at the top.

```
planner (testbed / auth-signup) asks (plan.md Open Questions):

1. Session store — Redis or DB-backed?
2. Email delivery — transactional provider or SMTP relay?
3. Rate limiting — per-IP, per-account, or both?
4. Password reset — link expiry window?

Answer in order, or all at once — the planner can parse either.
```

## Relaying the answer back

When the user replies, send the body verbatim to the teammate:

```
SendMessage(<teammate>, "[user-a] <user's answer verbatim>")
```

If the user answered a numbered set in a single block, relay the whole
block — do not split. The teammate parses by number.

## When the user does not answer

If the user does not reply in a reasonable window (you decide the
window — typically when they move on to a different topic), the
teammate is blocked. Two options:

1. **Prompt them once.** "planner is still waiting on the DB question —
   want me to ask it to default to Postgres and proceed?"
2. **Send a soft fallback** to the teammate so they can move on:

```
SendMessage(<teammate>, "[user-a] (user did not respond — pick the
choice you think is right and emit the assumption as a <decision>
block so they can revisit later)")
```

This unblocks the teammate. The decision is logged where the user
will see it on their next check-in.

## When the user has already answered earlier in this session

Do not re-ask. Reply directly with the answer:

```
SendMessage(<teammate>, "[user-a] user already specified <X> earlier
in this session — proceed with <X>")
```

You have access to the full conversation; the teammate does not.
Using your context to short-circuit a relay round is one of the
biggest wins of the protocol. Be careful that the earlier answer
really does cover the specific question — if you guess wrong, the
teammate locks in the wrong decision.

When uncertain, surface the relay with a note:

```
planner (testbed / auth-signup) asks:
> Which DB engine — Postgres or SQLite?

(I think you already said Supabase, which uses Postgres, but the
planner is asking about *local dev* specifically — should we still
use Postgres locally?)
```

## Five-round soft cap

After five rounds of grilling on the same skill, pause and check in:

```
planner has gone five rounds with you on this spec. Want to keep
going, or should they lock the remaining unknowns to reasonable
defaults and proceed?
```

The user almost always picks the second option. Forcing the question
prevents the planner from burning rounds the user has already
mentally checked out of.
