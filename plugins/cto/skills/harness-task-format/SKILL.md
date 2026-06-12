---
name: harness-task-format
description: Use when about to write `tasks.md` under `specs/`, about to call `TaskCreate` / `TaskUpdate` with a new subject line, when the `TaskCreated` hook has just rolled back a task creation and you need to diagnose the format violation, when the planner is finalizing `tasks.md` before handoff to designer or developer, or when reviewer FAIL output is being converted into a fresh group of `[dev]` fix tasks. Any time a line of the shape `[role] verb what | files | acceptance. Run: cmd` is being authored — or any time a teammate is staring at a "Task #N rejected by format check" message — this skill applies.
---

# harness-task-format

Every task in `tasks.md` flows through a `TaskCreated` hook that rolls
back creations whose subject + description does not match a specific
shape. The hook is fail-open on internal errors, but it is strict on
format. This skill is the field manual for that format: the shape, the
two bypass tokens, the consequences of getting it wrong, and the
pre-flight script.

## The shape

```
[role] <verb> <what> | <file paths> | <acceptance>. Run: <command>
```

Three things the hook checks:

1. A `[role]` tag where role is one of `plan`, `design`, `dev`, `review`
   (lowercase — the regex is case-insensitive at the hook layer but the
   convention is lowercase everywhere else in the protocol).
2. At least two pipe characters (`|`) in the combined subject + description.
   This is how `<files>` and `<acceptance>` are separated.
3. A `Run:` token followed by at least one non-whitespace character —
   the verification command a teammate will execute before marking the
   task complete.

If any of the three is missing, the hook responds with
`Task #N rejected by format check. Missing: ...` and the creation is
undone. You then re-author and try again. See
`references/format-anatomy.md` for the slot-by-slot breakdown and
worked examples.

## Two bypass tokens

- `[skip-format-check]` — exempts the task from the shape check. Use
  for coordination / research tasks that genuinely have no `Run:`
  command (env setup, "read these docs and report back").
- `[skip-verify]` — exempts the task from the verification-sentinel
  check at completion time. Use for docs-only tasks where there is
  nothing runnable. Prefer a real `Run:` whenever possible — even
  `ls some/dir` or `--dry-run` is better than skipping.

The two tokens are different gates (creation vs. completion) and are
not interchangeable. Details in `references/bypass-tokens.md`.

## Pre-flight validation

`${CLAUDE_SKILL_DIR}/scripts/validate_task_line.sh` mirrors the hook
regex. Pipe a candidate task line through it before calling
`TaskCreate`:

```bash
echo "[dev] add JWT verifier | src/auth/jwt.ts | tests pass. Run: npm test" \
  | ${CLAUDE_SKILL_DIR}/scripts/validate_task_line.sh
```

Exit 0 = the hook will accept it. Non-zero = specific reason on stderr.
Cheaper than authoring a malformed task, watching it get rolled back,
and recreating.

## Gotchas

The lessons in this section are the ones we have actually been burned
by. Read them before authoring `tasks.md`.

### 1. Drop the second pipe and the hook rolls you back, even when acceptance is one word

Dropping the second pipe is the most common rollback we hit. The hook
counts `|` characters and rolls back at < 2, even if the acceptance
criterion is one obvious word.

```
❌ [dev] add JWT verifier | src/auth/jwt.ts. Run: npm test
✅ [dev] add JWT verifier | src/auth/jwt.ts | unit tests pass. Run: npm test
```

Even a one-word acceptance ("tests pass", "exits 0") satisfies the slot.

### 2. Role must be lowercase: `plan` / `design` / `dev` / `review`

The hook regex is technically case-insensitive, but every other piece
of the protocol — task ownership, `TeammateIdle` self-claim, the
sentinel path — uses the lowercase form. `[planner]`, `[PLAN]`,
`[tester]`, `[qa]` all break either the format check (wrong role
name) or the downstream claim logic (no teammate matches the tag).
Stick to the four canonical role names exactly.

```
✅ [plan] / [design] / [dev] / [review]
❌ [planner] / [designer] / [developer] / [reviewer] (full names)
❌ [PLAN] / [Dev] (wrong case)
❌ [tester] / [qa] / [arch] (not a defined role)
```

