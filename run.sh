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
# Commands (새 체계 — plans/harness.md 정본):
#   ./run.sh ceo                              # start CEO chat (exec claude here)
#   ./run.sh add-cto <빌드dir>/plan.md         # spawn one CTO (plan.md 경로가 유일 인자;
#                                             # 부모 dir = 빌드타입(claude-project|modules),
#                                             # dir 이름 = CTO 이름. plan.md 없으면 실패)
#   ./run.sh attach cto-<name>                # tmux attach
#   ./run.sh test-cto <name> "<p>"            # non-interactive smoke test (claude --print)
#   ./run.sh ls / ports / help                # 조회
#   ./run.sh down                             # kill all sessions + dev서버/워커 프로세스 정리
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
  "teammateMode": "in-process",
  "model": "claude-opus-4-8",
  "effortLevel": "xhigh",
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

# Minimum Claude Code version — Agent Teams + /goal (autopilot, plans/harness.md).
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

cmd_add_cto() {
    # 새 시그니처 (plans/harness.md): 인자 1개 = plan.md 경로.
    #   ./run.sh add-cto claude-project/<name>/plan.md   # 프로젝트 빌드 CTO
    #   ./run.sh add-cto modules/<name>/plan.md          # 모듈 빌드 CTO
    # 부모 dir 가 빌드타입(축1)·CTO 이름·작업 dir 를 전부 확정한다.
    # plan.md 가 없으면 스폰 실패 (1단계 CEO plan 선행 강제 — fail-closed).
    local plan_arg="${1:?usage: $0 add-cto <claude-project|modules>/<name>/plan.md}"
    if [[ $# -gt 1 ]]; then
        echo "error: add-cto 는 인자 1개 (plan.md 경로). 구 --module/--plan 모드는 폐기됨." >&2
        return 1
    fi
    case "$plan_arg" in
        --module|--plan)
            echo "error: '$plan_arg' 모드는 폐기됨 — add-cto <빌드dir>/plan.md 로 호출." >&2
            echo "       모듈 재사용 = CEO plan.md 의 '## 3 Library Check' (RULES §7)." >&2
            return 1 ;;
    esac

    # 상대경로 허용 (repo 루트 기준) → 절대경로로.
    local plan_path="$plan_arg"
    [[ "$plan_path" != /* ]] && plan_path="$REPO/$plan_path"
    if [[ "$(basename "$plan_path")" != "plan.md" ]]; then
        echo "error: 인자는 plan.md 경로여야 함 (got: $plan_arg)" >&2
        return 1
    fi
    if [[ ! -f "$plan_path" ]]; then
        echo "error: plan.md not found: $plan_path" >&2
        echo "       1단계 먼저 — CEO 창에서 /build-project 또는 /build-module 로 plan.md 작성." >&2
        return 1
    fi

    local dir name base build_type
    dir="$(cd "$(dirname "$plan_path")" && pwd)"
    name="$(basename "$dir")"
    base="$(basename "$(dirname "$dir")")"
    case "$base" in
        claude-project) build_type="project" ;;
        modules)        build_type="module" ;;
        *)
            echo "error: plan.md 는 claude-project/<name>/ 또는 modules/<name>/ 아래 있어야 함 (got: $base/$name)" >&2
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

    # Auto-kickoff: /start-project 슬래시커맨드를 직접 타이핑 — 팀 spawn 의
    # 명시 트리거다 (harness-team-spawn "explicit user signal" 충족; add-cto
    # kickoff = 허용된 spawn 신호로 SKILL.md 에 문서화됨).
    ( sleep 12 && tmux send-keys -t "cto-$name" \
        "/start-project plan.md 분해 시작 (build_type=$build_type)" Enter ) &
    echo "auto-kickoff queued (typed in ~12s) — /start-project, build_type=$build_type"

    # Add a 6-line skill-activity tail pane at the bottom of the CTO session
    # so the ★ shows even when the user attaches directly (not via observe).
    mkdir -p "$HOME/.harness-claude"
    touch "$HOME/.harness-claude/skill-activity.log"
    if tmux has-session -t "=cto-$name" 2>/dev/null; then
        local win
        win=$(tmux list-windows -t "cto-$name" -F '#{window_index}' | head -1)
        if tmux list-panes -t "cto-$name" 2>/dev/null | grep -q 'tail'; then
            echo "skill-activity pane already present, skipping split"
        else
            tmux split-window -v -l 6 -t "cto-$name:${win}" \
              "printf '\\033[1m== skill activity (cto:${name}) ==\\033[0m\\n'; tail -n 20 -F $HOME/.harness-claude/skill-activity.log | grep --line-buffered -E '\\[cto:${name}\\]'"
            # return focus to the claude pane (top); pane index varies by tmux config
            tmux select-pane -t "cto-$name:${win}" -U 2>/dev/null || true
            # Set claude pane title so daemon's _find_by_pane_title('cto:NAME') can match.
            tmux select-pane -t "cto-$name" -T "cto:$name" 2>/dev/null || true
        fi
    fi

    echo "attach: tmux attach -t cto-$name"
}

# (observe 는 폐기됨 — CEO/CTO 터미널 독립 운영. plans/harness.md)

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
             plugins/_shared/RULES.md plugins/_shared/PROCESS.md plans/harness.md \
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

print_usage() {
    cat <<'EOF'
harness-claude — multi-agent control script (정본: plans/harness.md)

mental model:
  claude = process (one CEO or one CTO brain)
  tmux   = container (only CTOs are parked in tmux; CEO runs in your shell)
  CEO/CTO 터미널은 항상 독립 운영 (observe 폐기)

── 세션 기동 ──
  ./run.sh ceo                                     # CEO 활성화 (이 터미널에서)
  ./run.sh add-cto claude-project/<name>/plan.md   # 프로젝트 빌드 CTO
  ./run.sh add-cto modules/<name>/plan.md          # 모듈 빌드 CTO
      # plan.md 경로가 유일 인자 — 부모 dir=빌드타입, dir명=CTO 이름.
      # plan.md 없으면 스폰 실패 (1단계: CEO 창에서 /build-project | /build-module)
  ./run.sh attach cto-<name>                       # tmux attach 동일

── 조회 ──
  ./run.sh ls                                      # 세션 목록
  ./run.sh ports                                   # 포트 레지스트리 (docs/PORT.md)
  ./run.sh schema [<name>]                         # DB 스키마 현황 (테이블·컬럼, 읽기전용)
  ./run.sh help

── 종료/삭제 ──
  ./run.sh down                  # 전 세션 kill + dev서버/워커 프로세스 정리
  ./run.sh delete-cto <name>     # CTO 완전 삭제 (세션+프로세스+dir+sqlite+로그)
  ./run.sh delete-cto --all

── 유틸 ──
  ./run.sh test-cto <name> [--max-turns N] "<prompt>"   # 비대화 한 방
  ./run.sh fetch <git-url>       # extract 소스 .sources/ shallow clone

── 점검 ──
  ./run.sh doctor                # 정합 검사 (하네스 수정 후 무조건)
  ./run.sh smoke                 # 결정론 스모크 (tests/smoke.sh)

note: ./run.sh down does NOT kill CEO — CEO is in your shell.
EOF
}

case "${1:-}" in
    "")        print_usage ;;
    ceo)       cmd_ceo ;;
    add-cto)   shift; cmd_add_cto "$@" ;;
    delete-cto) shift; cmd_delete_cto "$@" ;;
    ports)     shift; cmd_ports "$@" ;;
    fetch)     shift; cmd_fetch "$@" ;;
    fetch-source) shift; cmd_fetch "$@" ;;   # 구명 호환
    test-cto)  shift; cmd_test_cto "$@" ;;
    ls)        cmd_ls ;;
    down)      cmd_down ;;
    attach)    shift; cmd_attach "$@" ;;
    doctor)    cmd_doctor ;;
    smoke)     bash "$REPO/tests/smoke.sh" ;;
    schema)    shift; python3 "$REPO/harness/schema_scan.py" "$@" ;;
    observe)   echo "observe 는 폐기됨 — CEO/CTO 터미널 독립 운영. ./run.sh attach cto-<name> 사용." >&2; exit 1 ;;
    -h|--help|help) print_usage ;;
    *) echo "unknown command: $1" >&2; print_usage >&2; exit 1 ;;
esac
