#!/usr/bin/env python3
"""plan_readonly_gate — 빌드 루트 `plan.md` 의 쓰기 주체와 잠금을 결정론으로 강제한다.

2026-10-15 역할 재분할: `plan.md` 는 **CTO lead 가 계획 단계에 사용자와 쓴다** (예전엔
CEO 산출물이었고 이 게이트는 "무조건 읽기전용" 이었다). 그래서 게이트는 "초안이면
lead 만 쓰기, 확정되면 잠금" 으로 바뀐다. 잠금이 없으면 만들다가 계획을 결과에
맞춰 고친다 — 이 게이트가 생긴 이유는 그대로다. role.md 의 prose 는 advisory 라
샌다(spec_overwrite_gate·phase2_viewable_gate 와 같은 클래스) — 여기서 결정론으로 막는다.

상태 = 초안 마커 유무: `~/.claude/logs/plan-draft/<name>.draft`
  - 있음 = 초안. lead(`HARNESS_ROLE=cto:<name>`, transcript 가 `/subagents/` 아님)가
    **자기 빌드**의 plan.md 를 Write/Edit/MultiEdit 할 수 있다.
  - 없음 = 잠금. 차단. **기존 빌드는 마커가 없으니 그대로 잠금 (이관 0).**
  - 마커를 만드는 곳: `run.sh add-cto` (빈 폴더 = 새 빌드), "plan.md 수정할까요?" 승인.
  - 마커를 지우는 곳: "plan.md 확정할까요?" 승인.

게이트:
  - PreToolUse(Write|Edit|MultiEdit): file_path 가 `<claude-project|modules>/<name>/plan.md`
    이고 (초안 ∧ lead ∧ 자기 빌드) 가 아니면 차단. planner·reviewer(`/subagents/`)·
    designer-cto 는 초안이어도 차단. `specs/plan.md` 같은 하위 경로·다른 이름은 통과.
  - UserPromptSubmit: 직전 CTO 메시지가
      "plan.md 확정할까" + 승인 답 → 확정: plan.md 실존 확인 → 초안 마커 삭제 →
        팀이 아직 없으면(spawn claim 없음) 시작 마커(start_project_gate._start — 팀 스폰
        신호 + claim 정리), 이미 떠 있으면(재확정) 건드리지 않음 → 카메라 포트 배선
        (run.sh `_wire_project_env`, 멱등) → stdout 1줄(이 턴의 컨텍스트).
      "plan.md 수정할까" + 승인 답 → 초안 마커 생성(잠금 해제) → stdout 1줄.
    승인 답 = 공유 긍정어(team_hook_common.approves — reviewer 스폰 승인과 같은 장치)
    또는 질문 전용 동사(확정 질문엔 `확정*`, 수정 질문엔 `수정*`). **반대 동사로 시작하면
    무효** — "확정할까요?" 에 "수정해" 는 거절이지 확정이 아니다. 다른 질문의 "응" 은
    무효. 빌드 dir = payload cwd (lead 의 cwd = 빌드 dir). 절대 exit 2 하지 않는다.

스코프: CTO project settings.json 에만 배선 (run.sh 의 cto 분기: Write|Edit|MultiEdit
매처 + UserPromptSubmit). CEO 템플릿엔 없다. Claude Code 는 훅 배선을 기동 시
스냅샷하므로 settings 재생성 전부터 돌던 세션은 UserPromptSubmit 쪽이 없다 —
차단 메시지가 재기동(stop-cto → add-cto, 대화 유지) 안내를 포함하는 이유.

알려진 fail-open 범위(의도적): Bash 경유 쓰기(`cat > plan.md`), codex 세션,
settings 재생성 전의 기존 세션. 기존 게이트들과 같은 posture 다.

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import (  # noqa: E402
    read_payload, allow, block, LOG_DIR, safe_key, repo_root, approves, last_assistant_text, NO_RE,
)
from start_project_gate import _start  # noqa: E402  (시작 마커 + claim 정리 — 구현 하나)

# 빌드 루트의 부모 디렉토리명 (run.sh add-cto 가 하드에러로 강제하는 두 가지).
BUILD_BASES = ("claude-project", "modules")
DRAFT_DIR = os.path.join(LOG_DIR, "plan-draft")
# one_teammate_per_role_gate 가 spawn 시 쓰는 claim — "이 lead 세션에서 팀이 떴다" 의 정본.
# add-cto 와 _start 가 지우므로 세션 범위 신호다 (start_project_gate.CLAIMS_DIR 와 동일).
CLAIMS_DIR = os.path.expanduser("~/.harness-claude/orca-team-spawn-claims")
# 모델은 파일명만 백틱/볼드로 감싸고("`plan.md` 확정할까요?") 동사를 띄우기도 한다("확정 할까요").
ASK_CONFIRM_RE = re.compile(r"plan\.md[`*\s]*(를|을)?[`*\s]*확정\s*할까")
ASK_EDIT_RE = re.compile(r"plan\.md[`*\s]*(를|을)?[`*\s]*수정\s*할까")


def _note(msg):
    """훅이 제 일을 못 한 사실을 stderr 로 표면화한다 (exit code 불변)."""
    try:
        print(f"[plan_readonly_gate] {msg}", file=sys.stderr)
    except Exception:
        pass


def _cto_name():
    role = os.environ.get("HARNESS_ROLE", "")
    return role.split(":", 1)[1] if role.startswith("cto:") else ""


def draft_marker(name):
    return os.path.join(DRAFT_DIR, safe_key(name) + ".draft")


def _tool_input(payload):
    return payload.get("tool_input") or payload.get("toolInput") or {}


def _build_root_plan_name(path):
    """path 가 <claude-project|modules>/<name>/plan.md 이면 <name>, 아니면 None.

    루트 한정 — `specs/plan.md` 같은 중첩 plan.md 는 대상 아님(오탐 방지).
    """
    if not path:
        return None
    norm = os.path.normpath(path)
    parent, base = os.path.split(norm)
    if base != "plan.md":
        return None
    grandparent = os.path.dirname(parent)          # .../<claude-project|modules>
    if os.path.basename(grandparent) not in BUILD_BASES:
        return None
    return os.path.basename(parent)


def _build_dir(payload):
    """payload cwd 가 <…>/<claude-project|modules>/<name> 이면 그 경로."""
    cwd = str(payload.get("cwd") or "")
    if cwd and os.path.basename(os.path.dirname(cwd)) in BUILD_BASES and os.path.isdir(cwd):
        return cwd
    return ""


def _first_word(prompt):
    p = (prompt or "").strip()
    return re.split(r"[\s,.!?~]+", p.lower())[0] if p else ""


def _answer_ok(prompt, yes_prefix, veto_prefix):
    """질문별 승인 판정 — 공유 긍정어(approves) 또는 질문 전용 동사.

    반대 동사로 시작하면 무조건 무효: "plan.md 확정할까요?" 에 "수정해" 는 정반대
    전이 요청이다 (리뷰 2026-10-15 F1). 전용 동사는 공유 YES_WORDS 에 넣지 않는다 —
    넣으면 reviewer 스폰 질문에 "수정해" 가 스폰 승인으로 샌다.
    """
    p = (prompt or "").strip()
    first = _first_word(p)
    if not first or first.startswith(veto_prefix):
        return False
    if approves(p):
        return True
    return first.startswith(yes_prefix) and len(p) <= 40 and not NO_RE.search(p)


def _team_alive(name):
    """이 lead 세션에서 planner/reviewer 가 이미 떴는가 (spawn claim 존재)."""
    d = os.path.join(CLAIMS_DIR, safe_key(name))
    return any(os.path.exists(os.path.join(d, r + ".claimed")) for r in ("planner", "reviewer"))


def _wire_ports(build_dir):
    """카메라 포트 배선 — run.sh 의 _wire_project_env 를 그대로 쓴다 (구현 하나, 멱등).

    run.sh 는 맨 아래 dispatch `case "${1:-}"` 가 있어 source 할 때 위치 인자를 비워야
    한다(`set --`) — 아니면 bash -c 의 인자가 서브커맨드로 읽혀 'unknown command' 로 죽는다.
    """
    run_sh = os.path.join(repo_root(), "run.sh")
    try:
        r = subprocess.run(
            ["bash", "-c", 'r="$1"; b="$2"; set --; source "$r" >/dev/null 2>&1; _wire_project_env "$b"',
             "_", run_sh, build_dir],
            check=False, timeout=30, capture_output=True, text=True,
        )
        if r.returncode != 0:
            _note(f"카메라 포트 배선 실패 (exit {r.returncode}) — 수동: .env 의 MEDIAMTX_* 확인 "
                  f"(add-cto 재실행도 같은 함수를 멱등으로 다시 부른다)")
    except Exception as exc:
        _note(f"카메라 포트 배선 실패 ({type(exc).__name__}: {exc}) — 수동: .env 의 MEDIAMTX_* 확인")


def _on_prompt(payload, name):
    prompt = payload.get("prompt") or payload.get("user_prompt") or ""
    first = _first_word(prompt)
    # transcript 읽기는 승인 후보일 때만 (매 프롬프트 1MB tail 읽기 방지).
    if not (approves(prompt) or first.startswith(("확정", "수정"))):
        return
    path = payload.get("transcript_path") or payload.get("transcriptPath") or ""
    try:
        asked = last_assistant_text(path) if path else ""
    except Exception as exc:
        _note(f"승인 판정 실패 ({type(exc).__name__}: {exc})")
        return
    marker = draft_marker(name)
    if ASK_CONFIRM_RE.search(asked):
        if not _answer_ok(prompt, "확정", "수정"):
            return
        build_dir = _build_dir(payload)
        if not build_dir or not os.path.isfile(os.path.join(build_dir, "plan.md")):
            _note("확정 무시 — plan.md 가 없다 (먼저 plan.md 를 쓰고 다시 물어라)")
            return
        if not os.path.exists(marker):
            _note("확정 무시 — 초안 상태가 아니다 (이미 잠김)")
            return
        try:
            os.remove(marker)
        except Exception as exc:
            _note(f"초안 마커 삭제 실패 ({type(exc).__name__}: {exc}) — plan.md 가 잠기지 않았다")
            return
        if _team_alive(name):
            # 재확정 (수정 → 재확정): 팀은 이미 떠 있다. 시작 마커를 다시 심으면 claim 정리 →
            # one_teammate_per_role 통과 → 중복 스폰, tasks.md 가 있으면 planner_dispatch_gate
            # 와 "스폰하라/안 된다" 훅 모순 (2026-08-20 annodock 클래스). 건드리지 않는다.
            print("[plan_readonly_gate] plan.md 재확정 — 잠금. 팀(planner·reviewer)은 이미 떠 있다 — "
                  "재스폰 X, 바뀐 계획을 specs/spec.md·specs/tasks.md 에 반영하는 쪽으로 이어간다. "
                  "카메라 빌드면 .env 의 MEDIAMTX_* 는 유지/보충됐다.")
        else:
            _start(name)
            print("[plan_readonly_gate] plan.md 확정 — 잠금 + 시작 마커 기록. 이 턴에 팀(planner·reviewer)을 "
                  "스폰하고 사용자의 분해 지시를 기다린다. 카메라 빌드면 .env 에 MEDIAMTX_* 4줄이 들어갔다.")
        _wire_ports(build_dir)
    elif ASK_EDIT_RE.search(asked):
        if not _answer_ok(prompt, "수정", "확정"):
            return
        try:
            os.makedirs(DRAFT_DIR, exist_ok=True)
            with open(marker, "w") as fh:
                fh.write(name + "\n")
        except Exception as exc:
            _note(f"초안 마커 생성 실패 ({type(exc).__name__}: {exc}) — plan.md 는 여전히 잠김")
            return
        print("[plan_readonly_gate] plan.md 수정 승인 — 잠금 해제(초안). 수정 후 다시 "
              "'plan.md 확정할까요?' 로 묻는다.")


def main():
    payload = read_payload()
    event = payload.get("hook_event_name") or payload.get("hookEventName") or ""
    name = _cto_name()

    if event == "UserPromptSubmit":
        if name:
            try:
                _on_prompt(payload, name)
            except Exception as exc:
                _note(f"UserPromptSubmit 처리 실패 ({type(exc).__name__}: {exc})")
        allow()  # 입력 게이트 아님 — 절대 차단하지 않는다

    tool = payload.get("tool_name") or payload.get("toolName") or ""
    # MultiEdit 도 file_path 로 같은 파일을 쓴다 — 빠뜨리면 그대로 우회로다
    # (공식 security-guidance 플러그인도 Edit|Write|MultiEdit 를 함께 건다).
    if tool not in ("Write", "Edit", "MultiEdit"):
        allow()

    ti = _tool_input(payload)
    target = _build_root_plan_name(ti.get("file_path") or ti.get("filePath") or "")
    if target is None:
        allow()

    tp = payload.get("transcript_path") or payload.get("transcriptPath") or ""
    is_lead = bool(name) and "/subagents/" not in tp
    if is_lead and target == name and os.path.exists(draft_marker(name)):
        allow("PreToolUse", payload, reason="plan.md 초안 — lead 쓰기 허용")

    if is_lead and target == name:
        why = ("plan.md 잠김 (확정됨). 계획을 바꿔야 하면 이유 한 줄 + 'plan.md 수정할까요?' 로 "
               "사용자에게 묻고 턴을 끝내라 — 승인 답이 잠금을 푼다. 계획-현실 괴리는 "
               "specs/spec.md·specs/tasks.md 갱신으로 (재분해 규모면 사용자에게 — RULES §17). "
               f"승인 뒤에도 잠금이 안 풀리면 이 세션이 settings 재생성 전(구 배선)이다 — 사용자에게 "
               f"`./run.sh stop-cto {name}` → `./run.sh add-cto {name}` 재기동(대화 유지)을 안내하라.")
    elif is_lead:
        why = f"plan.md 쓰기 차단 — 남의 빌드({target})다. 네 빌드는 {name}."
    else:
        why = ("plan.md 쓰기 차단 — plan.md 는 lead CTO 가 계획 단계에 쓰고 확정 후 잠근다. "
               "teammate·designer 는 쓰지 않는다. 계획에 의문이 있으면 ## 6 Open Questions 를 "
               "사용자에게 질문으로 올려라 (harness-relay-qa) — 그 섹션에 직접 쓰라는 뜻이 아니다.")
    block("PreToolUse", payload, why)


if __name__ == "__main__":
    main()
