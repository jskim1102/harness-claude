#!/usr/bin/env python3
"""PreToolUse hook for the `Skill` tool — announce skill invocation in the
CTO / teammate pane with a yellow star and the skill name.

Output is delivered three ways for max compatibility:
  1. stderr ANSI-colored line — visible directly in the terminal pane
  2. hookSpecificOutput.systemMessage JSON — Claude Code's UI message
     channel, surfaces in the agent transcript
  3. Append to ~/.harness-claude/skill-activity.log — tailed by the CTO tab's
     skill-activity pane so every teammate's activity is visible.

Exit 0 always. Never block tool invocation.
"""
import json
import os
import re
import sys
import time


def _extract_skill_name(tool_input):
    """Try several common keys for the skill identifier."""
    if not isinstance(tool_input, dict):
        return None
    for key in ("skill", "name", "skill_name", "skillName"):
        v = tool_input.get(key)
        if v:
            return str(v)
    # Some tool inputs nest under 'arguments'
    args = tool_input.get("arguments")
    if isinstance(args, dict):
        for key in ("skill", "name", "skill_name", "skillName"):
            v = args.get(key)
            if v:
                return str(v)
    return None


def _extract_workflow_name(tool_input):
    """Workflow 도구 호출에서 워크플로 이름을 뽑는다. 우선순위:
    named(name) → inline script 의 meta name → scriptPath basename."""
    if not isinstance(tool_input, dict):
        return None
    v = tool_input.get("name")
    if v:
        return str(v)
    script = tool_input.get("script")
    if isinstance(script, str):
        m = re.search(r"name\s*:\s*['\"]([^'\"]+)['\"]", script)  # meta = { name: '...' }
        if m:
            return m.group(1)
    sp = tool_input.get("scriptPath")
    if isinstance(sp, str) and sp:
        return re.sub(r"\.js$", "", sp.rsplit("/", 1)[-1])
    return None


def _extract_agent(payload):
    """어느 에이전트가 이 스킬을 쓰는지 best-effort 로 알아낸다.
    표기 규칙 (PROCESS.md §6): `<에이전트> ★ <스킬>`.
    소스 우선순위: hook payload 의 에이전트 키 → 환경변수 →
    transcript 경로 힌트 → 'cto' (lead 폴백). fail-open."""
    if isinstance(payload, dict):
        for key in ("agent_type", "agent_name", "agentName", "teammate_name",
                    "teammateName", "subagent_type", "agent"):
            v = payload.get(key)
            if v:
                return str(v)
    for env_key in ("CLAUDE_AGENT_NAME", "CLAUDE_TEAMMATE_NAME",
                    "TEAMMATE_NAME", "AGENT_NAME"):
        v = os.environ.get(env_key)
        if v:
            return v
    # transcript 경로에 subagents/<name>... 형태가 있으면 추출
    if isinstance(payload, dict):
        tp = str(payload.get("transcript_path", ""))
        if "/subagents/" in tp:
            tail = tp.split("/subagents/", 1)[1]
            name = tail.split("/", 1)[0].split(".", 1)[0]
            # agent-<id>.jsonl 같은 비식별 이름은 버림
            if name and not name.startswith(("agent-", "wf_")):
                return name
    return "cto"


