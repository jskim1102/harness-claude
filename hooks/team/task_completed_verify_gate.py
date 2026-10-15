#!/usr/bin/env python3
"""TaskCompleted hook — presence + sentinel verification gate.

Exit 2 prevents the task from being marked complete unless BOTH hold:
  1. PRESENCE — the task carries a `Run: <command>` (a defined verification step), and
  2. SENTINEL — the completing teammate left a verification marker at
       ~/.claude/logs/verified/<team_name>/task-<task_id>.verified
     written AFTER its Run command passed.

Why a sentinel: the hook payload's transcript_path is the lead's session, not the
teammate's, so the hook cannot observe the teammate actually running tests. The
sentinel is the teammate's attestation. On a successful pass it is consumed
(deleted) so it cannot be reused for a later re-completion.

Teammate convention (documented in agent-team-protocol):
    mkdir -p ~/.claude/logs/verified/<team>
    echo "<Run cmd> PASSED" > ~/.claude/logs/verified/<team>/task-<id>.verified
    # then TaskUpdate(status=completed)

Bypass: token [skip-verify] in subject/description (e.g. docs-only tasks), or
[skip-format-check] — a coordination/no-build task created without a `Run:`
command is exempt from completion verification too (else it would be uncompletable).

EXCEPTION — [review] tasks: the [skip-verify]/[skip-format-check] tokens are
IGNORED for [review] tasks. Review evidence (code-review/qa) is mandatory
(PROCESS §3, reviewer.md) and a model must not be able to self-waive it by
typing a token into tasks.md. The ONLY way to waive review for a segment is an
explicit per-segment WAIVER FILE outside tasks.md, recorded when the user said
"이번 segment 검토 필요없음":
    ~/.harness-claude/review-waivers/<project>/<ckpt-id>.waiver   (정본 — tasks.md 게이트와 공유 키;
                                                                   task 문안의 ckpt id 로 대응)
    ~/.harness-claude/review-waivers/<project>/task-<id>.waiver    (작업목록 task id 키; 레거시 <team>/ 폴백)
Its presence (not any task text) exempts that one [review] task.
FAIL OPEN: any internal error allows the completion.

Adapted from aws-samples/sample-claude-code-agent-team.
"""
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import (read_payload, allow, block, audit,  # noqa: E402
                              VERIFIED_DIR, LOG_DIR, project_of, regression_missing,
                              codereview_paths, codereview_missing)

EVENT = "TaskCompleted"
RUN_CMD = re.compile(r"\bRun:\s*\S")

# Per-segment review waivers live OUTSIDE ~/.claude/tasks (not tasks.md text) so a
# model can't self-grant one by editing a task's subject/description. Recorded by
# the CTO only when the user explicitly said "이번 segment 검토 필요없음".
WAIVER_DIR = os.path.join(os.path.expanduser("~"), ".harness-claude", "review-waivers")


def _safe(s):
    # Whitelist safe filename chars; map everything else (path separators, NUL,
    # control bytes) to "_". This both prevents a hostile team/task_id from
    # escaping VERIFIED_DIR and stops os.path ops from raising on embedded NUL —
    # a raise would propagate to the top-level fail-open and bypass the gate.
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(s))


# 증거 파일 키는 **프로젝트**다 (team_hook_common.project_of). team_name 은
# 세션 파생(`session-<8hex>`)이라 세션 재시작마다 회전해 고아 sentinel 330개를
# 만들었다 (2026-07-27). 레거시 team 키 경로는 읽기 전용 폴백으로만 남긴다 —
# 진행 중인 빌드가 이미 team 키로 써둔 sentinel 을 잃지 않게.
def sentinel_path(proj, task_id):
    return os.path.join(
        VERIFIED_DIR, _safe(proj or "_noteam"),
        "task-{}.verified".format(_safe(task_id)),
    )


