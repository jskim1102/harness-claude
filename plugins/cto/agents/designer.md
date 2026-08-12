---
name: designer
description: INACTIVE LEGACY — design is owned by the independent designer-cto session (plugins/designer-cto/role.md). Never spawn this agent.
---

> **INACTIVE LEGACY ROLE — tombstone.** `run.sh` deliberately skips installing
> this file into CTO projects (agent install filter), `hooks/team/
> one_teammate_per_role_gate.py` blocks spawning it, and `hooks/team/
> sendmessage_recipient_gate.py` blocks messaging it.
>
> Design is owned by the **independent designer-cto session** — the active
> contract lives at `plugins/designer-cto/role.md` (phase2 design chain,
> 브라우저 검수 루프 + Design-Max 모드, paired-inbox protocol included there). Reach it
> with `harness send --to designer-cto:<name>`.
>
> The full legacy teammate body was removed 2026-07-29 by the designer split
> (specs/2026-07-29-designer-cto-split-design.md) — its content moved, adapted,
> into the role.md above. History: `git log -- plugins/cto/agents/designer.md`.