def _repo_root():
    """이 훅 파일($REPO/hooks/team/skill_announce.py) 위치로 REPO 를 결정론 산출 (3단계 상위)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _project_from_transcript(payload):
    """payload transcript_path 의 인코딩된 프로젝트 경로(~/.claude/projects/<encoded>/…)를
    실제 빌드 dir(modules/·claude-project/) 목록의 인코딩과 매칭해 프로젝트명을 역산한다.
    인코딩 = 절대경로의 '/'·'_' → '-' (delete-cto 의 claude-state 인코딩과 동일). lead·teammate
    모두 같은 프로젝트 dir 아래 transcript 를 두므로 env/cwd 전파에 의존하지 않고 100% 식별된다.
    이름에 하이픈이 있어도(rtsp-detection) 실제 dir 목록과 == 비교라 모호성 없음."""
    if not isinstance(payload, dict):
        return None
    tp = str(payload.get("transcript_path", ""))
    m = re.search(r"/projects/([^/]+)/", tp)
    if not m:
        return None
    encoded = m.group(1)
    repo = _repo_root()
    for base in ("modules", "claude-project"):
        d = os.path.join(repo, base)
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for name in names:
            full = os.path.join(d, name)
            if not os.path.isdir(full):
                continue
            if full.replace("/", "-").replace("_", "-") == encoded:
                return name
    return None


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        p = json.loads(raw)
    except Exception:
        sys.exit(0)

    # Skill 도구 + Workflow 도구 둘 다 announce — 워크플로로 도는 스킬도 스킬창에
    # 보이게 (2026-06-24: Workflow 로 돌린 code-review 가 스킬창·게이트서 사라지던 갭).
    tool = p.get("tool_name")
    if tool == "Skill":
        skill = _extract_skill_name(p.get("tool_input")) or "<unknown>"
    elif tool == "Workflow":
        skill = _extract_workflow_name(p.get("tool_input")) or "<workflow>"
    else:
        sys.exit(0)
    kind = "스킬" if tool == "Skill" else "워크플로"
    agent = _extract_agent(p)

    # 권위적 role 태그 — lead 는 HARNESS_ROLE(env, 빠름). teammate(별도 프로세스, env 미상속)는
    # transcript_path 의 인코딩된 프로젝트 경로를 실제 빌드 dir 와 매칭해 역산 (env/cwd 전파에
    # 의존 X — 2026-06-30 teammate 스킬이 [?] 로 찍혀 skill-pane 필터·reviewer 완료게이트에서
    # 누락되던 버그). 아래 소비처(code-review 마커 / 로그 태그)가 이 값을 쓴다.
    role = os.environ.get("HARNESS_ROLE", "")
    if not role.startswith("cto:"):
        proj = _project_from_transcript(p)
        if proj:
            role = f"cto:{proj}"
    if not role:
        role = "?"

    # code-review/qa-only 스킬 호출을 결정론 기록 — reviewer 완료게이트
    # (task_completed_verify_gate)가 [review] 완료 전 실제 호출 여부를 모델 주장이
    # 아니라 hook 관측으로 검사한다 (2026-06-24 reviewer 수동검증-only PASS 사고).
    try:
        sk = skill.lower()
        if "code-review" in sk or sk in ("qa", "qa-only") or sk.endswith((":qa", ":qa-only")):
            proj = role.split(":", 1)[1] if ":" in role else (role or "_noteam")
            proj = re.sub(r"[^A-Za-z0-9._-]", "_", proj)
            crdir = os.path.expanduser("~/.claude/logs/codereview")
            os.makedirs(crdir, exist_ok=True)
            # 마커를 **에이전트별로** 기록한다. 예전엔 프로젝트 키뿐이라 CTO·planner·
            # designer 가 code-review 를 돌려도 reviewer 의 완료게이트가 열렸다
            # (`agent` 를 위에서 계산해놓고 버리고 있었다 — 2026-07-27).
            ag = re.sub(r"[^A-Za-z0-9._-]", "_", (agent or "?"))
            with open(os.path.join(crdir, "{}.{}.invoked".format(proj, ag)), "w") as _fh:
                _fh.write(str(time.time()))
            # 레거시 호환: 프로젝트 키 마커도 계속 남긴다 (다른 소비처가 있을 수 있음).
            with open(os.path.join(crdir, proj + ".invoked"), "w") as _fh:
                _fh.write(str(time.time()))
    except Exception:
        pass  # fail-open

    # 1) terminal-visible line — `<에이전트> ★ <스킬>` (PROCESS.md §6 표기)
    YELLOW = "\033[33m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    RESET = "\033[0m"
    print(f"{CYAN}{agent}{RESET} {YELLOW}★{RESET} {BOLD}{skill}{RESET} {kind}을(를) 사용합니다.", file=sys.stderr)

    # 2) UI systemMessage for transcript surface
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "systemMessage": f"{agent} ★ {skill} {kind} 사용",
        }
    }
    print(json.dumps(out))

    # 3) Append to shared activity log (CTO 세션 하단 tail pane 이 표시).
    try:
        log_dir = os.path.expanduser("~/.harness-claude")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "skill-activity.log")
        ts = time.strftime("%H:%M:%S")
        with open(log_path, "a", encoding="utf-8") as fp:
            fp.write(f"{ts} [{role}] \033[36m{agent}\033[0m \033[33m★\033[0m \033[1m{skill}\033[0m\n")
    except Exception:
        pass  # fail-open per hook contract

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail open
