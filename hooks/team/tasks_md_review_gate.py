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
  완료(`[✅]`/`[x]`)로 바뀌는 편집을, 다음 둘 중 하나라도 아니면 차단한다:
    · 회귀 검사 통과 (`team_hook_common.regression_missing`)
    · reviewer 의 code-review/qa 실호출 증거 (`team_hook_common.codereview_missing`)
  판정 로직은 둘 다 `team_hook_common` 하나를 TaskCompleted 게이트와 공유한다
  (구현이 갈리면 한쪽만 조여진다).

  호출-증거 판정이 뒤늦게 합류한 이유 (2026-08-02): 회귀 판정만 공유하고 호출-증거
  판정은 TaskCompleted 쪽에만 있어서, 작업목록을 안 쓰고 tasks.md 로만 흐르는
  빌드는 **reviewer 를 한 번도 dispatch 하지 않고 `[review]` 를 닫을 수 있었다.**
  실측: rtsp-keypoint phase4 — 체크박스가 코드 착지(v3.0.1) 후 사후에 찍혔고,
  ckpt2 revert→FAIL 뮤테이션 검증과 ckpt4 실카메라 검증이 미수행으로 남았다.

  ★ 이 훅은 PreToolUse(편집 **전**)라서 `.lastreview` 를 쓰지 않는다 — 판정 시점에
  비가역 상태를 남기면 편집이 실제로 성사되지 않았을 때 증거가 오염된다(같은 실수를
  TaskCompleted 게이트가 저질러 `[review]` 가 구조적으로 안 닫혔다, 2026-08-02).
  잔여 한계: 그래서 이 경로에서는 한 번의 code-review 호출이 여러 `[review]` 줄을
  닫는 것을 막지 못한다. 0회를 막는 것이 이 게이트의 몫이고, 재사용 방지는
  TaskCompleted 경로가 담당한다.

무엇을 막지 않나 (의도적):
  · `[dev]`/`[design]`/`[plan]` 체크박스 — 이 훅의 관심사가 아니다
  · 이미 완료된 줄을 그대로 다시 쓰는 편집 (상태 전이가 없음)
  · `[review]` 를 `[❓]`(블로커)로 바꾸는 편집 — 오히려 권장되는 정직한 표시
  · 닫히는 `[review]` 줄이 속한 ckpt 의 waiver 파일
    (`~/.harness-claude/review-waivers/<proj>/<ckpt-id>.waiver`) 이 있는 경우 —
    사용자가 명시 waive 한 segment. ckpt 를 역산 못 하면 면제 없음 (2026-09-10
    Astra 감사 F5: 구 판정 "폴더에 .waiver 하나라도" 는 지우는 코드가 없어 첫
    waive 가 프로젝트 리뷰게이트를 영구 해제했다)

FAIL OPEN: 내부 오류는 항상 허용. 단 `regressions > 0` 은 오류가 아니라 결과이므로
차단한다 (team_hook_common.regression_missing 의 계약과 동일).
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import (read_payload, allow, block, audit,  # noqa: E402
                              project_of, regression_missing, codereview_missing,
                              safe_key)

EVENT = "PreToolUse"
WAIVER_DIR = os.path.join(os.path.expanduser("~"), ".harness-claude", "review-waivers")

# `- [ ] [review] …` → `- [✅] [review] …` 형태의 완료 전이만 관심사.
REVIEW_DONE_RE = re.compile(r"^\s*[-*]\s*\[(✅|x|X)\]\s*.*\[review\]", re.M)
REVIEW_OPEN_RE = re.compile(r"^\s*[-*]\s*\[( |❓|!)\]\s*.*\[review\]", re.M)
# ckpt 헤딩 (regression_gate.CKPT_RE 와 같은 폭 — `fix.ckpt1` 류도 실빌드에 있다).
CKPT_HEAD_RE = re.compile(r"^###\s+([A-Za-z][A-Za-z0-9_-]*\.ckpt\d+)\b")


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


def _line_key(line):
    """체크박스 마크를 지운 정규화 텍스트 — 원본↔투영 사이 같은 줄을 잇는 키."""
    return re.sub(r"^(\s*[-*]\s*)\[(?:✅|x|X| |❓|!)\]", r"\1[]", line, count=1).strip()


