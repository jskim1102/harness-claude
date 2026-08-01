# Resolution paths

Every entry in `## Unknowns` must end with a resolution path: the
concrete next action that will close the unknown. The resolution path
exists so that "open" is a transient state, not a permanent one.

## The four valid resolution paths

| Path                  | When to use                                      |
| :-------------------- | :----------------------------------------------- |
| `relay to user`       | Decision only the user can make                  |
| `ask <teammate>`      | A specific teammate owns the answer              |
| `read <file>`         | The answer exists in a file you can open         |
| `run <command>`       | The answer is observable from a tool / command   |

Each has a worked example below. The important property is that the
resolution path names **who acts next** and **what they do** — no
ambiguity about who is responsible for closing the unknown.

## `relay to user`

The standard path for sticky decisions only the user can make:
framework choice, auth provider, durability requirements, brand
voice, target user.

```markdown
- [ ] expected DAU range (affects DB choice) — relay to user
- [ ] should the signup form require email confirmation? — relay to user
```

When you walk this path: send `[user-q]` to the lead per
`harness-relay-qa`. When the answer comes back, tick the checkbox
(`- [✅]`) and inline the answer in the spec, or emit it as a
`<decision>` block for the CTO to file.

## `ask <teammate>`

Use when another teammate has already made or owns the decision. The
designer owns visual decisions; the planner owns scope; the reviewer
owns acceptance interpretation.

```markdown
- [ ] does design.md commit to a specific color system? — ask designer
- [ ] is the eng review pass criteria documented? — ask reviewer
```

Direct `SendMessage` to that teammate. Do not relay through the user
for things another teammate already knows.

## `read <file>`

Use when the answer is sitting in a file you have not opened yet.

```markdown
- [ ] is there an existing DESIGN.md in the repo? — read ./DESIGN.md
- [ ] what test runner does this project use? — read ./package.json
- [ ] does spec.md already specify the DB engine? — read specs/spec.md
```

If the file does not exist, the unknown survives and you escalate to
relay / ask. Reading is the cheapest path — try it first when
applicable.

## `run <command>`

Use when the answer is observable, not stored. Lint state, test
state, whether a port is open, whether a build passes.

```markdown
- [ ] does the current main pass `npm run lint`? — run `npm run lint`
- [ ] is the dev server already running on port 3000? — run `lsof -i :3000`
- [ ] does the existing test suite pass? — run `npm test`
```

Output of the command is the answer. Capture it in the spec (or emit a
`<decision>` block if it is a fork worth filing) and tick the unknown.

## Bad resolution paths

These look like resolution paths but aren't. Anti-pattern in your
own draft if you see them.

### "TBD"

```markdown
❌ - [ ] auth provider — TBD
```

No owner, no action, no timeline. "TBD" is what you write when you
want to look thorough without doing the work. Replace with one of
the four valid paths, or downgrade to accepted-with-risk.

### "decide later" / "figure out in <phase>"

```markdown
❌ - [ ] color palette — figure out in design phase
❌ - [ ] DB engine — decide later
```

These push the decision forward without specifying who decides or
how. The design phase will inherit an unknown with no resolution
path, and the designer will either re-ask the user (wasted round) or
silently guess (the failure mode this whole skill exists to prevent).

If the designer is genuinely the right owner, write
`ask designer`. If it's a relay, write `relay to user`. Be concrete.

### "do research"

```markdown
❌ - [ ] best auth provider for our scale — do research
```

Research isn't a resolution path; it's procrastination dressed as
diligence. Either there is a file / command / teammate / user that
answers this (pick one and write the concrete path), or there isn't
(downgrade to accepted-with-risk and pick something defensible).

### "depends on X"

```markdown
❌ - [ ] DB engine — depends on auth provider
```

Express the dependency, not the resolution. If unknown A blocks
unknown B, link them:

```markdown
- [ ] auth provider — relay to user
- [ ] DB engine — depends on auth provider (resolves when auth provider known)
```

But B still needs a concrete resolution path of its own once A is
closed. "Depends on X" alone is not enough.

## Updating resolution paths across cycles

Resolution paths can change. If you started with `read DESIGN.md` and
that file turned out not to exist, the unknown isn't resolved — the
resolution path failed and you need a new one (`relay to user`).
Update the line, do not tick the checkbox.

```markdown
- [ ] design system reuse — ~~read DESIGN.md~~ → relay to user
      (DESIGN.md not present in repo)
```

The strikethrough + new path is honest: it documents that you tried
the cheap path and had to escalate.
