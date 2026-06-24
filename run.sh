#!/usr/bin/env bash
# Harness control script.
#
# Mental model:
#   claude = process (one CEO or one CTO brain)
#   tmux   = container (where the process is parked)
#
# CEO runs in the current shell (no tmux container).
# Each CTO runs in its own tmux session so it survives detach + can be
# observed in a multi-pane layout.
#
# Commands (새 체계):
#   ./run.sh ceo                              # start CEO chat (exec claude here)
#   ./run.sh add-cto <name>                   # spawn one CTO (<name> 또는 빌드dir/plan.md) — 세션만,
#                                             # 분해는 attach 후 /start-project 로 수동 시작
#                                             # (/model·/effort 먼저); plan.md 경로가 유일 인자;
#                                             # 부모 dir = 빌드타입(claude-project|modules),
#                                             # dir 이름 = CTO 이름. plan.md 없으면 실패)
#   ./run.sh attach cto-<name>                # tmux attach
#   ./run.sh split-cto <name>                 # teammate 별 tmux pane 분리 (재기동; 되돌리기=add-cto)
#   ./run.sh test-cto <name> "<p>"            # non-interactive smoke test (claude --print)
#   ./run.sh ls / ports / help                # 조회
#   ./run.sh down                             # kill all sessions + dev서버/워커 프로세스 + docker compose 컨테이너 정리
#   ./run.sh stop-cto <name>                  # 한 CTO 정지 (작업 보존, resume 가능)
#   ./run.sh delete-cto <name>|--all          # CTO 완전 삭제 (세션+프로세스+dir+상태)
#   ./run.sh fetch <git-url>                  # extract 소스 .sources/ shallow clone
# observe 는 폐기 — CEO/CTO 터미널 독립 운영.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Exported so slash-command `!`-lines and spawned agents/teammates can resolve
# the harness root on any machine (replaces hardcoded absolute paths).
export HARNESS_ROOT="$REPO"

# Per-role .claude/settings.json + slash-command symlinks + (for CTO) agent
# definitions + team rules.
# role is 'ceo' or 'cto' (template lookup under plugins/$role/).
write_role_settings() {
    local target_dir="$1"
    local role="$2"
    # teammate 표시 모드: in-process(기본 — lead pane 1개 + 하네스 skill pane 2분할)
    # | auto(Claude Code 가 teammate 를 각자 tmux pane 에 분리 — `split-cto` 가 씀).
    local teammate_mode="${3:-in-process}"

    # Slash commands (both roles).
    rm -rf "$target_dir/.claude/commands"
    mkdir -p "$target_dir/.claude/commands"
    for f in "$REPO/plugins/$role/commands"/*.md; do
        ln -sf "$f" "$target_dir/.claude/commands/$(basename "$f")"
    done

    # Saved dynamic workflows (both roles, only if any exist).
    if compgen -G "$REPO/plugins/$role/workflows/*.js" > /dev/null; then
        rm -rf "$target_dir/.claude/workflows"
        mkdir -p "$target_dir/.claude/workflows"
        for f in "$REPO/plugins/$role/workflows"/*.js; do
            ln -sf "$f" "$target_dir/.claude/workflows/$(basename "$f")"
        done
    fi

    # Sub-agent definitions (both roles, only if any exist). CTO gets the
    # 4-teammate Agent Team; CEO gets the librarian (사서). A one-shot Task
    # subagent only needs the agent .md here — Agent Teams env not required.
    if compgen -G "$REPO/plugins/$role/agents/*.md" > /dev/null; then
        rm -rf "$target_dir/.claude/agents"
        mkdir -p "$target_dir/.claude/agents"
        for f in "$REPO/plugins/$role/agents"/*.md; do
            ln -sf "$f" "$target_dir/.claude/agents/$(basename "$f")"
        done
    fi

    if [[ "$role" == "cto" ]]; then
        # Global rules auto-loaded into every teammate session.
        rm -rf "$target_dir/.claude/rules"
        mkdir -p "$target_dir/.claude/rules"
        for f in "$REPO/plugins/cto/rules"/*.md; do
            ln -sf "$f" "$target_dir/.claude/rules/$(basename "$f")"
        done

        # Harness-local skills — same deploy pattern as agents/commands/rules.
        # Without this the Skill tool returns "Unknown skill" on every
        # plugins/cto/skills/* invocation and the ★ never fires for them.
        rm -rf "$target_dir/.claude/skills"
        mkdir -p "$target_dir/.claude/skills"
        for d in "$REPO/plugins/cto/skills"/*/; do
            [[ -d "$d" ]] || continue
            ln -sf "${d%/}" "$target_dir/.claude/skills/$(basename "$d")"
        done

        # settings.json — Agent Teams enabled, in-process display, team hooks,
        # harness repo granted as additional directory so symlinked plugin
        # files (agents/*, rules/*, commands/*) are readable without a per-file
        # permission prompt.
        cat > "$target_dir/.claude/settings.json" <<JSON
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "teammateMode": "$teammate_mode",
  "model": "claude-opus-4-8",
  "effortLevel": "high",
  "statusLine": {
    "type": "command",
    "command": "python3 $REPO/hooks/cto_statusline.py"
  },
  "permissions": {
    "additionalDirectories": [
      "$REPO/plugins/cto"
    ],
    "allow": [
      "Bash(harness:*)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/session_start.py"
          }
        ]
      }
    ],
    "TaskCreated": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/task_created_format_check.py"
          }
        ]
      }
    ],
    "TaskCompleted": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/task_completed_verify_gate.py"
          }
        ]
      }
    ],
    "TeammateIdle": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/teammate_idle_workcheck.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Skill",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/skill_announce.py"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/git_guard.py"
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/project_memory.py"
          }
        ]
      }
    ]
  }
}
JSON
    else
        # CEO settings — minimal, no Agent Teams. The whole harness repo is an
        # additionalDirectory ON PURPOSE: the CEO is the harness meta-manager and
        # edits plugins/ hooks/ harness/ run.sh/ docs (role.md §5); it also makes
        # symlinked plugin files readable without per-file permission prompts.
        cat > "$target_dir/.claude/settings.json" <<JSON
{
  "model": "claude-opus-4-8",
  "permissions": {
    "additionalDirectories": [
      "$REPO"
    ],
    "allow": [
      "Bash(harness:*)"
    ]
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/session_start.py"
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/user_prompt_inbox_check.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/git_guard.py"
          }
        ]
      }
    ]
  }
}
JSON
    fi
}

# Spawn a detached tmux session running `claude` with HARNESS_ROLE set.
# CTO sessions launch with --dangerously-skip-permissions so they can act
# fully unattended (no Write/Edit/Bash approval dialogs, no bypass-mode
# acceptance screen). CEO uses cmd_ceo's exec path and keeps normal mode
# because a human is sitting next to it.
start_session() {
    local name="$1"   # tmux session name
    local cwd="$2"
    local role="$3"
    if tmux has-session -t "=$name" 2>/dev/null; then
        echo "session $name already running" >&2
        return 0
    fi
    tmux new-session -d -s "$name" -c "$cwd"
    tmux send-keys -t "$name" "export HARNESS_ROLE='$role'" Enter
    tmux send-keys -t "$name" "clear" Enter
    tmux send-keys -t "$name" "claude --dangerously-skip-permissions" Enter
    # Auto-accept the one-time "Bypass Permissions mode" warning screen.
    # That screen's default selection is "No, exit" — pressing Enter alone
    # would kill the session. Send Down (move to "Yes, I accept") + Enter.
    # If the screen never appears (consent already cached), Down+Enter is
    # harmless on the empty claude prompt. 5s delay tuned to claude boot.
    ( sleep 5 && tmux send-keys -t "$name" Down Enter ) &
    echo "started session=$name role=$role cwd=$cwd"
}

