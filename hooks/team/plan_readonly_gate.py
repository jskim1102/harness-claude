#!/usr/bin/env python3
"""plan_readonly_gate — 빌드 루트 `plan.md` 를 CTO 세션에서 읽기전용으로 강제한다.

문제: `plan.md` 는 **CEO 산출물**이다 (1단계 /build-project·/build-module 이
작성하고, add-cto 는 그게 이미 있어야 스폰한다 — run.sh `_build_ready`).
CTO 쪽엔 정당한 plan.md 쓰기 경로가 없다: 계획-현실 괴리는 planner 가
`specs/spec.md`+`specs/tasks.md` 를 고쳐서, 계획 자체의 의문은 `## 6 Open
Questions` 를 **사용자에게 질문**해서(harness-relay-qa `[user-q]`/`[user-a]`)
푼다. 그런데 이 규칙은 role.md:60 의 prose 뿐이라 advisory 로 샌다
(spec_overwrite_gate·phase2_viewable_gate 와 같은 클래스 — "advisory 라 샜다,
결정론으로 막는다"). 이 훅이 결정론 게이트로 막는다.

게이트:
  - PreToolUse(Write|Edit|MultiEdit): file_path 의 basename 이 `plan.md` 이고 그
    위치가 빌드 루트(`claude-project/<name>/` 또는 `modules/<name>/`)면 차단.
  - lead·teammate 둘 다 대상 (teammate 도 CEO 산출물을 고칠 권한이 없다).
  - `specs/plan.md` 같은 하위 경로·다른 이름은 무관 → 통과.

스코프: 이 훅은 CTO project settings.json 에만 배선된다 (run.sh 의 cto 분기).
CEO 세션 템플릿엔 Write/Edit matcher 자체가 없어 CEO 의 plan.md 작성은
구조적으로 영향받지 않는다.

알려진 fail-open 범위(의도적): Bash 경유 쓰기(`cat > plan.md`), codex 세션,
settings 재생성 전의 기존 세션. 기존 게이트들과 같은 posture 다.

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block  # noqa: E402

# 빌드 루트의 부모 디렉토리명 (run.sh add-cto 가 하드에러로 강제하는 두 가지).
BUILD_BASES = ("claude-project", "modules")


def _tool_input(payload):
    return payload.get("tool_input") or payload.get("toolInput") or {}


def _is_build_root_plan(path: str) -> bool:
    """True iff path is <claude-project|modules>/<name>/plan.md.

    루트 한정 — `specs/plan.md` 같은 중첩 plan.md 는 대상 아님(오탐 방지).
    """
    if not path:
        return False
    norm = os.path.normpath(path)
    parent, base = os.path.split(norm)
    if base != "plan.md":
        return False
    grandparent = os.path.dirname(parent)          # .../<claude-project|modules>
    return os.path.basename(grandparent) in BUILD_BASES


def main():
    payload = read_payload()
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    # MultiEdit 도 file_path 로 같은 파일을 쓴다 — 빠뜨리면 그대로 우회로다
    # (공식 security-guidance 플러그인도 Edit|Write|MultiEdit 를 함께 건다).
    if tool not in ("Write", "Edit", "MultiEdit"):
        allow()

    ti = _tool_input(payload)
    path = ti.get("file_path") or ti.get("filePath") or ""
    if not _is_build_root_plan(path):
        allow()

    block(
        "PreToolUse", payload,
        "plan.md 쓰기 차단 — plan.md 는 CEO 산출물이다 (읽기 전용).\n"
        "계획에 의문이 있으면 ## 6 Open Questions 를 **사용자에게 질문**으로 올려라 "
        "(그 섹션에 직접 쓰라는 뜻이 아니다 — 이 게이트가 그것도 막는다).\n"
        "계획과 현실이 어긋나면 CTO 가 specs/spec.md·specs/tasks.md 를 갱신한다 "
        "(재분해 규모면 사용자에게 — planner 는 사용자 명시 지시 시만, RULES §17). "
        "plan.md 자체의 변경은 CEO 몫이다.",
    )


if __name__ == "__main__":
    main()
