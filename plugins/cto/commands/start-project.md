---
description: Spawn the 2-Claude team (planner, reviewer) only.
argument-hint: [optional note]
---

# /start-project

이 명령의 유일한 목적은 Claude Agent Team 2명(`planner`, `reviewer`)을
spawn하는 것이다. plan.md, specs, tasks, segment, phase를 읽거나 검증하거나
진행하지 않는다. 별도 Codex 세션은 `add-cto`가 이미 준비한 것을 그대로 둔다.
외부 `codex-cto-<name>` 세션은 production developer로 유지하지만 이 명령에서
시작·재시작·작업 지시는 하지 않는다.

```
$ARGUMENTS
```

## Step 0 — Codex 상태 확인

`HARNESS_ROLE=cto:<name>`에서 name을 구하고 다음을 **조회만** 한다.

```bash
harness roles
```

세션이 없으면 사용자에게 `./run.sh add-cto <name>`을 안내한다. 자동 실행·재시작은
하지 않는다.

## Step 1 — Spawn Exactly 2 Claude Teammates

Spawn은 fresh/유지보수 판단보다 먼저다. `planner → reviewer`
순서로 두 명 전원을 upfront spawn 한다. `developer`는 외부 Codex 세션이므로
`Agent(subagent_type=developer)`를 절대 호출하지 않는다.

Invoke the `harness-team-spawn` skill. It owns:

- the exact 2-Claude spawn prompt
- plan-approval mode for both Claude teammates

Codex 세션은 Step 0에서 확인한 별도 세션을 그대로 사용한다.

완성 모듈이어도 두 Claude teammate는 모두 spawn 한다. 이 명령에서는 유지보수
여부를 판단하거나 planner에게 재분해 메시지를 보내지 않는다.

### Spawn Self-check

Claude Project tab에는 CTO lead와 skill activity pane이 있어야 한다.

```text
lead CTO + skill activity (planner/reviewer는 in-process 목록; designer 는 독립 탭)
```

Codex developer는 별도 `harness:cto:<name>:codex` Orca tab이다. Claude tab에
`developer` teammate가 있으면 잘못된 구성이다.

## Report

Claude team name과 두 teammate의 spawn 상태만 보고하고 종료한다. plan/tasks/spec
내용, phase/segment, 다음 빌드 행동은 이 명령에서 다루지 않는다.
spawn 직후 teammate가 자발적으로 작업을 시작하면 중단하고 대기하도록 지시한다.