### 3. The pipe character is reserved — do not let it appear inside slot bodies

The hook just counts pipes. It does not parse escape sequences. If
your `<what>` or `<acceptance>` description contains a literal `|`,
the hook over-counts and downstream tools that split on `|` to extract
slots will mis-split.

```
❌ [dev] add OR | AND filter | src/filter.ts | parses A|B|C. Run: npm test
   (5 pipes — splits into garbage)
✅ [dev] add OR/AND filter | src/filter.ts | parses A or B or C. Run: npm test
```

Rephrase or replace `|` with `or` / `,` / `/`. Same applies to anything
you paste from logs or example commands — strip pipes from the task
text before pasting.

### 4. `[skip-format-check]` is for coordination tasks only, not a way to ship sloppy work

The bypass exists for real cases: "read these docs and brief the
team", "wait for designer's color palette before claiming UI tasks".
These have no useful `Run:` command and forcing one produces a fake
verification step.

The bypass is NOT a way to dodge writing acceptance criteria for a
real build task. If you find yourself reaching for `[skip-format-check]`
on a `[dev]` task that produces code, stop — the right move is to write
the acceptance and the `Run:` properly. Using bypass here means the
teammate downstream has no verification target and the reviewer cannot
tell when the task is done.

### 5. `[skip-verify]` is for docs-only; prefer a cheap real `Run:`

`[skip-verify]` exempts the completion sentinel — the task can be
marked complete without the teammate writing the
`~/.claude/logs/verified/<team>/task-<id>.verified` file. Legitimate
case: "update CHANGELOG.md" has nothing to verify beyond "the file
was edited."

Even there, a `Run: test -s CHANGELOG.md` or `Run: grep -q '<entry>'
CHANGELOG.md` is preferable. The sentinel is the only mechanism the
hook has to confirm the teammate actually checked their work; bypassing
it on anything non-trivial means a teammate can mark `completed`
without ever running anything. Reserve `[skip-verify]` for the
unambiguously-runnable-nothing case.

### 6. Tasks in the same parallel group must not write to the same file

Group structure exists so multiple teammates work in parallel. Two
tasks in one group editing the same file = silent overwrites — whoever
saves last wins, the other's work is gone, and the reviewer has no
easy way to detect it because each task individually "passed" its
verification.

Before locking a group, scan the `<file paths>` slot of every task in
it. If two tasks list the same path, split them into sequential groups
or merge them into one task. Watch especially for index files
(`src/index.ts`, route registries, `__init__.py`) — these attract
collisions because every feature touches them.

**Groups nest inside the phase→ckpt tree.** `specs/tasks.md` is a
markdown heading tree (PROCESS.md §2 — 분해 공식 고정: phase1=환경설정,
phase2=프론트 디자인, phase3+=개발):

```
## phase3 — 인증
### phase3.ckpt1 로그인 API  ← F1
- [ ] [dev] add /api/login endpoint | src/api/login.ts | POST {...} → {...}. Run: npm test -- login
### phase3.ckpt2 로그인 폼  ← F1
- [ ] [dev] add login form | src/ui/login.tsx | POSTs to /api/login ... Run: npm test -- login-form
```

The ckpt ID (`phaseN.ckptN`) is a **convention in the heading + the
task's slot-2 free text** — the `TaskCreated` hook is unchanged (it
only checks the role tag, ≥2 pipes, and `Run:`; ckpt IDs live in free
text and pass as-is). A "group" (the parallel-dispatch, no-same-file
unit above) is the leaf inside a ckpt. ckpt progress derives from
nested done-box counts (완료 `[✅]`, 레거시 `[x]` 도) — no separate status
file (cto_statusline 훅이 이 카운트로 현재 ckpt 를 표시한다 — 헤딩에
status box 를 두지 마라). The
segment loop (PROCESS.md §3) dispatches a `phaseN.ckptN~phaseM.ckptM`
range, so **never renumber a ckpt ID after a segment may reference it.**

### 7. Interface contracts go INLINE in the task, not by reference

