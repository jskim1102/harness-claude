# Skill-specific batching rules

Different interactive skills are designed around different rhythms.
Batching matters because the cost of a relay round is paid by the
user, not by the teammate.

## Per-skill table

| Source of the question | Batching                 | Why                                     |
| :--------------------- | :----------------------- | :-------------------------------------- |
| `plan.md` Open Questions | Batch the independent ones | The CEO left them as a set            |
| Contingent follow-ups  | 1 question per round      | Each answer shapes the next question    |
| `design-consultation`  | Batched questionnaire     | Designed as a single frame              |
| `plan-eng-review`      | Reviewer findings only    | Most of the skill is internal grading   |
| `design-shotgun`       | Variants, not questions   | Surface mockups, not text Q&A           |

**Not on this table on purpose:** `office-hours`, `brainstorming`,
`grill-me`. Intent exploration is done before the CTO exists — the CEO
ran that loop with the user and `plan.md` is the result. Teammates do not
re-run them (`planner.md` "No Stage-1 Rituals"); the planner relays
`plan.md` `## 6 Open Questions` instead.

## `plan.md` Open Questions — batch the frame

These are the questions the CEO deliberately left open. They are
independent of each other by construction, so send them as one round and
let the user answer them in relation to each other. Splitting them across
rounds loses the frame and feels like an interrogation.

```
[user-q] plan.md leaves three decisions open:
1. Session store — Redis or DB-backed?
2. Email delivery — transactional provider or SMTP relay?
3. Rate limiting — per-IP, per-account, or both?
```

## Contingent follow-ups — never batch

Once an answer opens a branch, the next question depends on it. Batching
kills the dynamism — you get shallow parallel branches instead of one
deep one. This is the gate-2 design loop's normal shape:

```
Round 1:
[user-q] Variant B is picked. Should the card grid stay 3-up on tablet, or drop to 2-up?
[user-a] 2-up on tablet.

Round 2:
[user-q] At 2-up the card copy overflows at the current type scale — shrink the body text or truncate with a "more" link?
[user-a] Truncate.

Round 3:
[user-q] Truncate at a fixed line count, or at a character budget?
...
```

Each question is contingent on the previous answer. Batching would
produce questions that miss the contingencies.

## `design-consultation` — frame tool, always batch

`design-consultation` gathers direction (aesthetic, density, tone,
reference systems) as a questionnaire. The answers are read against each
other, so surface the whole set in one round rather than drip-feeding it.

## `plan-eng-review` and `design-review`

These are mostly internal — the reviewer skill grades the spec / design
against criteria and produces a report. The user only sees the
relay if the review surfaces an ambiguity the spec author cannot
resolve.

## `design-shotgun`

This is the canonical "do not relay text" case. Instead of asking
"do you want the dashboard cards taller?", `design-shotgun` produces
multiple visual variants and the user picks one. Use the relay
protocol only to confirm which variant was picked, not to gather
preferences as text.

## General rule for new skills

When deciding whether to batch a new interactive skill:

- If the next question depends on the previous answer → one per round.
- If the questions are independent and the user benefits from seeing
  the frame → batch.
- If the skill could produce visual variants instead → use shotgun,
  not text Q&A.
