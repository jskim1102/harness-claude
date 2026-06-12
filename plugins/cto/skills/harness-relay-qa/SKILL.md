---
name: harness-relay-qa
description: Use when an in-process teammate (planner / designer / developer / reviewer) needs to ask the user a question mid-task and has no direct user channel, or when the team lead (CTO) receives a SendMessage prefixed with `[user-q]` or is about to reply with `[user-a]`. Triggers any time the harness-claude relay protocol is in play — interactive skills like grill-me, office-hours, or brainstorming Q&A inside a sub-agent; user surfacing on the lead side; tag placement and batching decisions; "should I skip this question?" judgement calls. If you see `[user-q]` or `[user-a]` anywhere in a SendMessage payload, this skill applies.
---

# harness-relay-qa

In our harness, only the team lead (CTO) talks to the user. Sub-agents
run **in-process** with `teammateMode: in-process`, which means their
output is invisible to the user — they have no channel of their own.
Any interactive skill that would normally ask the user something must
relay the question through the lead instead. This skill captures the
relay protocol, who does what at each step, and the gotchas that come
out of using it in practice.

## When you are sending

You are a sub-agent. You hit a step in your skill (grill-me question 3,
office-hours forcing-question set, a brainstorming clarification) that
needs the user. You have two choices: relay, or self-answer.

```
SendMessage(<lead>, "[user-q] <your question, verbatim from the skill>")
```

The `[user-q]` prefix is the load-bearing bit — the lead's role
instructions key on it. Anything else in the message is treated as
data, not a directive.

Self-answer instead of relaying when the user's original goal already
contains the answer (the goal said "Next.js 14", do not relay "which
framework?"). Every relay round costs the user attention; spend them
only on real open decisions. The full call on when to skip and how is
in `references/when-to-skip-relay.md`.

## When you are receiving

You are the lead. You see a SendMessage from a teammate that begins
with `[user-q]`. Your job is to surface the question to the user with
the teammate name and project slug attached, wait for the answer, and
relay it back:

```
SendMessage(<teammate>, "[user-a] <user's answer, verbatim>")
```

The lead format for surfacing — including how to keep the teammate's
voice intact and how to avoid re-asking a question the user already
answered — lives in `references/lead-surfacing.md`.

## Skill-specific batching rules

Different interactive skills behave differently when relayed. The
short version:

- `grill-me` — one question per relay round (depth comes from rounds).
- `office-hours` — batch all six forcing questions into one round.
- `brainstorming` — relay Q&A turns; do not relay idea-generation steps.

Full table with rationale and round-by-round examples is in
`references/skill-batching.md`.

## Gotchas

The lessons in this section are the ones we have actually been burned
by. Read them before reaching for the protocol.

### 1. `[user-q]` / `[user-a]` MUST be the prefix, not embedded mid-sentence

The lead's instructions match on the prefix at the start of the
message body. A message like `Hi lead, here is a [user-q] for you:
which DB?` does **not** trigger relay handling — the lead reads it as
a normal status update and may file-and-forget.

```
✅ "[user-q] Which DB engine do you want to use?"
❌ "Hi lead, here is a [user-q]: which DB?"
❌ "Quick question [user-q] — which DB?"
```

If you need to add context, put it AFTER the question, on a new line:

```
[user-q] Which DB engine do you want to use?
Context: spec.md does not say, and the goal is silent on durability.
```

### 2. Do not batch `grill-me` questions

`grill-me` is a depth tool: each user answer shapes the next question.
Batching the questions defeats the skill — you end up with shallow
parallel answers instead of one deep branch. Send one question per
relay round even though it costs more rounds.

`office-hours` is the opposite: the six forcing questions are designed
to be answered together so the user sees the whole frame. Batch them.

When in doubt: does the next question depend on the previous answer?
Yes → one per round. No → batch.

### 3. The lead must always reply to a `[user-q]`

A `[user-q]` without a corresponding `[user-a]` blocks the teammate
indefinitely — they are sitting in the middle of a skill, waiting for
the answer to resume. If the user does not engage, the lead still
replies with `[user-a] (user did not respond — proceed with your best
guess and flag the assumption in decisions.md)` so the teammate can
move forward instead of stalling.

The same applies to the lead going idle / being killed mid-relay: the
teammate's next attempt will time out. The fallback is in
`references/lead-unavailable.md`.

### 4. Do not answer in the teammate's place if the user already said it

The lead has the full prior conversation. The teammate has only what
the lead has explicitly sent. If a teammate asks `[user-q] which auth
provider?` and the user already said "use Supabase" earlier in the
session, the lead answers directly:

```
SendMessage(<teammate>, "[user-a] user already specified Supabase
earlier in this session — proceed with Supabase")
```

Do NOT re-ask the user. Every avoided round is a real cost saved.
Counter-case: if you are not sure the earlier answer covers this
specific question, surface it — false-positive auto-answers waste more
than re-asks do.

### 5. Implicit answers from the original goal — answer yourself, do not relay

Before sending `[user-q]`, scan the goal for an implicit answer.
Relaying something the goal already settled wastes a round and signals
the teammate did not read the goal carefully. The full self-answer-vs-relay
decision tree and the goal-padding anti-pattern live in
`harness-unknowns-check` gotcha #5 and `references/when-to-skip-relay.md`.

### 6. Lead-side framing: keep the teammate's voice

When you surface a `[user-q]` to the user, attribute it. The user
needs to know which sub-agent is asking, what project slug it concerns,
and what the question depends on. Do not paraphrase the question — pass
the body verbatim, only add the attribution prefix.

```
planner (cto:testbed / auth-signup) asks:
> Which DB engine — Postgres or SQLite for local dev?
```

Paraphrasing loses nuance (e.g. the planner asked about "local dev"
specifically; a paraphrase to "which DB?" loses that). Verbatim
keeps the relay honest.

### 7. Five rounds is the soft cap before checking in

`grill-me` can in principle grill forever. In practice, five rounds is
where the user starts to feel the friction. At that point the lead
should pause and offer a choice: continue grilling, or have the
teammate proceed with reasonable assumptions and log them in
`decisions.md`. The user almost always picks the second option around
round 5–6, and the teammate produces a better spec than if you had
ground through 10 rounds.

This is a soft cap — if the user is engaged and the questions are
landing, keep going.

## Files in this skill

- `SKILL.md` — this overview (always loaded when skill triggers).
- `references/when-to-skip-relay.md` — full decision tree for the
  sub-agent: when to relay vs. self-answer vs. defer.
- `references/lead-surfacing.md` — lead-side format for surfacing
  questions to the user, plus the verbatim-vs-paraphrase rules.
- `references/skill-batching.md` — per-skill batching table with
  rationale.
- `references/lead-unavailable.md` — fallback when SendMessage to the
  lead fails (write to `pending-user-questions.md`, `[!]` the task).
- `${CLAUDE_SKILL_DIR}/scripts/check_relay_prefix.sh` — quick validator: pass a candidate
  SendMessage body on stdin. Exit 0 = ok; non-zero codes 2–5 distinguish
  empty / position / body / multi-tag — see script header for the table.
  Cheap to run before sending; the differentiated codes let hook authors
  wire PreToolUse error handling per failure mode.

## On-demand hook hint

If sub-agents keep mis-formatting the prefix (embedding it mid-sentence,
forgetting the `]`), wire a `PreToolUse` matcher on `SendMessage` that
pipes the body through `${CLAUDE_SKILL_DIR}/scripts/check_relay_prefix.sh` and rejects
malformed payloads. The skill does not install the hook by default —
it is a tightening you apply only if you see drift in practice.