def review_waiver_path(proj, task_id):
    return os.path.join(
        WAIVER_DIR, _safe(proj or "_noteam"),
        "task-{}.waiver".format(_safe(task_id)),
    )


CKPT_ID_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_-]*\.ckpt\d+)\b")


def ckpt_waiver_paths(proj, text):
    """task 문안에 적힌 ckpt id 마다 `<proj>/<ckpt-id>.waiver` — tasks_md_review_gate 와
    같은 키. (2026-09-10 반증: 두 게이트가 다른 키를 읽어 문서대로 만든 waiver 를
    한쪽이 무시했다 — 하나의 waiver 파일이 두 게이트를 다 면제해야 한다.)"""
    return [
        os.path.join(WAIVER_DIR, _safe(proj or "_noteam"), "{}.waiver".format(_safe(c)))
        for c in dict.fromkeys(CKPT_ID_RE.findall(text or ""))
    ]


# 하나의 TaskCompleted 이벤트가 훅에 **두 번 배달**된다 (실측 2026-08-02,
# ~/.claude/logs/team-hooks.jsonl): 1차는 teammate 컨텍스트가 실린 payload
# (team_name/teammate_name/permission_mode 있음), 2차는 그것들이 벗겨진 payload —
# session_id·prompt_id·task_id 는 동일하다. 예: cam-distance task#1
#   12:28:42 allow (team=session-a0e3749a, teammate=reviewer, prompt_id=ea4be0c5…)
#   12:28:46 block (team=None,             teammate=None,     prompt_id=ea4be0c5…)
# 1차 allow 가 sentinel 을 소각하므로 2차는 "증거 없음" 으로 판정해 완료를 되돌린다
# → `[review]` 가 구조적으로 닫히지 않는다. 전 이력 실측: 실 빌드 3건 + smoke 픽스처.
#
# 판정은 **논리 이벤트당 한 번**만 내리고, 같은 prompt_id 의 재배달은 1차 판정을
# 재생한다. prompt_id 가 다르면(= 진짜 새 완료 시도) 새 증거를 요구하는 기존 계약은
# 그대로다. prompt_id 가 없는 payload(구 shape)는 종전 동작으로 폴백한다.
def decision_marker_path(proj, task_id):
    return os.path.join(
        VERIFIED_DIR, _safe(proj or "_noteam"),
        "task-{}.consumed".format(_safe(task_id)),
    )


def _read_marker(path):
    try:
        with open(path) as fh:
            return fh.read().strip()
    except Exception:
        return None


def _existing(primary, legacy):
    """새 키 경로를 우선하되, 없으면 레거시(team) 경로를 인정한다."""
    if os.path.exists(primary):
        return primary
    if legacy and legacy != primary and os.path.exists(legacy):
        return legacy
    return None


