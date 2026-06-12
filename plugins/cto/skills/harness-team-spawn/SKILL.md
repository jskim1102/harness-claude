---
name: harness-team-spawn
description: Use when spawning the standard 4-teammate Agent Team (planner / designer / developer / reviewer) for a new project or feature in the harness-claude harness. Triggers on `/start-project` slash command; natural-language phrases like "팀 만들어", "팀 spawn", "agent team 띄워", "create a team", "build me X with agents", "팀 4명 만들어"; any time the CTO is about to call `TeamCreate`; or when `~/.claude/teams/<name>/` already exists and the CTO must decide resume-vs-delete-vs-rename.
---

# harness-team-spawn

In our harness, the CTO does not write code. The CTO spawns a team of
four in-process teammates (planner / designer / developer / reviewer)
through Claude Code Agent Teams and delegates everything. This skill
captures the standard spawn pattern, the team-name rules that prevent
cross-CTO collisions at the global `~/.claude/teams/<name>/` path, the
existing-team disambiguation flow, and the gotchas that come out of
running this in practice with multiple CTOs sharing one machine.

## When to spawn

Spawn only on an **explicit signal**. Three paths trigger it:

0. **add-cto auto-kickoff** — `run.sh add-cto` 가 스폰 직후 CTO 세션에
   `/start-project ...` 를 자동 타이핑한다. 이것은 사용자가 add-cto 를
   실행한 데서 위임된 **허용된 spawn 신호**다 — 추가 확인 없이 진행.

1. **Slash command** — `/start-project <goal>` (preferred). The command
   body is the canonical spawn prompt and handles team naming, plan
   approval mode, and the first SendMessage to the planner.

2. **Natural language** — phrases like "팀 만들어 / 팀 spawn / agent
   team 띄워 / create a team / build me X with agents". Extract the
   goal verbatim, confirm with a one-line check to the user (`Spawn
   team <name>? Goal: <extracted goal>`), then fire the same standard
   spawn prompt on user OK.

If the user just says "회원가입 페이지 만들어줘" with no team signal,
**do not auto-spawn**. Surface a one-line suggestion to use
`/start-project` instead. The reasoning and the full anti-pattern is
in gotcha #6.

## Team name derivation (critical)

Team configs live at `~/.claude/teams/<name>/` — a **global path
shared across every CTO on this machine**, so the team name must
encode the owner CTO as `<cto-name>-<slug>`. Run
`${CLAUDE_SKILL_DIR}/scripts/derive_team_name.sh <slug>` to compute it; full rules and
fallback chain in `references/team-naming.md`.

## Existing-team handling

If `TeamCreate` returns "team already exists", inspect
`~/.claude/teams/<name>/config.json` before reacting — the right
action (resume / delete-and-respawn / rename with hash) depends on
who owns it. The three-sub-case decision tree is in
`references/existing-team.md`.

## Standard spawn prompt

The literal prompt body is in `references/spawn-prompt.md`. Do not
paraphrase it — the planner, designer, developer, and reviewer agents
are tuned to specific phrasings (the skills loops named there map
exactly to their `.claude/agents/*.md` definitions).

Two non-obvious requirements baked into the prompt:

- **Plan approval mode is default ON** for every teammate, not just
  for destructive tasks. See gotcha #5.
- The first SendMessage goes to **planner only** — designer,
  developer, reviewer are spawned but idle until handoffs.

## Gotchas

The lessons in this section are the ones we have actually been burned
by on this harness. Read them before reaching for `TeamCreate`.

### 1. Generic team names collide between CTOs

`~/.claude/teams/<name>/` is a global path. CTO A and CTO B both
running on the same machine will compete for the slot if either picks
`auto-team`, `team`, `dev-team`, `agents`, or any other generic noun.
The first one wins; the second gets "team already exists" and — if it
follows the existing-team flow incorrectly — may `TeamDelete` the
other CTO's live work.

The fix is the `<cto-name>-<slug>` convention. `testbed-auth-signup`
and `harness-claude-auth-signup` never collide even when both CTOs are
building "auth signup" at the same moment. Run
`${CLAUDE_SKILL_DIR}/scripts/derive_team_name.sh <slug>` to enforce this — it pulls
`HARNESS_ROLE` itself and refuses to emit a generic name.

### 2. `HARNESS_ROLE` carries a `cto:` prefix — strip it

The env var is `cto:testbed`, not `testbed`. If you forget to strip
the prefix you end up with team names like `cto:testbed-auth-signup`,
which Claude Code's Agent Teams rejects (the `:` is illegal in team
names). The derivation script strips it for you; if you ever hand-roll
a name, do the same.

