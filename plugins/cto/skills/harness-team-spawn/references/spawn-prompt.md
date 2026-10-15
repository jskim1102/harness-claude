# Standard spawn prompt

This is the verbatim body used by `/start-project`. It creates exactly two
Claude teammates on a fresh build (`reviewer` only when `specs/tasks.md`
already exists — see the RESUMED-BUILD RULE inside). The production developer is the separate Codex session and
the designer is the separate designer-cto session (2026-07-29 split) — neither
is ever created with the Claude `Agent` tool.

## The prompt

```text
Create an agent team with teammateMode in-process and
EXACTLY 2 Claude teammates using Opus: planner and reviewer, spawned in that
order. Load each by its agent type name from .claude/agents/. RESUMED-BUILD
RULE: if specs/tasks.md already exists (decomposition is done),
spawn ONLY reviewer — planner is one-shot (RULES §17) and Agent(planner) is
blocked by planner_dispatch_gate; the roster is then reviewer alone. NEVER spawn a
Claude developer, a Claude designer, a third teammate, or a second teammate of
any role. The external Orca tab harness:cto:<cto-name>:codex is the sole
production-code developer and harness:cto:<cto-name>:designer is the sole
designer — both are independent sessions reached only through the harness
inbox (`harness send`), and neither is a Claude Agent Team member.

Keep teammateMode in-process; the Orca tab keeps its fixed cockpit rail (CTO
left; skill activity plus read-only planner/reviewer transcript viewers on
the right) and no native teammate splits are ever opened.
Each Claude role may fan out read-only or role-local, file-disjoint work
through its own Task subagents; do not add same-role teammates for
parallelism.

This is a spawn-only turn. Do not read, validate, generate, or modify plan.md,
spec.md, tasks.md, phases, ckpts, or segments. Do not request segment approval.
After booting, each teammate waits for a later explicit dispatch from the CTO.

Name the teammates exactly planner and reviewer. Tell each teammate the two
names and that they can message each other by name with SendMessage; a dormant
teammate wakes when it receives a message.

Role prompts:
- planner (fresh build only): boot, report that you are ready, then wait. Do not
  read or write specs. You own the acceptance criteria; you do NOT rule on
  reviewer findings — 계획 정합성 판정 is the CTO's (PROCESS §5.2).
- reviewer: boot, report that you are ready, then wait. Do not run verification yet.
  Later dispatch runs code-review, qa-only, API tests and DB integrity checks
  against the ckpt's acceptance criteria. Report the verdict to the CTO through
  SendMessage; send 계획 정합성 판정 requests to the CTO (team-lead), never to
  planner. Do not modify production files.

Apply agent-team-protocol rules to both Claude teammates. After both are live,
send no work, decomposition, orientation, or verification message to any
teammate. Return control to the CTO; later explicit CTO dispatch is the only
way a teammate begins work.
```

## Bridge note (not part of the verbatim prompt)

The prompt spawns Claude teammates only. Production dispatch flows through the
paired `cto:<name> → codex-cto:<same-name>` inbox and design dispatch through
the paired `designer-cto:<same-name>` inbox. The bridge transports context
only — `RULES §6` still forbids acting on an inbox body in the turn that reads
it, and the user authorizes the segment in the next turn of the receiving
session.