# Minimum Claude Code version — Agent Teams + /goal (autopilot).
CLAUDE_MIN_VERSION="2.1.139"

# Compare two semver-ish strings. Returns 0 if $1 >= $2.
_version_ge() {
    [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | tail -n1)" == "$1" ]]
}

_check_claude_version() {
    local current
    current=$(claude --version 2>/dev/null | awk '{print $1}')
    if [[ -z "$current" ]]; then
        echo "error: 'claude' command not found or no version output." >&2
        return 1
    fi
    if ! _version_ge "$current" "$CLAUDE_MIN_VERSION"; then
        echo "error: Claude Code $current detected; >= $CLAUDE_MIN_VERSION required (Agent Teams + /goal autopilot)." >&2
        echo "       Run: claude update" >&2
        return 1
    fi
    return 0
}

# Ensure the harnessd polling daemon is up. Spawn if missing.
_ensure_harnessd() {
    if ! tmux has-session -t "=harnessd" 2>/dev/null; then
        tmux new-session -d -s "harnessd" -c "$REPO"
        tmux send-keys -t harnessd "python3 -m harness.daemon" Enter
        echo "started harnessd"
    else
        echo "harnessd: alive"
    fi
}

# CTO 세션 하단에 6줄 skill-activity tail pane 추가 (idempotent — 'tail' pane 이
# 이미 있으면 skip). attach/observe 안 거쳐도 ★ 스킬 실행이 보이게 한다.
# add-cto(기본)·split-cto(팀 분할) 공통 — split 모드에서도 teammate pane 과 별개로
# "지금 누가 어떤 skill 도는지"를 한 줄 로그로 보여준다.
_attach_skill_pane() {
    local name="$1"
    mkdir -p "$HOME/.harness-claude"
    touch "$HOME/.harness-claude/skill-activity.log"
    tmux has-session -t "=cto-$name" 2>/dev/null || return 0
    if tmux list-panes -t "cto-$name" 2>/dev/null | grep -q 'tail'; then
        echo "skill-activity pane already present, skipping split"
        return 0
    fi
    local win
    win=$(tmux list-windows -t "cto-$name" -F '#{window_index}' | head -1)
    tmux split-window -v -l 6 -t "cto-$name:${win}" \
      "printf '\\033[1m== skill activity (cto:${name}) ==\\033[0m\\n'; tail -n 20 -F $HOME/.harness-claude/skill-activity.log | grep --line-buffered -E '\\[cto:${name}\\]'"
    # return focus to the claude pane (top); pane index varies by tmux config
    tmux select-pane -t "cto-$name:${win}" -U 2>/dev/null || true
    # Set claude pane title so daemon's _find_by_pane_title('cto:NAME') can match.
    tmux select-pane -t "cto-$name" -T "cto:$name" 2>/dev/null || true
}

# 빌드 dir 스폰 가능 검사. plan.md(1단계 신규) **또는** specs/tasks.md(분해 완료 —
# plan 없이 재개) 가 있으면 OK. specs 존재 = 이미 plan 이 있었음을 증명하므로
# fail-closed(§7 plan 선행) 유지 — 둘 다 없는 빈 dir 만 거부.
_build_ready() { [[ -d "$1" ]] && { [[ -f "$1/plan.md" ]] || [[ -f "$1/specs/tasks.md" ]]; }; }

