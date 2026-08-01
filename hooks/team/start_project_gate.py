#!/usr/bin/env python3
"""start_project_gate — CTO 팀 spawn 을 /start-project 신호에 결정론으로 묶는다.

설계 의도: `add-cto` 는 CTO 를 빈 세션으로 띄우고, 사용자가 `/model`·`/effort` 를
고른 뒤 `/start-project` 로 **명시 시작**하게 돼 있다. 그러나 stray 턴 한 번이면
(예: bypass-accept 키입력 누수 — run.sh start_session) Opus CTO 가 plan.md 를 보고
`Agent` tool 로 Claude 팀원(planner/designer/reviewer)을 자동 스폰해 /effort 설정
창을 놓친다. role.md "자동스폰 금지" 는 advisory 라 샌다. 이 훅이 결정론 게이트로 막는다
(RULES §5.3/netbind 와 같은 철학). 팀 spawn 은 이 환경에선 `TeamCreate` 가 아니라
`Agent` tool(subagent_type=팀역할) 이다 — 게이트도 `Agent` 를 겨눈다.

게이트:
  - UserPromptSubmit: 프롬프트에 `/start-project` 가 있으면 마커를 write
    (이 마커는 이 게이트 + 새 Stop-hook 가 함께 소비한다 — 브랜치 불변).
  - PreToolUse(Agent): LEAD 레벨(transcript_path 에 `/subagents/` 없음) 호출이고
    subagent_type ∈ {planner,designer,reviewer} 인데 /start-project 마커가
    **없으면** 차단(=premature team spawn — /start-project 가 명시 spawn 신호다).
    nested(`/subagents/`) 호출·비-팀역할 subagent_type·마커 존재 → 허용.
  - 마커 리셋: `run.sh add-cto` 가 spawn 시 마커를 지운다(fresh 마다 재요구).
    2026-07-23 까지 이건 **문서에만 있고 구현이 없었다** — run.sh 는
    `LOG_DIR/started/` 를 건드린 적이 없어서, 중도 실패한 이전 스폰의 stale
    마커가 살아남으면 다음 add-cto 가 `/start-project` 없이도 팀을 뽑을 수 있었다
    (게이트의 존재 이유인 `/model`·`/effort` 창을 조용히 무력화). 유일한 clearer
    였던 start_project_spawn_nudge 는 3-Claude+Codex 로스터가 **완성돼야만**
    지우고 giveup 경로는 마커를 남긴 채 fail-open 했다. 이제 run.sh 가 실제로 지운다.

정당 spawn 경로 보존: fresh/maintenance 둘 다 /start-project=마커 후 3팀원 upfront spawn /
팀원 내부 병렬=nested subagent(`/subagents/` → 게이트 안 탐).

one_teammate_per_role_gate 와 같은 `Agent` matcher 아래 공존한다(둘 다 통과해야 함):
이 게이트는 시작 마커를, 저 게이트는 역할별 원자 spawn claim 을 본다.

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import read_payload, allow, block, LOG_DIR  # noqa: E402

STARTED_DIR = os.path.join(LOG_DIR, "started")
TEAM_ROLES = ("planner", "designer", "reviewer")
CLAIMS_DIR = os.path.expanduser("~/.harness-claude/orca-team-spawn-claims")


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", s or "")


def _cto_name() -> str:
    role = os.environ.get("HARNESS_ROLE", "")
    return role.split(":", 1)[1] if ":" in role else role


def _marker_path(name: str) -> str:
    return os.path.join(STARTED_DIR, _safe(name) + ".started")


def _note(msg: str) -> None:
    """훅이 제 일을 못 한 사실을 stderr 로 표면화한다 (exit code 불변).

    audit() 는 같은 LOG_DIR 을 쓰므로 그게 안 될 때 유일한 채널이다.
    로그가 터져도 훅을 깨면 안 되니 이중 try.
    """
    try:
        print(f"[start_project_gate] {msg}", file=sys.stderr)
    except Exception:
        pass


def main() -> None:
    payload = read_payload()
    role = os.environ.get("HARNESS_ROLE", "")
    # CTO 세션 외(예: CEO)엔 무관 — 무조건 통과.
    if not role.startswith("cto"):
        allow()

    event = payload.get("hook_event_name") or payload.get("hookEventName") or ""
    name = _cto_name()

    if event == "UserPromptSubmit":
        prompt = payload.get("prompt") or payload.get("user_prompt") or ""
        if re.search(r"(^|\s)/start-project(\s|$)", prompt):
            try:
                os.makedirs(STARTED_DIR, exist_ok=True)
                with open(_marker_path(name), "w") as fh:
                    fh.write(name + "\n")
            except Exception as exc:
                # 마커 write 실패를 삼키면 fail-open 이 아니라 **fail-closed 로
                # 뒤집힌다**: 사용자가 /start-project 를 했는데도 이후 모든 spawn 이
                # "/start-project 전입니다" 라는 거짓 이유로 막히고, 재시도해도
                # 같은 write 가 계속 실패해 빠져나갈 수 없다. 같은 unwritable
                # LOG_DIR 이 audit() 도 죽이므로 원인이 이중으로 숨는다 → stderr 로
                # 표면화한다. (UserPromptSubmit 는 절대 exit 2 하지 않는다.)
                _note(f"/start-project 마커 기록 실패 ({type(exc).__name__}: {exc}) "
                      f"— 경로 {_marker_path(name)}. 이대로면 팀 spawn 이 "
                      f"'/start-project 전입니다' 로 잘못 차단된다.")
            # New explicit start signal = a new top-level spawn attempt.
            # Remove only this CTO's three harness-owned claim files.
            # (마커 write 와 분리 — 위가 실패해도 claim 정리는 따로 시도한다.)
            for teammate_role in TEAM_ROLES:
                try:
                    os.unlink(os.path.join(CLAIMS_DIR, _safe(name), teammate_role + ".claimed"))
                except FileNotFoundError:
                    pass
                except Exception as exc:
                    _note(f"spawn claim 정리 실패 ({teammate_role}): "
                          f"{type(exc).__name__}: {exc}")
        allow()  # UserPromptSubmit 는 절대 차단하지 않음 (입력 게이트 아님)

    if event == "PreToolUse":
        tool = payload.get("tool_name") or payload.get("toolName") or ""
        if tool != "Agent":
            allow()
        # 팀원의 nested subagent(paneless 병렬 fan-out) — 절대 막지 않는다.
        tp = payload.get("transcript_path") or payload.get("transcriptPath") or ""
        if "/subagents/" in tp:
            allow()
        tool_input = payload.get("tool_input") or payload.get("toolInput") or {}
        st = (tool_input.get("subagent_type") or tool_input.get("subagentType") or "").strip()
        if st not in TEAM_ROLES:
            allow()  # general-purpose 등 비-팀역할 → 게이트 무관
        if os.path.exists(_marker_path(name)):
            allow(event, payload, reason="start-project marker 존재")
        block(
            event, payload,
            "팀 spawn 차단 — /start-project 전입니다.\n"
            "attach 후 /model·/effort 설정 → /start-project 로 시작하세요 "
            "(CTO 자동스폰 금지 — role.md '무엇을 직접 하면 안 되는가'). "
            "/start-project 가 명시 spawn 신호이며 "
            "fresh·maintenance 둘 다 그때 planner/designer/reviewer 3명을 upfront 로 스폰합니다.",
        )

    allow()


if __name__ == "__main__":
    main()