```
HARNESS_ROLE="cto:testbed"
cto_name="${HARNESS_ROLE#cto:}"   # → "testbed"
```

### 3. Missing `HARNESS_ROLE` — never fall back to generic

If `HARNESS_ROLE` is unset or empty (test environment, sub-shell that
did not inherit it, etc.), the temptation is to default to `auto-team`
or `default`. **Do not.** That immediately re-introduces the
collision in gotcha #1 the moment a real CTO runs alongside you.

The correct fallback is `<slug>-<8char-hash>` — hash the slug + the
process PID + the wall clock so two simultaneous fallbacks on the
same slug still produce different names. The derivation script does
this when `HARNESS_ROLE` is missing.

### 4. Existing-team handling — never delete another CTO's team

"team already exists" is the most dangerous response from
`TeamCreate`, because the wrong reaction (blanket `TeamDelete` +
retry) can wipe another CTO's in-flight planner / developer.

The right reaction depends on **who owns the existing team**. Check
`~/.claude/teams/<name>/config.json` first to see the owner CTO. If
it is yours and orphaned, delete. If it is yours and active, resume.
If it is someone else's, your collision detection failed — regenerate
your name with a hash suffix and respawn under the new name. Full
sub-case tree (with config.json field names) in
`references/existing-team.md`.

### 5. Plan-approval mode is ON by default, not just for destructive work

The standard spawn prompt requires every teammate to write its plan
first and wait for your approval before executing. This is broader
than the usual "plan approval for destructive operations" pattern —
even the planner's first spec draft goes through approval.

Reason: in this harness the CTO is the only quality gate before the
user sees output. If the planner silently picks the wrong framework,
or the developer silently expands scope, the cost surfaces three
hours later as a failed visual review. Plan approval up-front catches
those at the cheapest moment. The flip side is round-trips — but the
SendMessage round-trip is cheap; rework is not.

If you find yourself rubber-stamping every plan, that is a signal the
teammates are well-calibrated, not a signal to disable the gate.

### 6. Auto-spawning without an explicit signal is forbidden

A user request that "obviously needs a team" — "회원가입 페이지
만들어줘" — still does not trigger spawn on its own. The user might
want the team route, or might want you to scope it down, or might be
exploring before committing. Spawning without asking burns four
agents, claims a global `~/.claude/teams/<name>/` slot, and starts a
spec the user may abandon.

The correct response to an implicit request is a one-line nudge:

```
이 요청은 4-teammate 팀으로 진행하면 좋을 것 같습니다.
`/start-project 회원가입 페이지` 로 시작할까요?
```

The bar for auto-spawn: the user used one of the trigger phrases
(`/start-project`, "팀 spawn", "agent team 띄워", "create a team",
"build me X with agents", "팀 4명 만들어"). Anything else gets the
nudge.

### 7. Natural-language trigger — why verbatim + confirm are non-negotiable

Paraphrasing at extraction time loses framing the planner later
re-derives. Example: "signup page, keep it simple, ship in a day"
paraphrased to "signup page" — the planner now optimizes for
completeness, not the 1-day constraint that was the real scope
signal, and you only catch it once cycle 2 of the build is running.
The confirmation prompt is the user's one redirect chance before
four agents start work. The mechanic is in the "When to spawn"
section above — this gotcha is about why both halves are
non-negotiable.

## Files in this skill

- `SKILL.md` — this overview (always loaded when skill triggers).
- `references/team-naming.md` — full team-name derivation rules, slug
  conventions, and the `HARNESS_ROLE` fallback chain.
- `references/existing-team.md` — three-sub-case decision tree for
  the "team already exists" response, with `config.json` field
  references.
- `references/spawn-prompt.md` — the verbatim standard spawn prompt
  body, with annotations on which lines are load-bearing.
- `references/plan-approval-default.md` — why plan approval is on by
  default for every teammate (not just destructive tasks), and how to
  approve / reject plans efficiently.
- `${CLAUDE_SKILL_DIR}/scripts/derive_team_name.sh` — deterministic team-name derivation.
  Reads `HARNESS_ROLE` from env and the slug from argv; emits the
  computed name; falls back to `<slug>-<8char-hash>` when
  `HARNESS_ROLE` is missing; exits non-zero with a specific reason on
  stderr — see script header for the full exit-code table.

## On-demand hook hint

If team-name collisions keep happening in your environment (multiple
CTOs on one box, fast slug churn), wire a `PreToolUse` matcher on
`TeamCreate` that pipes the requested team name through
`${CLAUDE_SKILL_DIR}/scripts/derive_team_name.sh --validate` and rejects names that do
not match the `<cto-name>-<slug>` convention. The skill does not
install the hook by default — apply it only if you see drift in
practice.