cmd_add_cto() {
    # 시그니처: <name> (CEO 가 만든 빌드 dir 이름) 또는 plan.md 경로/빌드 dir 1개.
    #   ./run.sh add-cto <name>                          # claude-project/·modules/ 스캔해 resolve
    #   ./run.sh add-cto claude-project/<name>/plan.md   # 경로 직접 지정도 가능
    # 분해는 자동 시작 안 함 — attach 후 /model·/effort 고르고 /start-project 로 시작.
    # 부모 dir 가 빌드타입(축1)·CTO 이름·작업 dir 를 전부 확정한다.
    # 스폰 가능 = plan.md(1단계 신규) 또는 specs/tasks.md(분해 완료 → plan 없이 재개);
    # 둘 다 없으면 실패 (fail-closed). 인자: 위치 인자 1개. 플래그 없음.
    local plan_arg="${1:?usage: $0 add-cto <name> | <claude-project|modules>/<name>/plan.md}"
    if [[ $# -gt 1 ]]; then
        echo "error: add-cto 는 인자 1개 (plan.md 경로)." >&2
        return 1
    fi
    case "$plan_arg" in
        --module|--plan)
            echo "error: '$plan_arg' 모드는 폐기됨 — add-cto <빌드dir>/plan.md 로 호출." >&2
            echo "       모듈 재사용 = CEO plan.md 의 '## 3 Library Check' (RULES §7)." >&2
            return 1 ;;
    esac

    # arg → 빌드 dir 로 normalize + 스폰 가능(_build_ready) 검사.
    local dir name base build_type
    if [[ "$plan_arg" != */* && "$plan_arg" != *.md ]]; then
        # bare name 단축 → claude-project/<name> | modules/<name> 스캔 (하나만; 둘 다면 모호).
        if ! [[ "$plan_arg" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
            echo "error: name must be kebab-case (lowercase, digits, hyphens)." >&2
            return 1
        fi
        local _dp="$REPO/claude-project/$plan_arg" _dm="$REPO/modules/$plan_arg" _hits=()
        _build_ready "$_dp" && _hits+=("$_dp")
        _build_ready "$_dm" && _hits+=("$_dm")
        if [[ ${#_hits[@]} -eq 0 ]]; then
            echo "error: '$plan_arg' 스폰 불가 — plan.md(1단계) 도 specs/tasks.md(재개) 도 없음. /build-project | /build-module 먼저." >&2
            return 1
        elif [[ ${#_hits[@]} -gt 1 ]]; then
            echo "error: '$plan_arg' 가 claude-project/ 와 modules/ 양쪽 존재 — 모호. 전체 경로로 지정." >&2
            return 1
        fi
        dir="${_hits[0]}"
    else
        # 경로 형: <dir>/plan.md 또는 빌드 <dir> 직접 (상대경로 = repo 루트 기준).
        local _p="$plan_arg"
        [[ "$_p" != /* ]] && _p="$REPO/$_p"
        [[ "$(basename "$_p")" == "plan.md" ]] && _p="$(dirname "$_p")"
        if [[ ! -d "$_p" ]]; then
            echo "error: 빌드 dir 없음: $_p" >&2
            return 1
        fi
        dir="$(cd "$_p" && pwd)"
        if ! _build_ready "$dir"; then
            echo "error: '$plan_arg' 스폰 불가 — plan.md(1단계) 도 specs/tasks.md(재개) 도 없음." >&2
            echo "       1단계 먼저 — CEO 창에서 /build-project 또는 /build-module." >&2
            return 1
        fi
    fi

    name="$(basename "$dir")"
    base="$(basename "$(dirname "$dir")")"
    case "$base" in
        claude-project) build_type="project" ;;
        modules)        build_type="module" ;;
        *)
            echo "error: 빌드 는 claude-project/<name>/ 또는 modules/<name>/ 아래여야 함 (got: $base/$name)" >&2
            return 1 ;;
    esac
    # 레포 밖 경로 차단 (/tmp/modules/x 같은 동명 base 우회 방지).
    if [[ "$dir" != "$REPO/claude-project/$name" && "$dir" != "$REPO/modules/$name" ]]; then
        echo "error: 빌드 dir 는 $REPO 안의 claude-project/ 또는 modules/ 여야 함 (got: $dir)" >&2
        return 1
    fi

    # validate name (kebab-case slug)
    if ! [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: name must be kebab-case (lowercase, digits, hyphens). Underscores forbidden." >&2
        return 1
    fi
    _check_claude_version || return 1
    _ensure_harnessd

    # Port allocation (PORT.md / hard rule 4): assign the next free offset and
    # write the project's .env so the CTO inherits non-colliding ports — no
    # manual sibling-grep. The .env is the truth PORT.md is regenerated from.
    if [[ ! -f "$dir/.env" ]]; then
        mkdir -p "$HOME/.harness-claude" 2>/dev/null || true
        # flock the read(next-offset)→write(.env)→refresh(PORT.md) sequence so
        # two concurrent `add-cto` runs can't be handed the same offset (RULES §4
        # TOCTOU floor; the CEO port-confirm protocol §4.0 is the 2nd layer).
        (
            flock 9
            offset="$(harness ports --next 2>/dev/null)"
            if [[ "$offset" =~ ^[0-9]+$ ]]; then
                {
                    echo "# auto-assigned by add-cto (PORT.md / hard rule 4); offset=$offset"
                    echo "PORT_OFFSET=$offset"
                    echo "BACKEND_PORT=$((8000 + offset))"
                    echo "FRONTEND_PORT=$((5173 + offset))"
                } > "$dir/.env"
                harness ports --quiet 2>/dev/null || true
                echo "ports: offset=$offset → backend $((8000 + offset)) / frontend $((5173 + offset)) (PORT.md 갱신)"
            fi
        ) 9>"$HOME/.harness-claude/ports.lock"
    fi

    write_role_settings "$dir" "cto"

    start_session "cto-$name" "$dir" "cto:$name"

    # 분해는 자동 시작하지 않는다 — CTO 세션을 빈 claude 프롬프트로 띄워두고,
    # 사용자가 attach 후 /model·/effort 를 고른 뒤 직접 /start-project 로 시작한다
    # (모델/effort 선택 window 확보). /start-project = 팀 spawn 의 명시 사용자
    # 신호 (harness-team-spawn "When to spawn" path 1). send-keys auto-kickoff 폐기.
    echo "CTO 세션 대기 중 — 분해 자동 시작 안 함 (build_type=$build_type, 디렉토리가 확정)."
    echo "  다음: ./run.sh attach cto-$name → 세션 안에서 /model · /effort 설정 → /start-project"

    # 6줄 skill-activity tail pane 추가 (attach 직접 해도 ★ 가 보이게).
    _attach_skill_pane "$name"

    echo "attach: tmux attach -t cto-$name"
}

# (observe 는 폐기됨 — CEO/CTO 터미널 독립 운영.)

# Non-interactive smoke test for a CTO sandbox. Sends a prompt to a fresh
# claude --print invocation in the CTO's sandbox dir with HARNESS_ROLE set,
# token-bounded by --max-turns (default 10). For real interactive work use
# `tmux attach -t cto-<name>` instead.
#
# Usage: ./run.sh test-cto <name> "<prompt>"
#        ./run.sh test-cto <name> --max-turns 30 "<prompt>"
cmd_test_cto() {
    local name="${1:?usage: $0 test-cto <name> [--max-turns N] \"<prompt>\"}"
    shift
    local turns=10
    if [[ "${1:-}" == "--max-turns" ]]; then
        turns="${2:-10}"
        shift 2
    fi
    local prompt="$*"
    if [[ -z "$prompt" ]]; then
        echo "error: prompt required" >&2
        return 1
    fi
    # 빌드 dir = claude-project/<name>/ (프로젝트) 또는 modules/<name>/ (모듈).
    local dir="" base
    for base in claude-project modules; do
        [[ -d "$REPO/$base/$name" ]] && { dir="$REPO/$base/$name"; break; }
    done
    if [[ -z "$dir" ]]; then
        echo "error: $name not present under claude-project/ or modules/." >&2
        return 1
    fi
    echo "$prompt" | (cd "$dir" && HARNESS_ROLE="cto:$name" claude --print --max-turns "$turns")
}

cmd_ls() {
    # Match legacy 'ceo'/'observe' sessions too so leftovers from an older
    # run.sh are visible to the user (and can be cleaned via down).
    tmux ls 2>/dev/null | awk -F: '
        /^(ceo|cto-|harnessd|observe)/ { print $0 }
    ' || echo "(no tmux server running)"
}

# Internal: kill every process tied to the project dir — (a) cmdline 이 그
# 경로를 포함하거나 (b) cwd 가 그 dir 아래인 프로세스 (vite 워커처럼 argv 에
# 경로가 없는 자식까지). tmux kill 만으론 dev 서버가 살아남아 디렉토리를
# 되살린다 (rtsp 부활 사고, 2026-06-12). 자기 자신·조상 프로세스는 제외.
_kill_project_processes() {
    local dir="$1"
    [[ -z "$dir" ]] && return 0
    # 안전핀: $REPO 아래의 빌드 dir 에만 동작 (임의 경로 pkill 방지).
    case "$dir" in
        "$REPO"/claude-project/*|"$REPO"/modules/*) ;;
        *) return 0 ;;
    esac
    local killed=0 pid cwd
    # (a) cmdline 매치
    if pkill -f -- "$dir" 2>/dev/null; then killed=1; fi
    # (b) cwd 매치 (argv 에 경로 없는 워커) — 자기 자신/부모 제외
    for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
        [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
        cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
        case "$cwd" in "$dir"|"$dir"/*) kill "$pid" 2>/dev/null && killed=1 ;; esac
    done
    if [[ $killed -eq 1 ]]; then
        sleep 1
        pkill -9 -f -- "$dir" 2>/dev/null || true
        for pid in $(ls /proc 2>/dev/null | grep -E '^[0-9]+$'); do
            [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
            cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
            case "$cwd" in "$dir"|"$dir"/*) kill -9 "$pid" 2>/dev/null || true ;; esac
        done
        echo "  ✓ killed leftover processes for $dir (cmdline+cwd)"
    fi
}

# Internal: tear down the build's Docker compose stack so containers don't
# outlive the CTO. _kill_project_processes only catches HOST processes
# (cmdline/cwd) — compose containers are docker-daemon children, so they
# survive a tmux kill + pkill (rtsp 부활 사고, 2026-06-12: 삭제된 빌드의
# frontend/backend/mediamtx 컨테이너가 24h 잔존 → 다음 빌드 포트 점유, 결정 요청).
# 2단 방어: (1) compose 파일 있으면 `compose down --remove-orphans`,
# (2) dir 가 이미 삭제돼 compose 파일이 없어도 프로젝트명 패턴으로 잔존 컨테이너 스윕.
# 볼륨·이미지는 보존 (데이터/캐시 — 비파괴). docker 없으면 no-op.
_down_compose_stack() {
    local dir="$1"
    [[ -z "$dir" ]] && return 0
    command -v docker >/dev/null 2>&1 || return 0
    # 안전핀: $REPO 아래 빌드 dir 만 (임의 프로젝트명 docker rm 방지).
    case "$dir" in
        "$REPO"/claude-project/*|"$REPO"/modules/*) ;;
        *) return 0 ;;
    esac
    local proj cf="" f
    proj="$(basename "$dir")"
    for f in docker-compose.yml docker-compose.yaml compose.yml compose.yaml; do
        [[ -f "$dir/$f" ]] && { cf="$dir/$f"; break; }
    done
    if [[ -n "$cf" ]]; then
        if timeout 60 docker compose -f "$cf" down --remove-orphans >/dev/null 2>&1; then
            echo "  ✓ docker compose down ($proj — 컨테이너/네트워크 정리, 볼륨 보존)"
        else
            echo "  - docker compose down 스킵/실패 ($proj) — docker 미동작이거나 stack 없음"
        fi
    fi
    # 잔존 스윕: compose 파일이 없어도(dir 삭제됨) 프로젝트명으로 남은 컨테이너 제거.
    # compose v2=<proj>-<svc>-<n> / v1=<proj>_<svc>_<n>. name 필터는 정규식(^앵커).
    local leftover
    leftover="$(timeout 30 docker ps -aq --filter "name=^${proj}[-_]" 2>/dev/null || true)"
    if [[ -n "$leftover" ]]; then
        if timeout 60 docker rm -f $leftover >/dev/null 2>&1; then
            echo "  ✓ removed leftover $proj containers ($(echo "$leftover" | grep -c .)개)"
        else
            echo "  - leftover $proj 컨테이너 제거 실패 — 수동 확인 필요"
        fi
    fi
}

# Internal: delete one CTO's traces. Caller already validated name.
_delete_cto_traces() {
    local name="$1"
    # 빌드 dir = claude-project/<name>/ 또는 modules/<name>/.
    local dir="" base
    for base in claude-project modules; do
        [[ -d "$REPO/$base/$name" ]] && { dir="$REPO/$base/$name"; break; }
    done
    [[ -z "$dir" ]] && dir="$REPO/claude-project/$name"
    # claude code encodes project paths by replacing / and _ with -.
    local encoded
    encoded=$(echo "$dir" | sed 's![/_]!-!g')
    local claude_state_dir="$HOME/.claude/projects/$encoded"
    local db="$HOME/.harness-claude/db.sqlite"
    local skill_log="$HOME/.harness-claude/skill-activity.log"

    if tmux kill-session -t "cto-$name" 2>/dev/null; then
        echo "  ✓ killed tmux session cto-$name"
    else
        echo "  - tmux session cto-$name not running"
    fi

    # dev 서버/워커 프로세스부터 정리 — rm 후 프로세스가 dir 를 되살리는 것 방지.
    _kill_project_processes "$dir"
    # docker compose 컨테이너 정리 — rm 전에 (compose 파일 필요). 잔존 방지.
    _down_compose_stack "$dir"

    if [[ -d "$dir" ]]; then
        rm -rf "$dir" && echo "  ✓ removed $dir"
    else
        echo "  - $dir not present"
    fi

    if [[ -f "$db" ]]; then
        sqlite3 "$db" \
          "DELETE FROM msg WHERE from_role='cto:$name' OR to_role='cto:$name'"
        echo "  ✓ purged sqlite rows for cto:$name"
    else
        echo "  - $db not present"
    fi

    if [[ -f "$skill_log" ]]; then
        sed -i "/\[cto:$name\]/d" "$skill_log"
        echo "  ✓ purged log lines for cto:$name"
    else
        echo "  - $skill_log not present"
    fi

    if [[ -d "$claude_state_dir" ]]; then
        rm -rf "$claude_state_dir" && echo "  ✓ removed $claude_state_dir"
    else
        echo "  - $claude_state_dir not present"
    fi

    # Free the port offset: regenerate PORT.md from the (now-removed) project set.
    harness ports --quiet 2>/dev/null && echo "  ✓ refreshed PORT.md (offset freed)" || true
}

cmd_ports() {
    # Regenerate + print docs/PORT.md from a scan of every project's .env.
    harness ports "$@"
}

# Fetch a source repo into .sources/ — extract 재료(축3 source=extract:[…]) 가
# git URL 일 때 CEO 가 분석 전에 받아온다. github URL → codeload tarball
# (no .git); 그 외 → shallow `git clone` with .git stripped.
# Reuses an existing .sources/<name>. Prints ONLY the absolute local path on
# stdout (progress → stderr) so callers can: dir="$(./run.sh fetch <url>)".
cmd_fetch() {
    local url="${1:?usage: $0 fetch <git-url>}"
    local root="$REPO/.sources" name dest
    name="$(basename "${url%.git}")"
    dest="$root/$name"
    mkdir -p "$root"
    if [[ -d "$dest" ]]; then
        echo "reuse: $dest already present" >&2
        echo "$dest"; return 0
    fi
    if [[ "$url" =~ github\.com[:/]+([^/]+)/([^/.]+) ]]; then
        local owner_repo="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}" b
        for b in main master; do
            if curl -sfL "https://codeload.github.com/$owner_repo/tar.gz/refs/heads/$b" -o "/tmp/.fs-$name.tar.gz"; then
                mkdir -p "$dest"
                if tar xzf "/tmp/.fs-$name.tar.gz" -C "$dest" --strip-components=1; then
                    rm -f "/tmp/.fs-$name.tar.gz"
                    echo "fetched (tarball $b): $dest" >&2
                    echo "$dest"; return 0
                fi
                rm -rf "$dest" "/tmp/.fs-$name.tar.gz"
            fi
        done
    fi
    if git clone --depth 1 "$url" "$dest" >&2; then
        rm -rf "$dest/.git"
        echo "fetched (shallow clone): $dest" >&2
        echo "$dest"; return 0
    fi
    echo "error: failed to fetch $url (tarball + clone both failed)" >&2
    return 1
}

# Enumerate every CTO name known to the system. Union of:
#   - on-disk build dirs under claude-project/ (excluding ceo)
#     ※ modules/ 는 의도적으로 제외 — 완성 모듈(라이브러리 자산)이
#       delete-cto --all 에 쓸려나가는 것 방지. 모듈 빌드 삭제는
#       명시적 `delete-cto <name>` 으로만.
#   - live tmux sessions matching cto-*
#   - sqlite roles matching cto:*
#   - skill-activity log entries tagged [cto:<name>]
_list_all_cto_names() {
    {
        for base in claude-project; do
            ls -1 "$REPO/$base" 2>/dev/null | grep -v '^ceo$' || true
        done
        tmux ls -F '#{session_name}' 2>/dev/null | grep '^cto-' | sed 's/^cto-//' || true
        sqlite3 "$HOME/.harness-claude/db.sqlite" \
          "SELECT DISTINCT substr(from_role,5) FROM msg WHERE from_role LIKE 'cto:%' \
           UNION SELECT DISTINCT substr(to_role,5) FROM msg WHERE to_role LIKE 'cto:%'" 2>/dev/null || true
        grep -oE '\[cto:[a-z0-9-]+\]' "$HOME/.harness-claude/skill-activity.log" 2>/dev/null \
          | sed -E 's/^\[cto:([a-z0-9-]+)\]$/\1/' || true
    } | sort -u | sed '/^$/d'
}

# Remove every trace of a CTO: tmux session, sandbox dir, sqlite rows,
# skill-activity log lines, and claude code's per-project state dir.
# No confirmation prompt — typing delete-cto IS the confirmation.
# Use --all to wipe every CTO known to the system.
cmd_delete_cto() {
    local target="${1:?usage: $0 delete-cto <name>|--all}"

    if [[ "$target" == "--all" ]]; then
        local names
        names=$(_list_all_cto_names)
        if [[ -z "$names" ]]; then
            echo "no CTOs found."
            return 0
        fi
        echo "Deleting all CTOs: $(echo "$names" | tr '\n' ' ')"
        while IFS= read -r n; do
            [[ -z "$n" ]] && continue
            if ! [[ "$n" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
                echo "  ✗ '$n' invalid kebab-case, skipping"
                continue
            fi
            echo "--- $n ---"
            _delete_cto_traces "$n"
        done <<< "$names"
        echo "done."
        return 0
    fi

    if ! [[ "$target" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: name must be kebab-case (or use --all)." >&2
        return 1
    fi
    # 'ceo' 는 CTO 가 아니다 — 삭제하면 CEO 대화이력+메모리까지 통째 소실.
    # (--all 의 grep -v '^ceo$' / cmd_down 의 ceo 스킵과 동일한 보호.)
    if [[ "$target" == "ceo" ]]; then
        echo "error: 'ceo' is reserved — not a CTO. CEO 디렉토리는 삭제 대상이 아님." >&2
        return 1
    fi

    echo "Deleting CTO '$target':"
    _delete_cto_traces "$target"
    echo "done."
}

# stop-cto — 한 CTO 의 **세션(claude 에이전트)만** 정지. delete-cto 와 달리
# 빌드 dir·specs·sqlite·로그·포트 오프셋을 유지하고, backend/frontend/compose
# 같은 dev 서버/컨테이너도 건드리지 않는다 (계속 떠 있음). 나중에
# `add-cto <dir>/plan.md` 로 기존 specs/tasks.md 에서 세션 재개.
cmd_stop_cto() {
    local name="${1:?usage: $0 stop-cto <name>}"
    if ! [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: name must be kebab-case." >&2
        return 1
    fi
    if [[ "$name" == "ceo" ]]; then
        echo "error: 'ceo' is reserved — not a CTO." >&2
        return 1
    fi
    # 빌드 dir 해석 (claude-project/<name> 또는 modules/<name>).
    local dir="" base
    for base in claude-project modules; do
        [[ -d "$REPO/$base/$name" ]] && { dir="$REPO/$base/$name"; break; }
    done

    echo "Stopping CTO '$name' (세션만 정지 — backend/frontend/compose/포트/specs 모두 유지):"
    # CTO claude 세션(에이전트)만 kill. dev 서버/워커/compose 컨테이너는 건드리지
    # 않는다 — 계속 떠 있음. 세션만 내린다.
    if tmux kill-session -t "cto-$name" 2>/dev/null; then
        echo "  ✓ killed tmux session cto-$name (세션만)"
    else
        echo "  - tmux session cto-$name not running"
    fi
    if [[ -n "$dir" ]]; then
        echo "재개: ./run.sh add-cto ${dir#"$REPO"/}/plan.md"
    else
        echo "재개: ./run.sh add-cto <빌드dir>/plan.md"
    fi
}

# split-cto <name> — 한 CTO 를 teammate-별-pane 분리 모드로 전환 + 재기동.
# 기본(add-cto) = teammateMode in-process (lead 1 pane + 하네스 skill pane = 2분할,
# teammate 출력이 lead pane 에 섞임). split-cto = teammateMode auto → Claude Code 가
# planner/designer/developer/reviewer 를 **각자 tmux pane** 에 띄움 → lead pane 은
# 사용자↔CTO 만. teammateMode 는 세션 시작 시 읽히므로 세션 재기동 필요(작업
# .env/specs/tasks.md 보존). split 모드에선 하네스 skill pane 안 붙인다(teammate
# pane 들이 활동을 보여줌; 추가 split 은 레이아웃만 빽빽). 되돌리기 = `add-cto`(기본).
cmd_split_cto() {
    local name="${1:?usage: $0 split-cto <name>}"
    if ! [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: name must be kebab-case." >&2
        return 1
    fi
    if [[ "$name" == "ceo" ]]; then
        echo "error: 'ceo' is reserved — not a CTO." >&2
        return 1
    fi
    local dir="" base
    for base in claude-project modules; do
        [[ -d "$REPO/$base/$name" ]] && { dir="$REPO/$base/$name"; break; }
    done
    if [[ -z "$dir" ]]; then
        echo "error: 빌드 dir 없음 (claude-project/$name·modules/$name) — 먼저 add-cto." >&2
        return 1
    fi
    if [[ ! -f "$dir/plan.md" ]]; then
        echo "error: $dir/plan.md 없음 — split-cto 전에 1단계(plan) 필요." >&2
        return 1
    fi
    _check_claude_version || return 1
    _ensure_harnessd

    echo "Switching CTO '$name' → split-pane teammate mode (auto):"
    # 1) 기존 세션 정지 (settings.json 은 세션시작에 읽혀 재기동 필요; 작업은 보존)
    if tmux kill-session -t "cto-$name" 2>/dev/null; then
        echo "  ✓ stopped session cto-$name (재기동용)"
        _kill_project_processes "$dir"
    fi
    # 2) settings.json 을 auto(split-pane) 로 재작성
    write_role_settings "$dir" "cto" "auto"
    echo "  ✓ teammateMode=auto — teammate 가 각자 tmux pane 에"
    # 3) 세션 재기동 + skill-activity pane (teammate pane 과 별개로 skill 로그도 표시)
    start_session "cto-$name" "$dir" "cto:$name"
    _attach_skill_pane "$name"
    echo "CTO 세션 재기동 — 분해 자동시작 안 함."
    echo "  다음: ./run.sh attach cto-$name → /model · /effort → /start-project"
    echo "  → lead pane(너↔CTO) + skill-activity + planner/designer/developer/reviewer 각자 pane."
    echo "  되돌리기(기본 2분할 in-process): ./run.sh add-cto ${dir#"$REPO"/}/plan.md"
}

cmd_down() {
    # Kill every session we own: harnessd plus all cto-* (+ legacy ceo/observe
    # leftovers). CEO in the user's foreground shell is NOT killed.
    local sessions
    sessions=$(tmux ls 2>/dev/null | awk -F: '
        /^(ceo|cto-[^:]+|harnessd|observe):/ { print $1 }
    ' || true)
    if [[ -n "$sessions" ]]; then
        while IFS= read -r s; do
            tmux kill-session -t "$s" && echo "killed $s"
        done <<< "$sessions"
    else
        echo "no harness sessions running"
    fi
    # CTO 가 띄운 dev 서버/워커 프로세스까지 정리 (ceo dir 제외).
    local d
    for d in "$REPO"/claude-project/*/ "$REPO"/modules/*/; do
        [[ -d "$d" ]] || continue
        [[ "$(basename "$d")" == "ceo" ]] && continue
        _kill_project_processes "${d%/}"
        _down_compose_stack "${d%/}"
    done
}

cmd_attach() {
    tmux attach -t "${1:?usage: $0 attach <session>}"
}

# doctor — 하네스 정합 검사 (결정론, 토큰 0). 재설계 리뷰의 교훈:
# 버그 대부분 = 참조 문서망의 구체계 drift. 하네스 파일 수정 후 반드시 실행
# (CEO role.md §5). 금지 토큰 / 참조 무결성 / 문법·컴파일 / 버전 / 심링크.
cmd_doctor() {
    local rc=0 t
    echo "== harness doctor =="

    # 1) 금지 토큰 — 폐기된 구체계가 활성 지시로 잔존하면 FAIL.
    #    ("폐기/구 경로/deprecated" 문맥의 이력 언급은 허용.)
    echo "--- [1] 금지 토큰 (plugins/ hooks/ run.sh harness/) ---"
    local banned="use-modules\.md|MODULE\.md|modules/INDEX\.md|autopilot-state|mode-state\.json|harness-autopilot-run|scan_module_coverage|claude-module|← spec:|\.claude/specs"
    local hits
    hits=$(grep -rnE "$banned" plugins/ hooks/ run.sh harness/ 2>/dev/null \
        | grep -vE "폐기|구 경로|구체계|deprecated|DEPRECATED|doctor|banned=" || true)
    if [[ -n "$hits" ]]; then
        echo "$hits" | head -10
        echo "  ✗ 금지 토큰 발견 ($(echo "$hits" | wc -l)건)"; rc=1
    else
        echo "  ✓ clean"
    fi

    # 2) 참조 무결성 — 핵심 파일/배선 실존.
    echo "--- [2] 참조 무결성 ---"
    local f missing=0
    for f in hooks/cto_statusline.py hooks/session_start.py hooks/git_guard.py hooks/team/skill_announce.py \
             plugins/_shared/RULES.md plugins/_shared/PROCESS.md plugins/_shared/CODE_QUALITY.md \
             plugins/ceo/commands/build-project.md plugins/ceo/commands/build-module.md \
             plugins/cto/commands/start-project.md \
             plugins/cto/agents/planner.md plugins/cto/agents/designer.md \
             plugins/cto/agents/developer.md plugins/cto/agents/reviewer.md \
             plugins/cto/skills/harness-task-format/scripts/scan_spec_coverage.sh; do
        [[ -f "$REPO/$f" ]] || { echo "  ✗ missing: $f"; missing=1; }
    done
    [[ $missing -eq 0 ]] && echo "  ✓ 핵심 파일 전부 실존" || rc=1
    # dangling symlinks (스폰된 빌드 dir 의 .claude 배선)
    local dangling
    dangling=$(find "$REPO/claude-project" "$REPO/modules" -xtype l 2>/dev/null || true)
    if [[ -n "$dangling" ]]; then
        echo "$dangling" | head -5; echo "  ✗ dangling symlink"; rc=1
    else
        echo "  ✓ dangling symlink 없음"
    fi
    # PROCESS.md 가 새 버전인지 (stale-buffer 사고 방어 — §0 헤더 존재 확인)
    if grep -q "모듈 vs 프로젝트" "$REPO/plugins/_shared/PROCESS.md" 2>/dev/null; then
        echo "  ✓ PROCESS.md = 새 체계 (§0 확인)"
    else
        echo "  ✗ PROCESS.md 가 구버전 — stale IDE buffer 저장 의심"; rc=1
    fi

    # 3) 문법/컴파일
    echo "--- [3] 문법/컴파일 ---"
    if bash -n "$REPO/run.sh" 2>/dev/null; then echo "  ✓ run.sh"; else echo "  ✗ run.sh 문법"; rc=1; fi
    if python3 -m py_compile "$REPO"/hooks/*.py "$REPO"/hooks/team/*.py \
        "$REPO"/harness/*.py "$REPO"/plugins/ceo/scripts/*.py 2>/dev/null; then
        echo "  ✓ python 전체"
    else echo "  ✗ python 컴파일 실패"; rc=1; fi
    for t in "$REPO"/plugins/cto/skills/*/scripts/*.sh; do
        [[ -f "$t" ]] || continue
        bash -n "$t" 2>/dev/null || { echo "  ✗ $t"; rc=1; }
    done
    echo "  ✓ 스킬 스크립트 문법"

    # 4) claude 버전 (/goal 요건)
    echo "--- [4] claude 버전 (>= $CLAUDE_MIN_VERSION) ---"
    if _check_claude_version 2>/dev/null; then echo "  ✓ $(claude --version 2>/dev/null | awk '{print $1}')"; else echo "  ✗ 버전 미달/미설치"; rc=1; fi

    # 5) canon 정합성 (RULE A/B) — teammate(planner/developer/designer)는 PROCESS 를
    #    주입받지 못해 각자 phase 공식 슬라이스를 복사해 든다(구조상 필수). 복사본이
    #    PROCESS/RULES 와 발산하면 drift (이번 세션 phase3/compose 버그가 그것).
    #    dedup 불가 → 복사본 동기화를 doctor 가 결정론으로 강제한다.
    echo "--- [5] canon 정합성 (RULE A/B) ---"
    local PLN="$REPO/plugins/cto/agents/planner.md"
    local DEV="$REPO/plugins/cto/agents/developer.md"
    local DSG="$REPO/plugins/cto/agents/designer.md"
    local PRC="$REPO/plugins/_shared/PROCESS.md"
    local RLS="$REPO/plugins/_shared/RULES.md"
    local QLT="$REPO/plugins/_shared/CODE_QUALITY.md"
    local canon_ok=1

    # 5a) RULE B drift sentinel (negative) — phase3 가 'compose up' 을 기본 실행경로로
    #     mandate 하면 위반. 게이트 문구가 없는 'phase3'+'compose up' 한 줄 = compose 버그 재발.
    local gate='docker화 해|docker화|사용자 명시|시만|계획된 ckpt 가|only on|Never Docker compose'
    local sentinel
    sentinel=$(grep -hnE 'phase3' "$PLN" "$DEV" "$DSG" "$PRC" 2>/dev/null \
        | grep -E 'compose up' | grep -vE "$gate" || true)
    if [[ -n "$sentinel" ]]; then
        echo "$sentinel" | head -5
        echo "  ✗ RULE B: phase3 가 compose up 을 기본 실행경로로 mandate (게이트 문구 없음)"; canon_ok=0
    fi

    # 5b) RULE B positive — phase3 실행경로 = ./dev.sh. planner/developer/PROCESS 각각 언급해야.
    local cf
    for cf in "$PLN" "$DEV" "$PRC"; do
        if ! { grep -qE 'phase3' "$cf" 2>/dev/null && grep -qE 'dev\.sh' "$cf" 2>/dev/null; }; then
            echo "  ✗ RULE B: $(basename "$(dirname "$cf")")/$(basename "$cf") 에 phase3 실행경로 dev.sh 부재"; canon_ok=0
        fi
    done

    # 5c) RULE A — 게이트3 가 /goal 통과불가. RULES 에 '게이트3', PROCESS 에 '게이트1·2·3' + 게이트3/goal 결속.
    grep -qE '게이트3' "$RLS" 2>/dev/null || { echo "  ✗ RULE A: RULES.md 에 게이트3 부재"; canon_ok=0; }
    grep -qE '게이트1·2·3' "$PRC" 2>/dev/null || { echo "  ✗ RULE A: PROCESS.md 에 게이트1·2·3 부재"; canon_ok=0; }
    grep -qE '게이트3.*(goal|통과 불가|자가 선언)|goal.*게이트3' "$PRC" 2>/dev/null \
        || { echo "  ✗ RULE A: PROCESS.md 에 게이트3↔goal 결속 부재"; canon_ok=0; }

    # 5d) 분해 공식 핵심 토큰 동기화 — phase1=환경설정(scaffold+venv), phase2=프론트, phase3=백엔드.
    grep -qiE 'scaffold' "$PLN" 2>/dev/null && grep -qiE 'venv' "$PLN" 2>/dev/null \
        || { echo "  ✗ 분해공식: planner.md phase1 에 scaffold/venv 부재"; canon_ok=0; }
    grep -qE 'phase1 = 환경설정' "$PLN" 2>/dev/null && grep -qiE 'phase2.*프론트' "$PLN" 2>/dev/null \
        && grep -qiE 'phase3.*백엔드' "$PLN" 2>/dev/null \
        || { echo "  ✗ 분해공식: planner.md phase 순서(환경설정/프론트/백엔드) 발산"; canon_ok=0; }
    grep -qE 'phase1 = 환경설정' "$PRC" 2>/dev/null && grep -qiE 'phase2 = 프론트' "$PRC" 2>/dev/null \
        && grep -qiE 'phase3.* = 백엔드' "$PRC" 2>/dev/null \
        || { echo "  ✗ 분해공식: PROCESS.md phase 순서(환경설정/프론트/백엔드) 발산"; canon_ok=0; }
    # reviewer 필수 (anti-drift: optional 로 돌아가면 reviewer 가 안 불린다 — 핵심 설계)
    grep -qE 'reviewer 호출 필수' "$PRC" 2>/dev/null \
        || { echo "  ✗ reviewer: PROCESS.md 에 'reviewer 호출 필수' 부재 (optional 드리프트)"; canon_ok=0; }
    grep -qE '\[review\]' "$PLN" 2>/dev/null \
        || { echo "  ✗ reviewer: planner.md 에 [review] task 백스톱 부재"; canon_ok=0; }
    # code-quality contract — authority exists and the two operative gates consume it.
    grep -qE 'improves or preserves code health' "$QLT" 2>/dev/null \
        || { echo "  ✗ quality: CODE_QUALITY.md 핵심 계약 부재"; canon_ok=0; }
    if ! { grep -qE 'Completion Evidence' "$DEV" 2>/dev/null \
        && grep -qE 'Changed:' "$DEV" 2>/dev/null \
        && grep -qE 'Tests:' "$DEV" 2>/dev/null \
        && grep -qE 'Existing pattern followed:' "$DEV" 2>/dev/null \
        && grep -qE 'Edge/risk considered:' "$DEV" 2>/dev/null \
        && grep -qE 'Rollback:' "$DEV" 2>/dev/null; }; then
        echo "  ✗ quality: developer.md 완료증거 5줄 게이트 부재"; canon_ok=0
    fi
    if ! { grep -qE 'Quality Classification Gate' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'BLOCKER' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'SHOULD' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'NIT' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'Approval requires' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null; }; then
        echo "  ✗ quality: reviewer.md BLOCKER/SHOULD/NIT 승인 게이트 부재"; canon_ok=0
    fi

    if [[ $canon_ok -eq 1 ]]; then echo "  ✓ RULE A/B + reviewer + quality 불변식 정합 (복사본 동기화 OK)"; else rc=1; fi

    echo "== doctor: $([[ $rc -eq 0 ]] && echo 'ALL CLEAN ✓' || echo 'FAIL ✗ (위 항목 수정 후 재실행)') =="
    return $rc
}

# Start CEO chat in the current shell. exec replaces this shell with claude.
# harnessd is spawned if missing so new-CTO detection works.
cmd_ceo() {
    if ! command -v claude >/dev/null 2>&1; then
        echo "error: 'claude' CLI not found in PATH" >&2
        return 1
    fi
    _ensure_harnessd
    local ceo_dir="$REPO/claude-project/ceo"
    mkdir -p "$ceo_dir"
    write_role_settings "$ceo_dir" "ceo"
    cd "$ceo_dir"
    export HARNESS_ROLE="ceo"
    cat <<'EOF'

================ CEO 채팅 시작 ================
환경: HARNESS_ROLE=ceo, harnessd alive.
첫 prompt 추천: "CEO 역할 인수. 상태 보고해줘."

이후엔 자연어로 시키기만 하면 됩니다.
예) "alpha 한테 회원가입 만들라고 해", "보고 왔어?",
    "CTO 두 명 띄워서 진행시켜줘"
==============================================
EOF
    exec claude
}

# 대시보드(웹 관리 콘솔) 기동/정지 — dev.sh 와 같은 detached up/down 패턴.
# backend(uvicorn main:app, 127.0.0.1:8165) + frontend(vite, 0.0.0.0:8166, /api 프록시).
cmd_dashboard() {
    local action="${1:-up}"
    local d="$REPO/dashboard" pidf="$REPO/dashboard/.dash.pids"
    case "$action" in
        up)
            [[ -f "$pidf" ]] && { echo "이미 실행중 — ./run.sh dashboard down 먼저"; return 1; }
            [[ -d "$d/backend/.venv" ]] || { echo "error: dashboard/backend/.venv 없음 — install 먼저 (python -m venv + pip install -r requirements.txt)"; return 1; }
            [[ -d "$d/frontend/node_modules" ]] || { echo "error: dashboard/frontend/node_modules 없음 — npm install 먼저"; return 1; }
            mkdir -p "$d/.dash-logs"
            setsid bash -c "cd '$d/backend' && source .venv/bin/activate && exec uvicorn main:app --host 127.0.0.1 --port 8165 --reload" >"$d/.dash-logs/backend.log" 2>&1 & echo $! >>"$pidf"
            setsid bash -c "cd '$d/frontend' && exec npm run dev" >"$d/.dash-logs/frontend.log" 2>&1 & echo $! >>"$pidf"
            echo "dashboard up — backend :8165, frontend :8166 (logs: dashboard/.dash-logs/)"
            if [[ -n "${DASH_TOKEN:-}" ]]; then
                echo "  제어 토큰 활성 (DASH_TOKEN 설정됨) — 웹에서 같은 토큰 입력 시 mutation 가능"
            else
                echo "  ⚠ DASH_TOKEN 미설정 → 제어 버튼(세션/dev/docker) 비활성(503). 활성화: DASH_TOKEN=<비밀> ./run.sh dashboard up"
            fi
            ;;
        down)
            [[ -f "$pidf" ]] || { echo "not running"; return 0; }
            while read -r pid; do kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done <"$pidf"
            rm -f "$pidf"; echo "dashboard down"
            ;;
        *) echo "usage: ./run.sh dashboard up|down" >&2; return 1 ;;
    esac
}

# git-listup — 대상 dir 의 git repo 에서 .gitignore 를 반영해 "업로드될 최상위
# 목록"을 출력. 업로드 대상 = tracked(디스크 존재) ∪ untracked-not-ignored.
# 삭제됐지만 tracked 인 파일은 제외(커밋하면 삭제로 기록되므로 repo 에 안 남음).
# harness 루트뿐 아니라 각 프로젝트/모듈 dir 에서도 동작 (그 repo 의 .gitignore 기준).
cmd_git_listup() {
    local arg="${1:-.}" target
    # bare name(슬래시 없음·'.' 아님) = 빌드 dir 이름 → claude-project/·modules/ 스캔
    # (add-cto 와 동일 resolve; 둘 다면 모호 에러). 경로/'.' 는 그대로.
    if [[ "$arg" == "." || "$arg" == */* || "$arg" == /* ]]; then
        target="$arg"
    else
        local hits=()
        [[ -d "$REPO/claude-project/$arg" ]] && hits+=("$REPO/claude-project/$arg")
        [[ -d "$REPO/modules/$arg" ]] && hits+=("$REPO/modules/$arg")
        if [[ ${#hits[@]} -eq 0 ]]; then
            echo "error: '$arg' — claude-project/·modules/ 둘 다 없음 (경로 직접 지정도 가능)" >&2; return 1
        elif [[ ${#hits[@]} -gt 1 ]]; then
            echo "error: '$arg' 가 claude-project/ 와 modules/ 양쪽 존재 — 전체 경로로 지정" >&2; return 1
        fi
        target="${hits[0]}"
    fi
    [[ -d "$target" ]] || { echo "error: 디렉토리 없음: $target" >&2; return 1; }
    (
        cd "$target" || exit 1
        git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
            || { echo "error: git repo 아님 ($target) — 'git init' 먼저" >&2; exit 1; }
        # 업로드 대상 파일 목록 (디스크 존재하는 것만 — 삭제 tracked 제외)
        local files
        files=$( { git ls-files; git ls-files --others --exclude-standard; } 2>/dev/null \
                 | sort -u | while IFS= read -r f; do [[ -e "$f" ]] && printf '%s\n' "$f"; done )
        echo "● 업로드 최상위 목록 ($(pwd))"
        echo
        echo "파일:"
        printf '%s\n' "$files" | awk -F/ 'NF==1 && $0!=""' | sed 's/^/  - /'
        echo
        echo "디렉토리:"
        printf '%s\n' "$files" | awk -F/ 'NF>1{print $1}' | sort -u | while IFS= read -r d; do
            [[ -n "$d" ]] || continue
            cnt=$(printf '%s\n' "$files" | awk -F/ -v D="$d" '$1==D' | grep -c . || true)
            other=$(printf '%s\n' "$files" | awk -F/ -v D="$d" '$1==D' | grep -vc '/\.gitkeep$' || true)
            if [[ "$other" -eq 0 ]]; then
                echo "  - $d/ (.gitkeep만 — 빈 폴더 유지)"
            else
                echo "  - $d/ ($cnt 파일)"
            fi
        done
    )
}

print_usage() {
    cat <<'EOF'
harness-claude — multi-agent control script

mental model:
  claude = process (one CEO or one CTO brain)
  tmux   = container (only CTOs are parked in tmux; CEO runs in your shell)
  CEO/CTO 터미널은 항상 독립 운영 (observe 폐기)

── 세션 기동 ──
  ./run.sh ceo                                     # CEO 활성화 (이 터미널에서)
  ./run.sh add-cto <name>                          # CTO 추가 (<name> 스캔 resolve; 경로형도 가능)
      # <name> = CEO 가 만든 빌드 dir 이름 → claude-project/·modules/ 중 하나로 resolve (둘 다면 에러).
      # 경로 직접: add-cto claude-project/<name>/plan.md | modules/<name>/plan.md
      # plan.md 없으면 스폰 실패 (1단계: CEO 창에서 /build-project | /build-module)
  ./run.sh attach-cto <name>                       # tmux attach (= attach cto-<name>)
  ./run.sh split-cto <name>                        # teammate 를 각자 tmux pane 으로 분리 (재기동; 되돌리기=add-cto)

── 조회 ──
  ./run.sh ls                                      # 세션 목록
  ./run.sh ports                                   # 포트 레지스트리 (docs/PORT.md)
  ./run.sh schema [<name>]                         # DB 스키마 현황 (테이블·컬럼, 읽기전용)
  ./run.sh git-listup [<name>|<dir>]               # 업로드될 최상위 목록 (.gitignore 반영). name=빌드dir 스캔(tunnel→claude-project/tunnel), 기본=현재 dir
  ./run.sh help

── 종료/삭제 ──
  ./run.sh down                  # 전 세션 kill + dev서버/워커 프로세스 + docker compose 컨테이너 정리
  ./run.sh stop-cto <name>       # 한 CTO 세션만 정지 (backend/frontend/compose/dir/specs/포트 모두 유지). 재개: add-cto
  ./run.sh delete-cto <name>     # CTO 완전 삭제 (세션+프로세스+compose 컨테이너+dir+sqlite+로그; 볼륨/이미지 보존)
  ./run.sh delete-cto --all

── 유틸 ──
  ./run.sh test-cto <name> [--max-turns N] "<prompt>"   # 비대화 한 방
  ./run.sh fetch <git-url>       # extract 소스 .sources/ shallow clone

── 점검 ──
  ./run.sh doctor                # 정합 검사 (하네스 수정 후 무조건)
  ./run.sh smoke                 # 결정론 스모크 (tests/smoke.sh)

── 대시보드 (웹 관리 콘솔) ──
  ./run.sh dashboard up          # backend :8165 + frontend :8166 기동 (detached)
  ./run.sh dashboard down        # 종료 (아무 터미널에서나)
      # 최초 1회 install: dashboard/frontend `npm install`,
      #   dashboard/backend `python -m venv .venv && .venv/bin/pip install -r requirements.txt`

note: ./run.sh down does NOT kill CEO — CEO is in your shell.
note: 빌드별 dev 서버는 각 빌드 dir 의 ./dev.sh up|down (run.sh 아님).
EOF
}

case "${1:-}" in
    "")        print_usage ;;
    ceo)       cmd_ceo ;;
    add-cto)   shift; cmd_add_cto "$@" ;;
    delete-cto) shift; cmd_delete_cto "$@" ;;
    stop-cto)  shift; cmd_stop_cto "$@" ;;
    split-cto) shift; cmd_split_cto "$@" ;;
    ports)     shift; cmd_ports "$@" ;;
    fetch)     shift; cmd_fetch "$@" ;;
    fetch-source) shift; cmd_fetch "$@" ;;   # 구명 호환
    test-cto)  shift; cmd_test_cto "$@" ;;
    ls)        cmd_ls ;;
    down)      cmd_down ;;
    attach)    shift; cmd_attach "$@" ;;
    attach-cto) shift; cmd_attach "cto-${1:?usage: $0 attach-cto <name>}" ;;
    doctor)    cmd_doctor ;;
    smoke)     bash "$REPO/tests/smoke.sh" ;;
    schema)    shift; python3 "$REPO/harness/schema_scan.py" "$@" ;;
    dashboard) shift; cmd_dashboard "$@" ;;
    git-listup) shift; cmd_git_listup "$@" ;;
    observe)   echo "observe 는 폐기됨 — CEO/CTO 터미널 독립 운영. ./run.sh attach cto-<name> 사용." >&2; exit 1 ;;
    -h|--help|help) print_usage ;;
    *) echo "unknown command: $1" >&2; print_usage >&2; exit 1 ;;
esac
