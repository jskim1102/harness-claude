# Grouping and inline contracts

`tasks.md` organizes tasks into parallel groups. The group is the unit
of "run these together"; the planner decides what is parallelizable.
Two rules govern group composition: no shared writes, and contracts
inline.

## Rule 1 — No two tasks in a group write the same file

Two subagents (fanned out by the one role teammate via the Task
tool, no panes) editing the same file in parallel is a guaranteed
silent overwrite. Whoever's write lands second wins; the
first subagent's diff is gone. Each task individually "passed" its
verification (it ran its `Run:` command in isolation against its own
state), so the reviewer's PASS / FAIL signal is uninformative —
nothing FAILed, but the build is wrong.

### Pre-flight check before locking a group

For each task in the group, list the paths in slot 3 (the file paths
between the pipes). Look for overlaps. Overlaps include:

- Exact path collisions: two tasks both list `src/index.ts`.
- Directory collisions: task A lists `src/components/`, task B lists
  `src/components/Login.tsx`. The directory wildcard subsumes the file.
- Index-file collisions: every task says "and edit
  `src/router.ts` to register the new route." This is the most common
  failure mode because index registration feels like a small append.

When you find an overlap, you have three options:

1. **Sequence**: move one of the tasks to a later group so they run
   serially.
2. **Serialize**: since all group tasks already run under one role
   teammate, sequence the two colliding tasks as serial subagent calls
   within that same teammate (or merge into one task). Lose parallelism
   for that pair, gain correctness — no teammate count changes.
3. **Split the shared file**: refactor so each task writes to its own
   submodule. The router becomes one task that registers a list of
   routes which the per-route tasks export individually.

### Why this is not auto-detected

The `TaskCreated` hook does not parse the file-paths slot — it only
counts pipes. Detecting collisions would require parsing across all
tasks in the group, which the hook does not do. The check is the
planner's responsibility at authoring time.

### Index-file collision pattern

```
Group 3 (parallel):
- [ ] [dev] add login route | src/routes/login.ts, src/router.ts | route registered. Run: npm test
- [ ] [dev] add signup route | src/routes/signup.ts, src/router.ts | route registered. Run: npm test
- [ ] [dev] add reset route | src/routes/reset.ts, src/router.ts | route registered. Run: npm test
```

Three subagents (fanned out by the one developer teammate) each
appending to `src/router.ts` in parallel = chaos.
Restructure:

```
Group 3 (parallel subagent fan-out — each owns its own route file):
- [ ] [dev] add login route handler | src/routes/login.ts | exports loginRoute. Run: npm test -- routes/login
- [ ] [dev] add signup route handler | src/routes/signup.ts | exports signupRoute. Run: npm test -- routes/signup
- [ ] [dev] add reset route handler | src/routes/reset.ts | exports resetRoute. Run: npm test -- routes/reset

Group 4 (serial subagent call within the same developer teammate — registers all three at once):
- [ ] [dev] register auth routes | src/router.ts | imports {login,signup,reset}Route and mounts them. Run: npm test -- routes
```

## Rule 2 — Interface contracts go inline

When task A produces a type, endpoint, or file format that task B
consumes, the contract lives in the acceptance slot of both tasks. As
literal text.

### Anti-pattern: indirection

```
❌ [dev] add /api/login endpoint | src/api/login.ts | see spec.md §3.2. Run: npm test
❌ [dev] add login form caller | src/ui/login.tsx | matches spec.md §3.2. Run: npm test
```

The reviewer reads the tasks linearly and has no idea what §3.2 says
without re-opening the spec. The contract drifts when the spec is
edited but the tasks are not, or vice versa.

### Correct pattern: contract literal at both endpoints

```
✅ [dev] add /api/login endpoint | src/api/login.ts | POST {email,password} → 200 {token:string,expiresAt:ISO8601} | 401 {error:string}. Run: npm test -- src/api/login
✅ [dev] add login form caller | src/ui/login.tsx | POSTs {email,password} to /api/login, reads {token,expiresAt} from response, displays error on 401. Run: npm test -- src/ui/login
```

The reviewer reading either task immediately sees the boundary on the
other side. If the implementer of either side diverges from the
contract, the reviewer catches it at the contract level without needing
to cross-reference spec.md.

### When the contract is long

If the contract is too long to fit in one acceptance line (e.g. a JSON
schema with many fields), the right move is to make the contract a
file that both tasks reference and verify against — and put the path
to that file inline:

```
✅ [dev] add /api/login endpoint | src/api/login.ts | response matches schema in src/api/login.schema.json. Run: npm test -- src/api/login
✅ [dev] add login form caller | src/ui/login.tsx | parses response per src/api/login.schema.json. Run: npm test -- src/ui/login
```

The schema file is itself produced by an earlier `[plan]` or `[design]`
task. The contract is still inline — it is the schema file path, which
both tasks pin against. Drift becomes a schema diff, which the
reviewer can detect mechanically.

## How the planner decides groups

Roughly:

1. Identify every task the spec implies.
2. Build a dependency DAG (task B uses task A's output → B depends on A).
3. Within each layer of the DAG, check for file collisions. Split or
   merge until the layer is collision-free.
4. The layer becomes a parallel group.

Each parallel group/layer is executed by the single role teammate for
that layer, which fans the collision-free tasks out to Task subagents;
the planner's DAG + collision analysis feeds that one teammate's
subagent scheduling, not a teammate count.

Tasks with no dependencies between them but with file collisions are
serialized into separate groups even though the DAG says they could
parallelize. Collision correctness wins over parallelism.

## Bad symptoms to look for

- **Reviewer FAIL with "feature X works but feature Y is gone"**:
  almost always a same-file collision. Check the group's file paths.
- **Both subagents report PASS but the build is broken**: same (the
  one role teammate's fan-out — check the group's file paths).
- **Teammate edits a file that is not in their task's file paths
  slot**: an `agent-team-protocol` violation, but also a sign the
  planner under-specified the slot. Add the file or split the task.