When task A produces a type / endpoint / file format that task B
consumes, the contract belongs in both tasks' `<acceptance>` slot as
literal text. Not "see spec.md section 3" — that loses the contract
during cross-task review when the reviewer reads tasks linearly.

```
✅ [dev] add /api/login endpoint | src/api/login.ts | POST {email,password} → {token:string,expiresAt:ISO}. Run: npm test -- login
✅ [dev] add login form caller | src/ui/login.tsx | POSTs to /api/login, reads {token,expiresAt} from response. Run: npm test -- login-form
❌ [dev] add /api/login endpoint | src/api/login.ts | see spec.md §3.2. Run: npm test -- login
```

The contract being visible at both sides of the boundary means a
reviewer reading one task immediately sees the other side's
expectation. Indirection (`see spec.md`) defeats this — the contract
drifts when the spec is edited without both tasks being re-checked.

### 8. Ckpt headings carry a `← F<n>` back-ref (커버리지 기계 검증)

The phase→ckpt tree doubles as the **coverage trace** (PROCESS.md §2
장치1, RULES §7 — fail-closed). Each ckpt heading carries a free-text
suffix `← F<n>[, ← F<n>...]` naming which `specs/spec.md` `## Features`
label(s) (`- [F1] ...`) it covers:

```
### phase3.ckpt1 로그인 API  ← F1
### phase3.ckpt2 구글 로그인  ← F2
### phase4.ckpt1 게시글 CRUD  ← F3, ← F4
```

The suffix is free text in the heading, so — exactly like the ckpt ID
in gotcha #6 — the `TaskCreated` hook does not care: the hook only
inspects task LINES (role tag, ≥2 pipes, `Run:`), not ckpt HEADINGS.
Nothing rolls back.

**The rule (fail-closed):** every `spec.md` `## Features` label
(supplied 포함) must be referenced by ≥1 ckpt heading. A label with no
ref = a feature planned but assigned to no ckpt — 분해 미완, segment
진행 금지. `${CLAUDE_SKILL_DIR}/scripts/scan_spec_coverage.sh specs/`
(exit 0 clean / 1 omission-or-stray / 2 usage) is the GATE INPUT — the
planner runs it after decomposition and a nonzero exit blocks handoff.

**Boundary:** this is spec↔tree **internal** coverage only — it does NOT
check whether the spec itself captured everything the user wanted
(intent→spec is the CEO 1단계 / `harness-unknowns-check` gate).

## Files in this skill

- `SKILL.md` — this overview (always loaded when skill triggers).
- `references/format-anatomy.md` — slot-by-slot breakdown of the
  format, with worked examples per role and common rollback messages.
- `references/bypass-tokens.md` — `[skip-format-check]` vs.
  `[skip-verify]`, when each is legitimate, and the audit trail to
  leave when using them.
- `references/grouping-and-contracts.md` — file-collision avoidance
  rules and the inline-contract pattern for tasks that share types.
- `${CLAUDE_SKILL_DIR}/scripts/validate_task_line.sh` — mirrors the hook
  regex. Pipe a candidate line on stdin (or pass as argv), exits 0 if
  valid, non-zero with a specific message on stderr otherwise.
- `${CLAUDE_SKILL_DIR}/scripts/scan_spec_coverage.sh` — advisory G1 completeness check
  (fail-closed gate input). Compares `spec.md` `## Features` `[F<n>]` labels
  against `tasks.md` ckpt-heading `← F<n>` refs; prints omissions and
  stray refs. Exit 0 clean / 1 omission-or-stray / 2 usage. Advisory
  only — the reviewer's 8th step makes the FAIL call; NOT a hook.

## On-demand hook hint

The `TaskCreated` hook is already installed by the harness. If you
want a *pre*-flight check that catches violations before they hit the
hook (e.g. when authoring `tasks.md` in bulk), wire a `PreToolUse`
matcher on `TaskCreate` / `TaskUpdate` that pipes the subject through
`${CLAUDE_SKILL_DIR}/scripts/validate_task_line.sh` and rejects malformed lines locally.
This skill does not install that hook by default — the existing
post-creation rollback is already authoritative; a pre-flight is just
a faster feedback loop when you are drafting many tasks at once.
