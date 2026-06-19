#!/usr/bin/env python3
"""TaskCreated hook — enforce task authoring format. Exit 2 rolls back creation.

Authoring rule (harness-claude agent-team-protocol): a task must carry a role
tag `[plan|design|dev|review]`, pipe-delimited `| <files> | <acceptance>`, and a
`Run: <command>`. The check runs on subject + description combined.

Bypass: include the token [skip-format-check] anywhere in the subject or
description for legitimate non-build / coordination tasks.

FAIL OPEN: any internal error allows the creation.

Adapted from aws-samples/sample-claude-code-agent-team.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block, audit, ROLES  # noqa: E402

EVENT = "TaskCreated"
ROLE_TAG = re.compile(r"\[(" + "|".join(ROLES) + r")\]", re.I)
RUN_CMD = re.compile(r"\bRun:\s*\S")


def main():
    p = read_payload()
    # Empty/unparseable payload (no task_id): can't assess — fail open, never roll back.
    if not p.get("task_id"):
        allow(EVENT, p, reason="incomplete payload (no task_id) — fail-open")

    text = "{}\n{}".format(p.get("task_subject", ""), p.get("task_description", "")).strip()

    if "[skip-format-check]" in text.lower():
        allow(EVENT, p, reason="bypass token present")

    missing = []
    if not ROLE_TAG.search(text):
        missing.append("`[role]` tag — one of " + " ".join("[" + r + "]" for r in ROLES))
    # pipe 슬롯은 `Run:` 앞에 산다 (`[role] … | <files> | <acceptance>. Run: <cmd>`).
    # 정확히 2개(3슬롯)여야 한다 — 적으면 슬롯 누락, 많으면 슬롯 본문에 stray `|`
    # 가 섞여 downstream split 이 깨진다(gotcha #3 결정론화). Run 명령 자체의
    # pipe(`pytest | tail`)는 구분자가 아니므로 Run: 이후는 세지 않는다.
    slot_seg = re.split(r"\bRun:", text, maxsplit=1)[0]
    n_pipes = slot_seg.count("|")
    if n_pipes != 2:
        missing.append(
            "`| <file paths> | <acceptance>` — Run: 앞 슬롯 구간 pipe 정확히 2개 "
            "(현재 {}); 슬롯 본문의 `|` 는 or/,// 로 교체".format(n_pipes)
        )
    if not RUN_CMD.search(text):
        missing.append("`Run: <command>` — the verification command")

    if missing:
        reason = (
            "Task #{} rejected by format check. Missing: {}.\n"
            "Required shape: `[role] <verb> <what> | <files> | <acceptance>. Run: <command>`\n"
            "Fix and recreate, or add [skip-format-check] for a non-build task."
        ).format(p.get("task_id", "?"), "; ".join(missing))
        block(EVENT, p, reason)

    allow(EVENT, p, reason="format ok")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # FAIL OPEN
        audit(EVENT, {}, "allow", reason="hook error (fail-open): {}".format(e))
        sys.exit(0)