def main():
    p = read_payload()
    # Empty/unparseable payload (no task_id): can't assess — fail open, never block.
    if not p.get("task_id"):
        allow(EVENT, p, reason="incomplete payload (no task_id) — fail-open")

    text = "{}\n{}".format(p.get("task_subject", ""), p.get("task_description", ""))
    task_id = p.get("task_id", "?")
    team = p.get("team_name")
    proj = project_of(p)

    lower = text.lower()
    is_review = "[review]" in lower

    # 재배달 멱등 — 같은 논리 이벤트를 두 번 판정하지 않는다 (decision_marker_path 참조).
    prompt_id = _safe(p.get("prompt_id") or "")
    marker_p = decision_marker_path(proj, task_id)
    if prompt_id and _read_marker(marker_p) == prompt_id:
        allow(EVENT, p, reason=(
            "same completion event re-delivered (prompt_id {}) — replaying the "
            "prior allow instead of re-consuming evidence".format(prompt_id)))

    # [skip-verify] is the completion-gate bypass. [skip-format-check] declares a
    # no-build / coordination task at creation (it has no `Run:` by design), so it
    # is ALSO exempt here — otherwise such a task passes TaskCreated but can never
    # be marked complete (no Run:, no sentinel). See harness-task-format gotcha #4.
    #
    # BUT NOT for [review] tasks: a model could otherwise add [skip-verify] to a
    # [review] task and self-bypass the MANDATORY code-review/qa evidence gate
    # (PROCESS §3, reviewer.md). For [review] tasks these tokens are IGNORED; the
    # only exemption is an explicit per-segment waiver FILE (outside tasks.md,
    # written by the CTO only when the user said "이번 segment 검토 필요없음").
    if is_review:
        if _existing(review_waiver_path(proj, task_id), review_waiver_path(team, task_id)) \
                or any(os.path.exists(w) for w in ckpt_waiver_paths(proj, text)):
            allow(EVENT, p, reason="review explicitly waived (per-segment waiver file)")
        # else: fall through — tokens ignored, review evidence still required.
    elif "[skip-verify]" in lower or "[skip-format-check]" in lower:
        allow(EVENT, p, reason="bypass token present")

    sp = sentinel_path(proj, task_id)
    found_sp = _existing(sp, sentinel_path(team, task_id))
    missing = []
    if not RUN_CMD.search(text):
        missing.append("task has no `Run:` verification command")
    if not found_sp:
        missing.append(
            "verification sentinel not found at {0} — run the task's `Run:` command, then "
            "`mkdir -p {1} && echo PASSED > {0}` before completing".format(
                sp, os.path.dirname(sp)
            )
        )

    # [review] 태스크는 code-review/qa 스킬을 '이번 리뷰에서' 실제 호출했어야 한다.
    # (2026-06-24 reliability 갭: reviewer 가 수동 static 검증만 하고 PASS 낸 사고.)
    # skill_announce 가 호출 시 .invoked 를 touch, 여기서 직전 [review] 완료(.lastreview)
    # 이후 새 호출이 있었는지 mtime 으로 검사 — 한 번의 code-review 로 여러 세그먼트
    # 리뷰를 때우는 재사용도 막는다.
    if is_review:
        missing.extend(codereview_missing(proj))
        missing.extend(regression_missing(proj))

    if missing:
        footer = (
            "[review] 는 [skip-verify] 로 면제되지 않는다 — 사용자가 이 segment 를 "
            "명시 waive 한 경우에만 CTO 가 {} 를 만들어 면제한다.".format(
                (ckpt_waiver_paths(proj, text) or [review_waiver_path(proj, task_id)])[0])
            if is_review else
            "If this task genuinely needs no verification, add [skip-verify] to it."
        )
        reason = (
            "Completion of task #{} blocked by the verification gate: {}.\n{}"
        ).format(task_id, "; ".join(missing), footer)
        block(EVENT, p, reason)

    # Passed: consume the sentinel so it can't be reused (legacy 경로였으면 그것을).
    # 소각 **전에** 이 논리 이벤트의 판정을 기록한다 — 기록이 소각보다 늦으면 그
    # 사이의 재배달이 다시 증거 없음으로 판정한다.
    if prompt_id:
        try:
            os.makedirs(os.path.dirname(marker_p), exist_ok=True)
            with open(marker_p, "w") as _fh:
                _fh.write(prompt_id)
        except Exception:
            pass
    try:
        os.remove(found_sp or sp)
    except Exception:
        pass
    # [review] 통과 → .lastreview 갱신: 다음 [review] 는 새 code-review 호출을 요구.
    if is_review:
        try:
            _, last_p = codereview_paths(proj)
            os.makedirs(os.path.dirname(last_p), exist_ok=True)
            with open(last_p, "w") as _fh:
                _fh.write(str(time.time()))
        except Exception:
            pass
    allow(EVENT, p, reason="verified (presence + sentinel" + (" + code-review" if is_review else "") + ")")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:  # FAIL OPEN
        audit(EVENT, {}, "allow", reason="hook error (fail-open): {}".format(e))
        sys.exit(0)
