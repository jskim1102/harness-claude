# docs/claude-code-docs/ — Claude Code Official Docs (cached)

Verbatim local caches of Claude Code's official documentation pages, kept so the
harness builders can consult the spec offline.

## What's here

- `sub-agents.md` — cache of <https://code.claude.com/docs/en/sub-agents>.
  Defines frontmatter fields, tools allowlist semantics, permission modes,
  hooks-in-subagent, preload-skills semantics, memory scopes.
- `skills.md` — cache of <https://code.claude.com/docs/en/skills>. Defines
  SKILL.md frontmatter, plugin namespace (`<plugin>:<skill>`), invocation
  control, scoping.

## Not cached locally (URL-only)

- <https://code.claude.com/docs/en/agent-teams> — Agent Teams main doc
- <https://code.claude.com/docs/ko/agent-teams> — Korean translation
- <https://code.claude.com/docs/en/hooks> — TeammateIdle, TaskCreated,
  TaskCompleted, SubagentStart, SubagentStop schemas
- <https://code.claude.com/docs/en/settings> — settings.json fields
  (`env`, `teammateMode`, `effortLevel`, `permissions`)

If those URLs become inaccessible, re-fetch via `WebFetch` and save here.

## How our design maps to these references

See `docs/agent-teams-mapping.md` (one level up) for the full mapping: which
official feature we use, which AWS sample pattern we copy, and which decisions
are ours. The AWS sample clone lives at `references/aws-sample/`.
