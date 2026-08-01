#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) — `specs/tasks.md` 의 `[review]` 완료 편집 게이트.

왜 이 훅이 따로 필요한가 (2026-07-27):
  `task_completed_verify_gate.py` 는 Claude **작업목록(task store)** 의
  `TaskCompleted` 이벤트에 걸려 있다. 그런데 실측상 최근 빌드들은 작업목록을
  아예 쓰지 않는다 — rescue-pose·rtsp-keypoint·bulk-receipe 는 TaskCreated/
  TaskCompleted 가 **0건**이고(TeammateIdle 은 37~64건), 실 프로젝트의 마지막
  작업목록 기록은 2026-07-21 rtsp-detection 이다. 즉 진행 상태는 전부
  `specs/tasks.md` 체크박스로만 흐르고, 완료 게이트는 그 경로 밖에 있었다.

  PROCESS §3.8 이 `tasks.md` 를 진행 상태의 단일 소스로 규정하므로, 게이트도
  거기 걸어야 한다. 이 훅은 **작업목록 사용 여부와 무관하게** 발동한다.

무엇을 막나:
  `<빌드>/specs/tasks.md` 안의 `[review]` task 줄이 미완(`[ ]`)에서
  완료(`[✅]`/`[x]`)로 바뀌는 편집을, 회귀 검사가 통과하지 않았으면 차단한다.
  판정 로직은 `team_hook_common.regression_missing()` 하나를 TaskCompleted
  게이트와 공유한다 (구현이 갈리면 한쪽만 조여진다).

무엇을 막지 않나 (의도적):
  · `[dev]`/`[design]`/`[plan]` 체크박스 — 이 훅의 관심사가 아니다
  · 이미 완료된 줄을 그대로 다시 쓰는 편집 (상태 전이가 없음)
  · `[review]` 를 `[❓]`(블로커)로 바꾸는 편집 — 오히려 권장되는 정직한 표시
  · per-segment waiver 파일이 있는 경우 — 사용자가 명시 waive 한 segment

FAIL OPEN: 내부 오류는 항상 허용. 단 `regressions > 0` 은 오류가 아니라 결과이므로
차단한다 (team_hook_common.regression_missing 의 계약과 동일).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import (read_payload, allow, block, audit,  # noqa: E402
                              project_of, regression_missing, safe_key)

EVENT = "PreToolUse"
WAIVER_DIR = os.path.join(os.path.expanduser("~"), ".harness-claude", "review-waivers")

# `- [ ] [review] …` → `- [✅] [review] …` 형태의 완료 전이만 관심사.
REVIEW_DONE_RE = re.compile(r"^\s*[-*]\s*\[(✅|x|X)\]\s*.*\[review\]", re.M)
REVIEW_OPEN_RE = re.compile(r"^\s*[-*]\s*\[( |❓|!)\]\s*.*\[review\]", re.M)


def _target_is_tasks_md(path):
    p = (path or "").replace("\\", "/")
    return p.endswith("/specs/tasks.md") or p == "specs/tasks.md"


def _edits(tool_input):
    """(old, new) 쌍 목록. Write 는 (None, content), Edit/MultiEdit 는 문자열 쌍."""
    out = []
    if not isinstance(tool_input, dict):
        return out
    if "content" in tool_input:
        out.append((None, str(tool_input.get("content") or "")))
    if "old_string" in tool_input or "new_string" in tool_input:
        out.append((str(tool_input.get("old_string") or ""),
                    str(tool_input.get("new_string") or "")))
    for e in (tool_input.get("edits") or []):
        if isinstance(e, dict):
            out.append((str(e.get("old_string") or ""), str(e.get("new_string") or "")))
    return out


def closes_review(pairs):
    """이 편집이 `[review]` 를 미완→완료로 닫는가. 순수 함수 (smoke 단위 검증용).

    Write(전체 덮어쓰기)는 old 가 없으므로 새 본문에 완료된 `[review]` 가 있으면
    보수적으로 '닫는 편집'으로 본다 — tasks.md 전체 덮어쓰기는 이미
    `spec_overwrite_gate` 가 별도로 다루는 드문 경로다.
    """
    for old, new in pairs:
        new_done = len(REVIEW_DONE_RE.findall(new))
        if new_done == 0:
            continue
        if old is None:
            return True
        old_done = len(REVIEW_DONE_RE.findall(old))
        if new_done > old_done:
            return True
        # 같은 수라도 미완이 사라졌으면 전이로 본다
        if REVIEW_OPEN_RE.search(old) and not REVIEW_OPEN_RE.search(new):
            return True
    return False


def _waived(proj):
    """segment 단위 waiver — task id 를 모르므로 프로젝트 디렉토리에 파일이 하나라도
    있으면 이 훅은 물러난다. 정밀 판정은 TaskCompleted 게이트가 한다."""
    d = os.path.join(WAIVER_DIR, safe_key(proj))
    try:
        return any(n.endswith(".waiver") for n in os.listdir(d))
    except Exception:
        return False


def main():
    p = read_payload()
    ti = p.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ""

    if not _target_is_tasks_md(path):
        sys.exit(0)                      # 관심 대상 아님 — 조용히 통과 (감사 소음 방지)

    pairs = _edits(ti)
    if not closes_review(pairs):
        sys.exit(0)                      # [review] 완료 전이가 아님

    proj = project_of(p)
    if _waived(proj):
        allow(EVENT, p, reason="review waived for this segment (waiver file)")

    missing = regression_missing(proj)
    if missing:
        block(EVENT, p,
              "`[review]` 완료 차단 ({}): {}\n"
              "이 게이트는 작업목록(task store) 사용 여부와 무관하게 tasks.md 편집에서 "
              "발동한다 (PROCESS §3 5.4). 회귀가 0 이 된 뒤 다시 체크하라.".format(
                  proj, "; ".join(missing)))

    allow(EVENT, p, reason="tasks.md [review] 완료 — 회귀 0 확인")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                                   # FAIL OPEN
        audit(EVENT, {}, "allow", reason="hook error (fail-open): {}".format(e))
        sys.exit(0)
