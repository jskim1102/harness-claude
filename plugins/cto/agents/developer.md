---
name: developer
description: INACTIVE LEGACY — production development is owned by the external Codex session (plugins/codex-cto/role.md). Never spawn this agent.
---

> **INACTIVE LEGACY ROLE — tombstone.** `run.sh` deliberately skips installing
> this file into CTO projects (`write_role_settings` filters `developer.md`),
> `hooks/team/one_teammate_per_role_gate.py` blocks spawning it, and
> `hooks/team/sendmessage_recipient_gate.py` blocks messaging it.
>
> Production development is owned by the **separate Codex session** — the
> active contract lives at `plugins/codex-cto/role.md` (phase1 environment
> setup, phase3+ development, TDD, live-app verification, mediamtx/port
> rules included there).
>
> The full legacy body (301 lines) was removed 2026-07-28 by harness audit —
> it duplicated the codex-cto contract and invited accidental edits against a
> role that cannot run. History: `git log -- plugins/cto/agents/developer.md`.
