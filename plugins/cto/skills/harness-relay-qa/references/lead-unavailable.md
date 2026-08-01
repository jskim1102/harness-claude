# When the lead is unavailable

Three scenarios where the teammate's `[user-q]` cannot land:

1. The lead's CTO session was killed mid-build.
2. `SendMessage(lead, ...)` returned an error (lead inbox full, transport
   failure, etc.).
3. The lead acknowledged but never returned with `[user-a]` (lead
   crashed or got distracted by another teammate).

In all three cases, the teammate is blocked in the middle of an
interactive skill. The protocol is:

## Step 1: Write the pending question to the spec dir

```bash
slug="<your current spec slug>"
mkdir -p "specs"
cat >> "specs/pending-user-questions.md" <<EOF

## $(date -u +%Y-%m-%dT%H:%M:%SZ) — <your teammate name>

<verbatim question body, as you would have sent in [user-q]>

Context: <step that needed this answer, e.g. "gate-2 design loop round 3">
EOF
```

This file is the durable record of unresolved relay attempts. It
survives session restarts.

## Step 2: Mark the blocked task

```bash
# In tasks.md, edit the relevant task line:
- [❓] [plan] write spec.md | specs/spec.md | spec passes plan-eng-review. Run: ...
  > BLOCKED: waiting on user answer in pending-user-questions.md (Open Question 3)
```

The `[❓]` mark is recognized by the harness as a blocked state. The
CTO sees it on next check-in.

## Step 3: Notify the CTO when it comes back

**There is no boot-time auto-pickup.** The lead's spawn sequence is
spawn-then-wait (role.md 부팅 시퀀스 step 4) — it deliberately reads no
spec files, so nothing scans `pending-user-questions.md` for you. Step 2's
`[❓]` is the live channel: the statusline surfaces it and `/goal` halts on
it (PROCESS §3), which is what actually gets the lead's attention.

So **re-ping the lead yourself** once it is back — a fresh `[user-q]`
pointing at the pending-questions entry. The lead then surfaces it to the
user the same way it would have surfaced a live `[user-q]`, and relays the
answer back to the (now blocked) teammate.

If the teammate already exited / restarted, the user's answer goes
into `decisions.md` so the next teammate to touch that spec sees the
resolution.

## What NOT to do when the lead is unavailable

- **Do not self-answer with a guess** for sticky decisions (framework,
  auth provider, primary language). Block and wait — guessing here
  is worse than waiting.
- **Do not retry the SendMessage in a loop**. One attempt, then
  fallback. Tight retry loops fill the inbox and make the user's
  next check-in noisier.
- **Do not silently complete the task with the unknown unresolved.**
  The Unknowns Stay Unknown protocol applies — log it, mark `[❓]`,
  surface it.

## Soft-failure variant: lead unresponsive after acknowledgement

Sometimes the lead acknowledges `[user-q]` but does not relay
`[user-a]` back. This is harder to detect from the teammate side.
The defensible move: if more than 10 minutes pass without
`[user-a]`, fall through to Step 1 / 2 above and proceed as if the
relay had failed.

10 minutes is a heuristic, not a hard rule. If the user is in the
middle of a long unrelated conversation with the lead, give them
longer.
