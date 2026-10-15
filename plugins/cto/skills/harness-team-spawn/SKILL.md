---
name: harness-team-spawn
description: Spawn the standard 2-Claude team (planner, reviewer) while external Codex (production code) and designer-cto (design) sessions own their crafts. Use on the CTO's FIRST turn whenever the start marker (~/.claude/logs/started/<name>.started, pre-seeded by add-cto) exists — spawn before answering anything else. Also use for /start-project and explicit team-spawn requests.
---

# harness-team-spawn

The CTO is a Claude lead. Its Agent Team contains exactly two Claude
teammates on a fresh build, spawned in this order (a resumed build whose
`specs/tasks.md` already exists spawns `reviewer` only — planner is
gate-blocked after decomposition, RULES §17):

```text
planner -> reviewer
```

Design is owned by the separate `harness:cto:<name>:designer` Orca tab
(independent Claude session, 2026-07-29 split) — never a teammate; reach it
with `harness send --to designer-cto:<name>`.

The production developer is the separate `codex-cto-<name>` Orca tab. It
is not a Claude teammate. Never call `Agent(subagent_type=developer)` or
`Agent(subagent_type=designer)`, never spawn a third Claude teammate, and
never spawn a second teammate of one role.

## When To Spawn

**If the start marker exists (`~/.claude/logs/started/<name>.started`), spawn
the team immediately — on your very first turn, whatever that turn is.** Do not
wait for a work instruction, do not judge whether the turn "counts", do not ask
for confirmation. `add-cto` pre-seeds the marker (2026-08-04 사용자 결정: 팀
spawn 은 CTO 실행에 포함된다), so a spawned CTO always comes up with its team.
Spawn first, then answer whatever the user actually asked.

The only turn to postpone on is an inbox-isolation turn (RULES §6 blocks all
tool use that turn) — spawn on the next turn instead. The
`start_project_spawn_nudge` Stop hook enforces roster completion either way.

**After the marker was consumed** (roster completed earlier — e.g. a resumed
session whose teammates died, or the reviewer is needed again): **never tell
the user to type `/start-project`** (2026-10-06 사용자 지시). Say in one line
why the teammate is needed, end with `reviewer 스폰할까요?` (fresh build:
`planner·reviewer 스폰할까요?`) and end the turn. Ask it on its own — don't
bundle other approvals (alembic, commit …) into the same message, or a bare
"응" becomes ambiguous. When the user approves (응/네/해 …),
`start_project_gate` records the start signal from that reply; spawn on that
turn and **continue the work that needed the teammate** (e.g. dispatch the
review) — an approval turn is not spawn-only. `/start-project` typed by the
user still works as a manual re-signal (that turn stays spawn-only).

## Mandatory Preflight

Before any Claude teammate spawn, derive `<name>` from `HARNESS_ROLE=cto:<name>`
and check the existing Codex session:

```bash
harness roles
```

Missing session means stop and tell the user to run `./run.sh add-cto <name>`.
Do not start or restart Codex from the slash command or this skill.

## Team Name

Claude team state lives under the global `~/.claude/teams/<team>/` path. **You do
not choose the name.** The runtime names the team `session-<8 hex of
leadSessionId>` and discards any name this skill proposes — so there is nothing
to derive and collisions are structurally impossible (one team per lead session).

Config schema is `name` / `createdAt` / `leadAgentId` / `leadSessionId` /
`members`. There is no owner field: a team cannot be matched back to a CTO name,
only to the session that created it. Never delete a team you did not create.

## Standard Spawn

Use `references/spawn-prompt.md` verbatim. Its load-bearing invariants are:

- exactly `planner`, `reviewer` on a fresh build; `reviewer` only when
  `specs/tasks.md` already exists (`planner_dispatch_gate` blocks planner after
  decomposition — same rule as `start_project_spawn_nudge`)
- `teammateMode in-process` in a plain `claude` lead session (no
  `orca claude-teams` wrapper — it force-opens native splits, 2026-07-29).
  The lead tab is the cockpit rail: lead left, right rail = skill activity +
  read-only planner/reviewer transcript viewers (designer has its own tab).
- spawn-only boot; no plan approval or work dispatch during `/start-project`
- no Claude developer
- no teammate SendMessage until the CTO explicitly dispatches work later

The only pre-spawn check is whether `specs/tasks.md` exists (decides planner
or not). Any other fresh/maintenance handling happens only after a later CTO
dispatch.

## Layout Check

After spawn, the Claude session's current window must contain:

```text
lead CTO + skill activity; teammates are selected in-process from the lead view
```

The Codex developer is one pane in a different Orca tab. A `developer` teammate
inside the Claude session is a configuration error.

## After Spawn

There is no fresh/maintenance branch during `/start-project`. Do not inspect
`plan.md`, `spec.md`, or `tasks.md`, and do not create decomposition or fix
tasks. The CTO owns the next explicit dispatch and decides which teammate, if
any, should work.

## Parallelism

Each Claude role may fan out independent, role-local work through Task
subagents. Subagents create no panes. Do not use parallelism to bypass role
ownership: production source is written only by Codex, and same-file writers
must be serialized.

## Codex Handoff

After the user approves a segment, the CTO sends a concise structured `[dev]`
scope through `harness send` to `codex-cto:<same-name>`. The Codex daemon wake
reads that inbox; `RULES.md` §6 still requires summary-only in that turn and
explicit user authorization in the next Codex turn. Completion evidence and
blockers return through the same pair-only bridge. Never claim that
`SendMessage(developer)` worked; no such Claude teammate exists.

## Files

- `references/spawn-prompt.md`: verbatim two-Claude spawn prompt
- `references/plan-approval-default.md`: teammate plan approval policy
