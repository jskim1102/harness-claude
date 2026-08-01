#!/usr/bin/env python3
"""spec_overwrite_gate — 완성(분해된) 모듈의 spec/tasks 재분해 덮어쓰기를 결정론으로 막는다.

문제: 2단계 분해(plan.md → specs/spec.md + specs/tasks.md)는 **모듈당 1회**다. 그러나
`/start-project`·standard spawn-prompt 는 planner 에게 무조건 "specs 작성"을 지시한다.
tasks.md 에 완료 ckpt(`- [✅]`, 레거시 `- [x]`)가 쌓인 완성 모듈에 이걸 다시 돌리면
planner 의 Write 가 Done 이력·learnings 를 통째로 덮어써 파괴한다 — 모든 CTO 가 수정단계
진입 시 겪는 함정.
`start_project_gate` 는 spawn(TeamCreate) 만 게이트하고 이 downstream 덮어쓰기는 못 막는다.
role.md/spawn-prompt 의 "분해 스킵" 안내는 advisory 라 샌다. 이 훅이 결정론으로 막는다
(git_guard 와 같은 철학).

게이트:
  - PreToolUse(Write): file_path 가 `specs/spec.md` | `specs/tasks.md` 이고, 형제
    `specs/tasks.md` 가 이미 완료 ckpt(`- [✅]`)를 담고 있으면 = 분해된 모듈 →
    전체 덮어쓰기(Write)는 재분해로 간주하고 차단.
  - PreToolUse(Bash): 같은 파괴를 셸 리다이렉트로 하는 경로 (`cat > specs/tasks.md`,
    `... | tee specs/spec.md`). Write 만 보던 시절엔 무방비였고 git_guard 에도
    리다이렉트 규칙이 없어 Done 이력이 게이트 없이 날아갔다 (2026-07-23 감사).
    "heredoc 이 빠르니까" 가 정확히 이 훅이 존재하는 합리화 경로다.
  - 수정작업은 Edit(수술적 append/수정)로 하라 → Edit 는 이 훅을 안 탄다(Write 만 본다).
  - 진짜 재분해가 필요하면 사용자 승인 하에 기존 specs/tasks.md 를 먼저 치우면
    (rm/rename) 파일 부재 → 통과.

Bash 검사는 **일부러 좁다** — 리터럴 basename 2개 + non-append(`>`/`tee`, `>>`·
`tee -a` 제외). 넓히면 lead-unavailable.md 의 정당한
`cat >> specs/pending-user-questions.md` append 워크플로가 깨진다. 남는 우회
(`sed -i`, `mv` 덮어쓰기, cd 체인)는 의도적 fail-open 범위다 — git_guard 와 같은
anti-합리화 위협모델이지 샌드박스가 아니다.

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block  # noqa: E402

GUARDED = ("spec.md", "tasks.md")

# 셸 truncating 리다이렉트 → specs/{spec,tasks}.md.
#   `> specs/tasks.md` / `>specs/tasks.md` / `1> …`  (append `>>` 는 제외)
#   `tee specs/spec.md`                              (append `tee -a` 는 제외)
# 경로 앞부분은 자유(`../m/specs/tasks.md`), 반드시 `specs/` 바로 아래여야 한다.
_SPECS_TAIL = r"[^\s;&|<>]*specs/(?:spec|tasks)\.md(?![\w.-])"
REDIRECT_RE = re.compile(rf"(?<!>)>\s*{_SPECS_TAIL}")
TEE_RE = re.compile(rf"\btee\b(?!\s+(?:-a\b|--append\b))[^;&|\n]*?{_SPECS_TAIL}")

# 완료 ckpt 마커 = 정본 `[✅]` (레거시 `[x]`/`[X]` 도 인식) — cto_statusline.py 의
# box_re 와 같은 done 집합. `[ ]`(미완)·`[❓]`/`[!]`(블로커) 는 Done 아님.
DONE_RE = re.compile(r"^\s*[-*]\s*\[(?:✅|x|X)\]", re.M)


def _tool_input(payload):
    return payload.get("tool_input") or payload.get("toolInput") or {}


def _is_guarded_spec(path):
    """True iff path is .../specs/spec.md or .../specs/tasks.md."""
    if not path:
        return False
    parent, base = os.path.split(os.path.normpath(path))
    return base in GUARDED and os.path.basename(parent) == "specs"


def _tasks_has_done(specs_dir):
    """True iff specs/tasks.md exists and has >=1 완료 ckpt (`- [✅]`/`- [x]`)."""
    try:
        with open(os.path.join(specs_dir, "tasks.md"), encoding="utf-8") as fh:
            return bool(DONE_RE.search(fh.read()))
    except Exception:
        return False


def _redirect_target(cmd):
    """셸 리다이렉트/tee 로 덮어쓰려는 specs 파일 경로. 없으면 None."""
    for rx in (REDIRECT_RE, TEE_RE):
        m = rx.search(cmd or "")
        if m:
            tail = re.search(_SPECS_TAIL, m.group(0))
            if tail:
                return tail.group(0)
    return None


def main():
    payload = read_payload()
    tool = payload.get("tool_name") or payload.get("toolName") or ""
    ti = _tool_input(payload)

    if tool == "Bash":
        # 같은 파괴의 셸 경로. 대상 파일이 실존하고 Done ckpt 가 있을 때만 막는다
        # (fresh 분해는 리다이렉트로 써도 파괴할 이력이 없다).
        target = _redirect_target(ti.get("command") or "")
        if not target:
            allow()
        specs_dir = os.path.dirname(os.path.normpath(target))
        if not _tasks_has_done(specs_dir):
            allow()
        block(
            "PreToolUse", payload,
            "재분해 차단 — 셸 리다이렉트로 specs 덮어쓰기 시도 "
            f"({target}). 형제 specs/tasks.md 에 완료 ckpt(- [✅]) 존재 = 이미 분해된 모듈.\n"
            "`cat > …` / `tee …` 는 Write 와 똑같이 Done 이력·learnings 를 파괴한다.\n"
            "수정작업이면 Edit 로 append 하라. append 리다이렉트(`>>`)는 이 게이트를 안 탄다.\n"
            "진짜 재분해가 필요하면 사용자 승인 하에 기존 specs/tasks.md 를 먼저 치우고(rm/rename) 다시 시도.",
        )

    if tool != "Write":
        allow()

    path = ti.get("file_path") or ti.get("filePath") or ""
    if not _is_guarded_spec(path):
        allow()

    specs_dir = os.path.dirname(os.path.normpath(path))
    # 형제 tasks.md 에 완료 ckpt 가 없으면 = fresh/진행중 분해 → 통과.
    if not _tasks_has_done(specs_dir):
        allow()

    # 완료 ckpt(- [✅]) 있는 분해된 모듈에 대한 Write 전체덮어쓰기 = 재분해 → 차단.
    block(
        "PreToolUse", payload,
        "재분해 차단 — specs/tasks.md 에 완료 ckpt(- [✅]) 존재 = 이미 분해된 모듈.\n"
        f"Write 전체덮어쓰기({os.path.basename(path)})는 Done 이력·learnings 를 파괴한다.\n"
        "수정작업이면 Edit 로 기존 specs/tasks.md 에 [dev]/[review] fix 태스크를 append 하라 (재분해 X).\n"
        "진짜 재분해가 필요하면 사용자 승인 하에 기존 specs/tasks.md 를 먼저 치우고(rm/rename) 다시 시도.",
    )


if __name__ == "__main__":
    main()
