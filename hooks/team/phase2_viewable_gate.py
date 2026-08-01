#!/usr/bin/env python3
"""phase2_viewable_gate — phase2 가 사용자-검수 가능(dev 서버 + mock)한지 결정론으로 강제.

문제: PROCESS §2 는 phase2 END 에서 **프론트 dev 서버 기동**(0.0.0.0/FRONTEND_PORT) +
백엔드 없이 핵심 UI 가 보이도록 **mock/local-state**(dev-only `?mock` 가드 등) 를 내장해
게이트2(사용자 시각 검수) 를 phase3 진입 **전** 성립시키라고 **의무화**한다. dev 서버를
phase3 로 미루면 게이트2 가 빈 껍데기가 된다. 그러나 이 규칙은 advisory 라 샜다 —
rtsp-keypoint planner 가 phase2 를 compile-only(tsc+build) 로 두고 "dev 서버 기동" 을
phase3.ckpt1 로, 게이트2 를 phase3.ckpt5 로 미뤄 위반.

게이트 (PreToolUse Write, `specs/tasks.md` 한정):
  차단 = 분해 완료(`## phase3` 존재)면서
    (a) phase3+ 에 dev-server-start 태스크가 있고
    (b) phase2 에는 dev-server-start 태스크가 **없다** (= dev 서버를 phase3 로 미룸)
  = "compile-only phase2 + dev 서버를 phase3 로 미룸" → phase2 끝에 접속할 서버가 없음.

허용(보수적 — false-positive 회피):
  - `## phase3` 없음 = stub/부분작성 → 통과.
  - phase3+ 에 dev-server-start 토큰 없음(예: cam-distance/rtsp-streaming 는 phase3.ckpt1 이
    `compose up -d`) → 판정 대상 아님 → 통과.
  - phase2 에 dev-server-start 토큰 있음 = 준수(접속 가능) → 통과.
  애매하면 통과 — 명확한 위반만 hard-block.
  (mock/local-state 는 게이트 조건 아님 — 데이터-게이트 UI 조건부라 판별 불가, planner.md/PROCESS §2 로만 강제.)

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block  # noqa: E402

# dev-server-start 토큰 — 프론트 dev 서버(또는 dev.sh 러너) 기동 태스크 신호.
DEV_SERVER_TOKENS = ("dev 서버 기동", "dev.sh up", "vite dev", "npm run dev")

# 최상위 `##` 헤더 전체(`### ...` ckpt 헤더 제외). 섹션 경계는 **모든** 최상위 헤더에서
# 끊어야 한다 — 그래야 phase 섹션이 뒤따르는 `## Maintenance`/`## 유지보수`/`## CEO order`
# (완성 후 fix·문서수정 — dev.sh 등 토큰이 섞임)을 삼키지 않는다.
TOP_HDR = re.compile(r"^##(?!#)[^\n]*", re.M)
PHASE_HDR = re.compile(r"^##\s*phase(\d+)\b")


def _tool_input(payload):
    return payload.get("tool_input") or payload.get("toolInput") or {}


def _is_tasks_md(path):
    """True iff path is .../specs/tasks.md."""
    if not path:
        return False
    parent, base = os.path.split(os.path.normpath(path))
    return base == "tasks.md" and os.path.basename(parent) == "specs"


def _phase_sections(text):
    """{phase_number: section_text}. A phase section runs from its `## phaseN`
    header to the NEXT top-level `##` header of ANY kind (so post-build
    Maintenance/fix/order sections stay out of the phase slices)."""
    tops = list(TOP_HDR.finditer(text))
    sections = {}
    for i, m in enumerate(tops):
        pm = PHASE_HDR.match(m.group(0))
        if not pm:
            continue
        num = int(pm.group(1))
        start = m.start()
        end = tops[i + 1].start() if i + 1 < len(tops) else len(text)
        sections[num] = sections.get(num, "") + text[start:end]
    return sections


def _has_token(text, tokens):
    return any(tok in text for tok in tokens)


def main():
    payload = read_payload()
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if tool != "Write":
        allow()

    ti = _tool_input(payload)
    path = ti.get("file_path") or ti.get("filePath") or ""
    if not _is_tasks_md(path):
        allow()

    content = ti.get("content") or ti.get("file_text") or ""
    sections = _phase_sections(content)

    # 분해 미완(phase3 없음) = stub/부분작성 → 통과.
    if 3 not in sections or 2 not in sections:
        allow()

    phase2 = sections[2]
    later = "".join(t for n, t in sections.items() if n >= 3)

    # phase3+ 에 dev-server-start 태스크가 없으면(compose 기반 등) 판정 대상 아님 → 통과.
    if not _has_token(later, DEV_SERVER_TOKENS):
        allow()

    # phase2 에 dev-server-start 태스크가 있으면 = 준수(접속 가능) → 통과.
    # mock/local-state 는 게이트 조건이 아님 — 데이터-게이트 UI 조건부라 훅이 판별 불가,
    # planner.md/PROCESS §2 로만 강제(soft). dev 서버(접속=보편)만 hard.
    if _has_token(phase2, DEV_SERVER_TOKENS):
        allow()

    # 명확한 위반: compile-only phase2 + dev 서버를 phase3 로 미룸 → 차단.
    block(
        "PreToolUse", payload,
        "phase2-viewable 위반 차단 (PROCESS §2) — phase2 가 compile-only 이고 dev 서버 기동이 phase3+ 로 밀렸다.\n"
        "PROCESS §2 는 phase2 END 에서 (a) 프론트 dev 서버 기동(0.0.0.0/FRONTEND_PORT, vite dev/dev.sh up),\n"
        "(b) 백엔드 없이 핵심 UI 가 보이도록 mock/local-state(예: dev-only `?mock` 가드) 내장,\n"
        "(c) 게이트2(사용자 시각 검수) 를 phase3 진입 전 성립 — 을 의무화한다. dev 서버를 phase3 로 미루지 말 것.\n"
        "→ tasks.md 를 고쳐라: dev 서버 기동 태스크 + mock/local-state 검수경로를 phase2 마지막 ckpt 로 옮기고,\n"
        "  게이트2 를 phase2 종료 시점에 둔다(phase3.ckptN 아님). 그런 뒤 다시 Write.",
    )


if __name__ == "__main__":
    main()
