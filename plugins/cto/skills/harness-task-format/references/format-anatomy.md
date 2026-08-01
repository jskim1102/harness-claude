# Format anatomy

The shape, slot by slot, with what the hook checks at each one and
worked examples per role.

```
[role] <verb> <what> | <file paths> | <acceptance>. Run: <command>
└──┬──┘ └──────┬─────┘   └────┬───┘   └─────┬────┘  └────┬────┘
   1          2              3              4              5
```

## Slot 1 — `[role]` tag

One of `plan`, `design`, `dev`, `review`. Lowercase. Inside square
brackets.

Hook check: regex `\[(plan|design|dev|review)\]` (case-insensitive at
the hook layer, but lowercase by convention).

Why this slot exists: the `TeammateIdle` hook and the self-claim
lifecycle both key off this tag. A `[design]` task is invisible to the
developer's idle check and vice versa.

## Slot 2 — `<verb> <what>`

Free-form description of what the task does. Verb-first ("add", "fix",
"write", "verify") so the intent is scannable.

Hook check: none (free text, just must not contain stray `|`).

Why this slot exists: it is the human-readable label. Reviewer logs and
completion summaries echo this back to the user.

## Slot 3 — `<file paths>`

Comma-separated file or directory paths the task is allowed to write.
This is the file-ownership boundary; teammates are expected to only
edit these.

Hook check: presence of the first `|`. The hook does not validate paths
exist or are sensible.

Why this slot exists: the file-ownership rule in `agent-team-protocol`
keys off this slot to detect collisions across the same group. See
`grouping-and-contracts.md` for the collision-avoidance pattern.

## Slot 4 — `<acceptance>`

One-line statement of what "done" looks like. Often "tests pass",
"endpoint returns 200", "3 variants present in design-preview/", etc.

Hook check: presence of the second `|`.

Why this slot exists: the reviewer reads this verbatim when judging
PASS / FAIL. Vague acceptance ("works correctly") makes reviewer
verdicts unstable; specific acceptance ("POST /api/login with valid
creds returns 200 + JSON {token}") makes them mechanical.

For interface-producing tasks, this slot should contain the literal
contract — see `grouping-and-contracts.md`.

## Slot 5 — `Run: <command>`

The shell command the teammate runs before marking the task complete.
Must follow the literal `Run:` prefix.

Hook check: regex `\bRun:\s*\S` — `Run:` followed by at least one
non-whitespace character.

Why this slot exists: the `TaskCompleted` hook requires a verification
sentinel, and the sentinel records the result of this exact command.
No `Run:` = no sentinel possible = task cannot complete legitimately.

Acceptable `Run:` commands:

- Real test runners: `npm test`, `pytest tests/unit/auth_test.py`
- Linters / type checkers: `npm run lint`, `mypy src/auth/`
- Dry-runs: `terraform plan -out=/tmp/p`, `npm run build --dry-run`
- File existence checks: `test -s DESIGN.md`, `ls design-preview/dashboard | wc -l`
- Cheap curls: `curl -sf http://localhost:3000/healthz`

## Worked examples per role

### `[plan]`

```
[plan] write signup spec | specs/spec.md | spec.md passes plan-eng-review. Run: ls specs/spec.md
[plan] decompose signup into ckpts | specs/tasks.md | 모든 F<n> 이 ckpt heading 에 참조됨. Run: bash scripts/scan_spec_coverage.sh
```

### `[design]`

```
[design] generate dashboard variants | DESIGN.md, design-preview/dashboard/ | 3 visual variants present. Run: ls design-preview/dashboard | wc -l
[design] specify auth flow contract | specs/design.md | design.md has Auth Flow section with 4 states. Run: grep -c "^### State" specs/design.md
```

### `[dev]`

```
[dev] add JWT verifier | src/auth/jwt.ts | unit tests pass for valid/invalid/expired tokens. Run: npm test -- src/auth/jwt
[dev] wire login endpoint | src/api/login.ts, src/api/index.ts | POST /api/login returns {token,expiresAt}. Run: npm test -- src/api/login
```

### `[review]`

```
[review] verify auth group | (검증 전용, 파일 X) | signup/login/expiry 전 케이스 green, 401 경로 포함. Run: cd backend && .venv/bin/python -m pytest tests/test_auth.py -q
[review] check sign-in dogfood | (검증 전용, 파일 X) | 로그인 성공/실패 화면 동작 확인, 콘솔 에러 0. Run: curl -sf -X POST localhost:8001/api/login -d '{"email":"x@y.z","password":"bad"}' -H 'Content-Type: application/json' -o /dev/null -w '%{http_code}' | grep -q 401
```

## Common rollback messages and what they mean

The hook prints what is missing. Map of message → cause:

- `Missing: [role] tag` — slot 1 absent or used a non-canonical role
  name. Fix: insert one of `[plan]/[design]/[dev]/[review]`.
- `Missing: | <file paths> | <acceptance>` — fewer than two `|` in the
  combined subject + description. Fix: add the second pipe even if
  acceptance is one word ("tests pass").
- `Missing: Run: <command>` — no `Run:` prefix in the text. Fix: append
  `. Run: <cmd>` at the end.

If two are missing, the hook reports both in one message. Fix all at
once; do not iterate one fix per rollback round.