def review_transitions(text, pairs, replace_all=False):
    """(closing, ckpts). 원본 text 에 편집을 투영한 뒤 **줄 단위**로 `[review]` 미완→완료
    전이를 찾는다 — 편집 조각(old/new)만 보면 불릿 없는 부분줄 편집이 `^[-*]` 앵커를
    비켜가 게이트를 통째로 우회한다 (반증 2026-09-10).

    closing: 전이 있음. ckpts: 전이 줄이 속한 ckpt id 집합 — 하나라도 못 정하면 None
    (= waiver 무효, 일반 검증으로). 투영 불가(text 비었거나 old 가 본문에 없음)면
    (None, None) — 호출자가 조각 기준 폴백(closes_review)을 쓴다. 순수 함수.

    보수 규칙 (전부 "면제 없음" 쪽으로 기운다):
      · 같은 텍스트의 미완 줄이 여럿인데 일부만 닫히면 어느 ckpt 인지 모름 → 미상
      · 같은 ckpt 헤딩이 둘이면(가짜 헤딩 삽입 스티어링) 그 ckpt → 미상
      · 원본 미완 줄과 짝이 안 맞는 완료 [review] 줄이 늘어나면(삭제+추가, 텍스트
        바꿔 닫기) 전이로 보되 ckpt 미상
    완료 줄을 고쳐 쓰기만 하는 편집(전이 없음)은 키에 넣지 않는다.
    """
    if not text:
        return None, None
    proj = text
    for old, new in pairs:
        if old is None:
            proj = new
            continue
        if old not in proj:
            return None, None
        proj = proj.replace(old, new) if replace_all else proj.replace(old, new, 1)

    heads = {}
    cur = None
    orig_open = {}      # key -> [ckpt or None, ...] (줄마다)
    orig_done_n = 0
    for line in text.splitlines():
        h = CKPT_HEAD_RE.match(line)
        if h:
            cur = h.group(1)
            heads[cur] = heads.get(cur, 0) + 1
            continue
        if REVIEW_OPEN_RE.match(line):
            orig_open.setdefault(_line_key(line), []).append(cur)
        elif REVIEW_DONE_RE.match(line):
            orig_done_n += 1
    proj_open, proj_done = {}, {}
    for line in proj.splitlines():
        if REVIEW_OPEN_RE.match(line):
            k = _line_key(line)
            proj_open[k] = proj_open.get(k, 0) + 1
        elif REVIEW_DONE_RE.match(line):
            k = _line_key(line)
            proj_done[k] = proj_done.get(k, 0) + 1

    closing, unknown, matched, ckpts = False, False, 0, set()
    for k, owners in orig_open.items():
        closed = len(owners) - proj_open.get(k, 0)
        done = proj_done.get(k, 0)
        if closed <= 0 or done <= 0:
            continue
        closing = True
        matched += min(closed, done)
        if closed < len(owners) or any(c is None or heads.get(c, 0) != 1 for c in owners):
            unknown = True
        else:
            ckpts.update(owners)
    if sum(proj_done.values()) - orig_done_n - matched > 0:
        closing, unknown = True, True
    if not closing:
        return False, None
    return True, (None if unknown else ckpts)


def _read_target(payload, path):
    """편집 대상 tasks.md 본문 (ckpt 역산용). 상대경로는 payload cwd 기준. 실패 = ''."""
    p = path
    if not os.path.isabs(p):
        p = os.path.join(str(payload.get("cwd") or ""), p)
    try:
        with open(p, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _waived(proj, ckpts):
    """ckpt 단위 waiver — 닫히는 [review] 줄이 속한 **모든** ckpt 에
    `<WAIVER_DIR>/<proj>/<ckpt-id>.waiver` 가 있을 때만 물러난다. ckpt 미상 = 면제 없음.
    (2026-09-10 Astra 감사 F5: 구 판정은 '폴더에 .waiver 하나라도' 였고 지우는 코드가
    없어 첫 waive 가 그 프로젝트의 리뷰게이트를 영구 해제했다.)"""
    if not ckpts:
        return False
    d = os.path.join(WAIVER_DIR, safe_key(proj))
    return all(os.path.isfile(os.path.join(d, safe_key(c) + ".waiver")) for c in ckpts)


def main():
    p = read_payload()
    ti = p.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("path") or ""

    if not _target_is_tasks_md(path):
        sys.exit(0)                      # 관심 대상 아님 — 조용히 통과 (감사 소음 방지)

    pairs = _edits(ti)
    closing, ckpts = review_transitions(_read_target(p, path), pairs,
                                        bool(ti.get("replace_all")))
    if closing is None:                  # 투영 불가 → 조각 기준 폴백 (waiver 는 무효)
        closing, ckpts = closes_review(pairs), None
    if not closing:
        sys.exit(0)                      # [review] 완료 전이가 아님

    proj = project_of(p)
    if _waived(proj, ckpts):
        allow(EVENT, p, reason="review waived for ckpt {} (waiver file)".format(
            ",".join(sorted(ckpts))))

    missing = codereview_missing(proj) + regression_missing(proj)
    if missing:
        block(EVENT, p,
              "`[review]` 완료 차단 ({}): {}\n"
              "이 게이트는 작업목록(task store) 사용 여부와 무관하게 tasks.md 편집에서 "
              "발동한다 (PROCESS §3 5.4). reviewer 를 실제로 dispatch 하고 회귀가 0 이 "
              "된 뒤 다시 체크하라.".format(proj, "; ".join(missing)))

    allow(EVENT, p, reason="tasks.md [review] 완료 — reviewer 호출 + 회귀 0 확인")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:                                   # FAIL OPEN
        audit(EVENT, {}, "allow", reason="hook error (fail-open): {}".format(e))
        sys.exit(0)
