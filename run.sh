#!/usr/bin/env bash
# Harness control script.
#
# Mental model:
#   claude/codex = process (one agent brain)
#   Orca terminal = session keeper and process boundary
#
# CEO and each CTO run in Orca-managed terminals — they survive launcher-shell
# close and stop only through stop-ceo/stop-cto/down.
#
# 명령 목록 정본 = print_usage() (파일 하단) + docs/RUNSH-COMMANDS.txt (smoke 고정).
# 여기 헤더에 목록 사본을 두지 않는다 — 사본은 드리프트한다 (2026-07-28 감사에서
# 10개 커맨드 누락 상태로 발견돼 제거).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Exported so slash-command `!`-lines and spawned agents/teammates can resolve
# the harness root on any machine (replaces hardcoded absolute paths).
export HARNESS_ROOT="$REPO"

# Orca terminal identity (migration step 1).
#
# Runtime handles are intentionally NOT persisted: Orca may issue replacement
# handles after a runtime restart.  The durable harness identity is the exact,
# manually-renamed terminal title, and every operation re-resolves its current
# live handle through `terminal list`.
_orca_cli() {
    if [[ -n "${ORCA_CLI_COMMAND:-}" ]]; then
        "$ORCA_CLI_COMMAND" "$@"
    elif [[ -n "${ORCA_DEV_REPO_ROOT:-}" ]] && command -v orca-dev >/dev/null 2>&1; then
        orca-dev "$@"
    elif [[ "$(uname -s)" == "Linux" ]] && command -v orca-ide >/dev/null 2>&1; then
        # Outside an Orca-managed Linux terminal, bare `orca` is commonly the
        # GNOME screen reader.  orca-ide is the unambiguous product CLI.
        orca-ide "$@"
    else
        orca "$@"
    fi
}

# Orca CLI 의 --json 실패 응답에서 사람이 읽을 사유를 뽑는다. 응답은 비0 종료여도
# 본문에 `{"ok":false,"error":{"code":…,"message":…}}` 를 담고 있는데, 호출부가
# `|| return 1` 로 그 본문을 버리면 실패 이유가 통째로 사라진다 — 대시보드 CTO
# 실행 버튼이 "아무 일도 안 일어난 것처럼" 보이던 원인이 이것이었다 (2026-07-23:
# 빌드 dir 이 자기 git 저장소가 아니어서 워크스페이스가 없었고 Orca 는
# `selector_not_found` 로 정확히 알려줬는데 하네스가 그걸 버렸다).
# 파싱 실패해도 절대 죽지 않는다 — 원문 첫 줄로 폴백한다.
_orca_err() {
    python3 -c '
import json, sys
raw = sys.stdin.read()
try:
    err = json.loads(raw).get("error") or {}
    code, msg = err.get("code"), err.get("message")
except Exception:
    code = msg = None
if code and msg and msg != code:
    print(f"{code}: {msg}")
elif code or msg:
    print(code or msg)
else:
    print((raw.strip().splitlines() or ["(응답 없음)"])[0][:200])
' <<<"$1" 2>/dev/null || printf '(사유 파싱 실패)\n'
}

_orca_role_title() {
    local role="${1:-}"
    if [[ "$role" == "ceo" ]]; then
        printf 'harness:ceo\n'
        return 0
    fi
    if [[ "$role" =~ ^cto:[a-z0-9]+(-[a-z0-9]+)*:(lead|planner|designer|reviewer|codex)$ ]]; then
        printf 'harness:%s\n' "$role"
        return 0
    fi
    echo "error: invalid Orca harness role '$role'." >&2
    return 2
}

_orca_terminal_handle() {
    local title
    title=$(_orca_role_title "${1:-}") || return $?
    _orca_cli terminal list --limit 500 --json | python3 -c '
import json
import sys

title = sys.argv[1]
try:
    payload = json.load(sys.stdin)
    terminals = payload["result"]["terminals"]
except (KeyError, TypeError, ValueError) as exc:
    print(f"error: invalid Orca terminal list response: {exc}", file=sys.stderr)
    raise SystemExit(3)

matches = [
    terminal for terminal in terminals
    if terminal.get("title") == title
    and terminal.get("connected") is True
    and terminal.get("writable") is True
]
tabs = {terminal.get("tabId") for terminal in matches if isinstance(terminal.get("tabId"), str)}
if len(matches) == 1 and not tabs:
    # Compatibility with older Orca runtimes/test doubles without tabId.
    terminal = matches[0]
elif len(tabs) != 1:
    state = "not found" if not matches else f"ambiguous ({len(tabs)} live tabs)"
    print(f"error: Orca role {title!r} {state}.", file=sys.stderr)
    raise SystemExit(1 if not matches else 2)
else:
    # leafId==tabId 로 root leaf 를 고르던 분기 제거 (2026-07-31, orca 1.4.162
    # 실측): 이제 단일 pane 탭도 leafId 를 tabId 와 다른 uuid 로 발급하므로 그
    # 조건은 **절대 참이 되지 않는다** — 남겨두면 동작하는 가드처럼 읽히는
    # 죽은 코드다. 역할 pane 식별의 정본은 `terminal rename` 으로 박은 pane
    # title 이고, rail split pane 은 자기 쉘 OSC title 을 달아 이 title 과
    # 겹치지 않는다 (실측: split 직후 title=None → OSC, 탭 title 상속 없음).
    # 그래서 같은 탭에 같은 title leaf 가 2개면 리드를 특정할 근거가 없다 → fail closed.
    tab_id = next(iter(tabs))
    leaves = [terminal for terminal in matches if terminal.get("tabId") == tab_id]
    if len(leaves) != 1:
        print(f"error: Orca role {title!r} has no unique pane ({len(leaves)} leaves).",
              file=sys.stderr)
        raise SystemExit(3)
    terminal = leaves[0]
handle = terminal.get("handle")
if not isinstance(handle, str) or not handle.startswith("term_"):
    print(f"error: Orca role {title!r} returned an invalid handle.", file=sys.stderr)
    raise SystemExit(3)
print(handle)
' "$title"
}

_orca_create_terminal() {
    local role="${1:?role required}" command="${2:?command required}"
    local worktree="${3:-$REPO}"
    local title handle response rc
    title=$(_orca_role_title "$role") || return $?
    if handle=$(_orca_terminal_handle "$role" 2>/dev/null); then
        printf '%s\n' "$handle"
        return 0
    else
        rc=$?
        if [[ $rc -ne 1 ]]; then
            _orca_terminal_handle "$role" >/dev/null
            return $rc
        fi
    fi

    response=$(_orca_cli terminal create \
        --worktree "path:$worktree" --title "$title" --command "$command" --json) \
        || {
        echo "error: Orca terminal create 실패 ($title) — $(_orca_err "$response")" >&2
        echo "  worktree=$worktree" >&2
        echo "  selector_not_found 면 그 경로에 Orca 워크스페이스가 없다 — 빌드 dir 이" >&2
        echo "  자기 git 저장소 루트인지 확인 (orca worktree list --json)." >&2
        return 1
    }
    handle=$(python3 -c '
import json, sys
try:
    handle = json.load(sys.stdin)["result"]["terminal"]["handle"]
except (KeyError, TypeError, ValueError):
    raise SystemExit(1)
if not isinstance(handle, str) or not handle.startswith("term_"):
    raise SystemExit(1)
print(handle)
' <<<"$response") || {
        echo "error: Orca create returned no valid terminal handle for $title." >&2
        return 1
    }
    if ! _orca_cli terminal rename --terminal "$handle" --title "$title" --json >/dev/null; then
        # The terminal belongs to this failed create attempt; close it so an
        # unidentifiable agent process cannot survive outside role routing.
        _orca_cli terminal close --terminal "$handle" --json >/dev/null 2>&1 || true
        echo "error: failed to lock Orca terminal title $title." >&2
        return 1
    fi
    # create 응답의 surface/warning 은 버리지 않는다 (2026-07-31). Orca 데스크톱
    # 창이 없거나 UI 가 탭을 채택하지 못하면 터미널은 **뜨긴 하되**
    # `surface:"background"` 인 비가시 핸들로 만들어진다 (실측: 창 미개방 상태의
    # 프로브 2건 모두 background, visualLayouts groupId=headless-terminals).
    # ok:true 라 조용히 삼키면 add-cto 는 성공했는데 사용자 화면엔 CTO 탭이
    # 없다 — `_orca_err` 로 고친 "실패 본문 폐기" 와 같은 클래스의 침묵이다.
    # 자동으로 --focus 를 붙이진 않는다: create 가 여러 번 도는 경로에서
    # 포커스를 계속 빼앗는 쪽이 더 나쁘다. 알리고 판단은 사용자에게 남긴다.
    python3 -c '
import json, sys
try:
    terminal = json.load(sys.stdin)["result"]["terminal"]
except (KeyError, TypeError, ValueError):
    raise SystemExit(0)
if not isinstance(terminal, dict) or terminal.get("surface") != "background":
    raise SystemExit(0)
title, handle = sys.argv[1], sys.argv[2]
warning = terminal.get("warning") or "Orca UI did not adopt the terminal."
print(f"warning: {title} 이 비가시(background) 핸들로 생성됐다 — {warning}", file=sys.stderr)
print(f"  Orca 창을 연 뒤 드러내라: orca terminal focus --terminal {handle}", file=sys.stderr)
' "$title" "$handle" <<<"$response" || true
    printf '%s\n' "$handle"
}

_orca_rail_split() {
    # pane 을 분할하고 새 pane 의 handle 을 출력한다 (rail 체인용).
    local target="$1" direction="$2" command="$3" response
    response=$(_orca_cli terminal split --terminal "$target" \
        --direction "$direction" --command "$command" --json) || return 1
    python3 -c '
import json, sys
try:
    print(json.load(sys.stdin)["result"]["split"]["handle"])
except (KeyError, TypeError, ValueError):
    raise SystemExit(1)
' <<<"$response"
}

_orca_ensure_rail() {
    # CTO 콕핏 rail (specs/2026-07-29-cto-cockpit-rail-design.md):
    # lead 좌측 + 우측 세로 rail 4단 = ★skill / planner / designer / reviewer.
    # add-cto is intentionally resumable.  ★정정 (2026-07-31 실측, orca 1.4.162):
    # `terminal list` 는 split leaf 를 같은 tabId 의 **별도 레코드로 보여준다**
    # (안 보이는 건 `visualLayouts` 쪽뿐). 그럼에도 leaf 계수로 멱등을 판정할 수
    # 없는 이유는 따로다 — rail pane 은 자기 쉘 OSC title 을 달아 lead 의 durable
    # title 과 안 겹치고, 우리 목록 필터는 title 매치라 rail 이 걸러진다.
    # 그래서 pane 프로세스 pgrep 이 여전히 유일한 가드다. 어느 rail 프로세스든
    # 살아 있으면 전체를 건너뛴다 (기존 split handle 은 재조회 불가 → 부분 재구성 없음).
    local lead_handle="${1:?lead handle required}" name="${2:?cto name required}"
    local skill_log="$HOME/.harness-claude/skill-activity.log"
    mkdir -p "$(dirname "$skill_log")"
    touch "$skill_log"
    # 멱등 가드는 **skill 피드 프로세스 하나로만** 판정한다. 이유(2026-07-29 실측):
    # 사용자가 lead 탭을 닫으면 `tail|grep` 파이프라인은 탭과 함께 죽지만 python
    # 뷰어(teammate_tail)는 고아로 살아남는다. 예전처럼 둘 중 하나라도 살아있으면
    # skip 하면, 탭 복구 시 rail 이 재생성되지 않아 rail 없는 lead 가 뜬다.
    # skill 피드는 탭과 생사를 같이 하므로 탭 존재의 정확한 대리 신호다.
    # grep 은 쉘 alias 가 --color=auto 등을 끼워넣을 수 있어 옵션 나열을
    # 리터럴로 핀하지 않는다 (실측: `grep --color=auto --line-buffered -F ...`).
    if pgrep -f "grep .*\[cto:$name\]" >/dev/null 2>&1; then
        return 0
    fi
    # 고아 뷰어 정리 — 없으면 rail 재생성 때마다 화면 없는 python 이 누적된다.
    # 정확한 인자 패턴(스크립트 경로 + 이 CTO 이름)으로만 매칭한다.
    local orphan
    for orphan in $(pgrep -f "teammate_tail.py $name " 2>/dev/null); do
        kill "$orphan" 2>/dev/null || true
    done
    local skill_cmd viewer s p
    # skill 피드는 lead 팀 활동([cto:<name>]) + 독립 designer 세션 활동
    # ([designer-cto:<name>]) 둘 다 보여준다 (2026-07-29 designer 분리).
    printf -v skill_cmd 'tail -n 30 -F %q | grep --line-buffered -F -e %q -e %q' \
        "$skill_log" "[cto:$name]" "[designer-cto:$name]"
    s=$(_orca_rail_split "$lead_handle" vertical "$skill_cmd") || return 1
    # 체인: S 아래 planner → planner 아래 reviewer ⇒ skill ½ / planner ¼ /
    # reviewer ¼ 3단 (designer 는 독립 탭이라 rail 에서 제외 — 사용자 결정).
    printf -v viewer 'python3 %q %q planner' "$REPO/harness/teammate_tail.py" "$name"
    p=$(_orca_rail_split "$s" horizontal "$viewer") || return 1
    printf -v viewer 'python3 %q %q reviewer' "$REPO/harness/teammate_tail.py" "$name"
    _orca_rail_split "$p" horizontal "$viewer" >/dev/null || return 1
}

_orca_switch_role() {
    local handle
    handle=$(_orca_terminal_handle "${1:?role required}") || return $?
    _orca_cli terminal switch --terminal "$handle" --json >/dev/null
}

_orca_harness_terminals() {
    _orca_cli terminal list --limit 500 --json | python3 -c '
import json, re, sys
try:
    terminals = json.load(sys.stdin)["result"]["terminals"]
except (KeyError, TypeError, ValueError) as exc:
    print(f"error: invalid Orca terminal list response: {exc}", file=sys.stderr)
    raise SystemExit(1)
pattern = re.compile(
    r"harness:(ceo|cto:[a-z0-9]+(?:-[a-z0-9]+)*:"
    r"(?:lead|planner|designer|reviewer|codex|pending-[1-9][0-9]*))"
)
seen_tabs = set()
for terminal in terminals:
    title = terminal.get("title", "")
    handle = terminal.get("handle", "")
    tab_id = terminal.get("tabId") or handle
    # leafId==tabId 검사 제거 (2026-07-31): orca 1.4.162 부터 단일 pane 탭도
    # leafId 를 tabId 와 다른 uuid 로 발급 — 그 조건이면 전 세션이 탈락한다.
    # lead pane 선별은 title 정규식 + seen_tabs 중복제거로 이미 보장됨.
    if (pattern.fullmatch(title) and handle.startswith("term_")
            and terminal.get("connected") is True
            and terminal.get("writable") is True
            and isinstance(tab_id, str) and tab_id
            and tab_id not in seen_tabs):
        seen_tabs.add(tab_id)
        role = title.removeprefix("harness:")
        print(f"{role}\t{handle}")
'
}

_orca_register_project() {
    local dir="${1:?project dir required}" response existing_id
    # ★show-first (2026-07-29): 무조건 `repo add` 는 같은 경로 재등록마다 새
    # uuid 를 발급해 **이전 등록의 workspaceSession 키를 전부 고아로** 만든다
    # — 사이드바 "Unknown" 유령의 주 생산 라인이었다 (실측: 유령 17개 중
    # detection 6·keypoint 4 등 대부분이 add-cto 재실행분). 이미 등록된 경로는
    # 기존 id 를 그대로 재사용하고, 미등록일 때만 add 한다.
    existing_id=$(_orca_cli repo show --repo "path:$dir" --json 2>/dev/null | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
    repo = payload["result"]["repo"]
    rid, path = repo["id"], repo["path"]
except (KeyError, TypeError, ValueError):
    raise SystemExit(1)
if not isinstance(rid, str) or not rid or path != sys.argv[1]:
    raise SystemExit(1)
print(rid)
' "$dir" 2>/dev/null) && [[ -n "$existing_id" ]] && {
        echo "$existing_id"
        return 0
    }
    response=$(_orca_cli repo add --path "$dir" --json) || {
        echo "error: Orca Project 등록 실패 ($dir) — $(_orca_err "$response")" >&2
        return 1
    }
    python3 -c '
import json, sys
try:
    repo = json.load(sys.stdin)["result"]["repo"]
    repo_id = repo["id"]
    path = repo["path"]
except (KeyError, TypeError, ValueError):
    raise SystemExit(1)
if path != sys.argv[1] or not isinstance(repo_id, str) or not repo_id:
    raise SystemExit(1)
print(repo_id)
' "$dir" <<<"$response" || {
        echo "error: Orca Project registration returned an invalid path/id for $dir." >&2
        return 1
    }
}

_orca_unregister_project() {
    local dir="${1:?project dir required}" response repo_id rc
    response=$(_orca_cli repo show --repo "path:$dir" --json) || {
        echo "error: Orca Project 조회 실패 ($dir) — $(_orca_err "$response")" >&2
        return 1
    }
    if repo_id=$(python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(2)
if payload.get("ok") is False:
    error = payload.get("error") or {}
    if error.get("code") == "repo_not_found":
        raise SystemExit(10)
    raise SystemExit(2)
try:
    repo = payload["result"]["repo"]
    repo_id = repo["id"]
    path = repo["path"]
except (KeyError, TypeError):
    raise SystemExit(2)
if path != sys.argv[1] or not isinstance(repo_id, str) or not repo_id:
    raise SystemExit(2)
print(repo_id)
' "$dir" <<<"$response"); then
        rc=0
    else
        rc=$?
    fi
    if [[ $rc -eq 10 ]]; then
        echo "  - Orca Project not registered for $dir"
        return 0
    elif [[ $rc -ne 0 ]]; then
        echo "error: Orca Project lookup returned an invalid path/id for $dir." >&2
        return 1
    fi

    # 등록해제는 런타임 `repo.rm` 으로 한다 — CLI `project setup-delete` 가 아니다.
    # ★단, Orca ≤1.4.147 에서는 repo.rm 도 "Unknown" 유령을 만든다 (2026-07-29
    # 실측: repos 행은 지워지나 workspaceSession 7개 컬렉션의 `<uuid>::` 키가
    # 잔존 → 그 잔존 키가 worktreeMeta 를 재생성 → 사이드바 Unknown 부활).
    # 사용자가 장기간 고생한 유령의 근원이 바로 이 경로다. 벤더 소스
    # 1.4.151-rc.1 의 removeProject() 는 removeRepoFromWorkspaceSession() 으로
    # 전 컬렉션을 청소한다 — **근본 해결 = Orca 1.4.151+ 업데이트**, 그 전까지
    # 이 함수 실행(=delete-cto)마다 유령 1개가 남고, 청소는
    # scripts/orca-prune-ghosts.py --apply (Orca 완전 종료 후) 뿐이다.
    # ✅ 2026-07-31: 설치본이 1.4.162 로 올라갔고(removeRepoFromWorkspaceSession
    # 실재 확인) → **이 경로의 신규 유령 생산은 멈춤**. 업데이트 이전에 쌓인
    # 기존 유령은 여전히 prune-ghosts --apply 1회로만 걷힌다.
    # (2026-07-23 의 "repo.rm 은 소멸" 실측은 worktreeMeta 즉시값만 본 오판 —
    # 참조: .references/orca src/main/persistence.ts, profile-project-session-state.ts)
    response=$(python3 "$REPO/harness/orca_rpc.py" repo.rm "{\"repo\": \"id:$repo_id\"}" 2>&1) || {
        echo "error: Orca Project 등록해제 실패 ($repo_id / $dir) — $response" >&2
        return 1
    }
    python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
except (TypeError, ValueError):
    raise SystemExit(1)
if payload.get("removed") is not True:
    raise SystemExit(1)
' <<<"$response" || {
        echo "error: Orca Project unregister was not acknowledged for $dir." >&2
        return 1
    }
    echo "  ✓ unregistered Orca Project $repo_id ($dir) — worktree 메타까지 정리"
}

_orca_close_cto() {
    local name="${1:?name required}" records role handle closed=0
    # 순서 고정 (2026-07-29): terminal close 먼저, keeper kill 나중.
    # keeper 를 먼저 죽이면 그 시점 목록에서 죽은 터미널이 connected/writable
    # 필터에 탈락해 탭 close 를 건너뛰고, UI 에 "Remote runtime disconnected"
    # 카드 잔해만 남는다 (실측 재현). keeper 안의 agent 는 탭을 닫아도
    # 살아남으므로 close 뒤 keeper kill 은 여전히 필수다.
    # ★ 탭 close 실패로 **중단하지 않는다** (2026-08-02 실사고). 예전엔 첫 실패에서
    # `|| return 1` 로 빠져나가 아래 `_keeper_kill` 3개가 통째로 안 돌았다 — 즉
    # Orca 가 딸꾹질 한 번 하면 stop-cto 가 **아무것도 안 하고** 에이전트는 계속
    # 살아있었다(대시보드엔 사유 없는 "실패" 만). 실측 사인: 런타임 재시작 뒤
    # rtsp-streaming 3탭이 `terminal switch` 는 ok 인데 `terminal close` 만
    # `tab_not_found` 를 냈다 — 핸들은 유효한데 close 경로만 죽은 상태.
    # 정지의 본질은 **에이전트 프로세스 종료**지 탭 정리가 아니다. 탭이 안 닫히면
    # 사유를 찍고 계속 진행해 keeper 를 반드시 죽인 뒤, 마지막에 실패를 보고한다.
    local resp failed=0
    records=$(_orca_harness_terminals) || return 1
    while IFS=$'\t' read -r role handle; do
        [[ "$role" == "cto:$name:"* ]] || continue
        if resp=$(_orca_cli terminal close --terminal "$handle" --tab --json 2>&1); then
            echo "  ✓ closed Orca tab $role"
            closed=1
        else
            echo "  ⚠ Orca 탭 close 실패 ($role) — $(_orca_err "$resp")" >&2
            echo "    에이전트는 아래 keeper kill 로 정지한다. 탭 잔해는 Orca 에서 수동으로 닫아라." >&2
            failed=1
        fi
    done <<< "$records"
    [[ $closed -eq 1 || $failed -eq 1 ]] || echo "  - Orca terminals for cto:$name not running"
    _keeper_kill "cto-$name-lead"
    _keeper_kill "cto-$name-codex"
    _keeper_kill "cto-$name-designer"
    # rail pane 프로세스도 직접 걷는다 (2026-08-04 실사고). 탭 close 가 성공하면
    # skill 피드(grep)는 탭과 함께 죽지만, close 가 tab_not_found 로 실패하면
    # **살아남는다** — 그러면 다음 스폰에서 `_orca_ensure_rail` 의 pgrep 멱등
    # 가드("skill 피드 생존 = rail 존재")가 유령을 보고 split 을 통째로 건너뛰어
    # rail 없는 맨몸 lead 가 뜬다 (rtsp-streaming 실측). 정지의 본질 = 프로세스
    # 종료 — keeper 와 같은 급으로 여기서 확정 처리한다. close 성공 경로에선
    # 이미 죽어 있어 no-op (멱등). 패턴은 ensure_rail 가드·고아 정리와 동일 리터럴.
    local pane
    for pane in $(pgrep -f "grep .*\[cto:$name\]" 2>/dev/null); do
        kill "$pane" 2>/dev/null || true
    done
    for pane in $(pgrep -f "teammate_tail.py $name " 2>/dev/null); do
        kill "$pane" 2>/dev/null || true
    done
    return $failed
}

# close 가 거부한 유령 레코드를 역할 네임스페이스 밖으로 밀어낸다 (2026-08-04).
# 왜 필요한가: `_orca_create_terminal` 은 같은 role title 이 이미 있으면 그 핸들을
# **재사용**한다 (add-cto 멱등성의 근거). 그런데 close 실패 뒤에는 keeper 는 죽고
# 레코드만 connected 로 남은 상태라, 그 재사용이 "죽은 탭을 살아있는 세션으로
# 착각" 시킨다 — 재기동이 create 를 한 번도 안 부르고 조용히 끝난다(실측: 결함주입
# 스모크에서 create 0회). 타이틀을 벗기면 유령은 매칭에서 탈락하고 create 가 새
# 탭을 연다. 잔해 탭은 남지만, 그건 사용자가 닫을 수 있는 문제고 죽은 CTO 는 아니다.
_orca_retire_stale_role_terminals() {
    local name="${1:?name required}" records role handle retired=0
    records=$(_orca_harness_terminals) || return 0
    while IFS=$'\t' read -r role handle; do
        [[ "$role" == "cto:$name:"* ]] || continue
        if _orca_cli terminal rename --terminal "$handle" \
                --title "stale:$role" --json >/dev/null 2>&1; then
            retired=1
        else
            echo "  ⚠ 유령 탭 타이틀 해제 실패 ($role) — 재기동이 죽은 탭을 재사용할 수 있다." >&2
            echo "    Orca 를 재시작한 뒤 다시 실행해라." >&2
        fi
    done <<< "$records"
    [[ $retired -eq 1 ]] && echo "  ✓ 유령 탭을 역할에서 분리 (stale:cto:$name:*) — 새 탭으로 재기동"
    return 0
}

# Per-role .claude/settings.json + slash-command symlinks + (for CTO) agent
# definitions + team rules.
# role is 'ceo' or 'cto' (template lookup under plugins/$role/).
write_role_settings() {
    local target_dir="$1"
    local role="$2"
    # CTO uses in-process Agent Teams: the main Orca view remains lead + skill
    # activity and teammates are selected from the lead view.
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
    # 3-teammate Claude team; production developer is the external Codex
    # session. CEO gets the librarian (사서). A one-shot Task
    # subagent only needs the agent .md here — Agent Teams env not required.
    if compgen -G "$REPO/plugins/$role/agents/*.md" > /dev/null; then
        rm -rf "$target_dir/.claude/agents"
        mkdir -p "$target_dir/.claude/agents"
        for f in "$REPO/plugins/$role/agents"/*.md; do
            [[ "$role" == "cto" && "$(basename "$f")" == "developer.md" ]] && continue
            # designer 는 독립 designer-cto 세션으로 분리 (2026-07-29) — 팀
            # teammate 로 설치하지 않는다 (developer 와 동일한 tombstone).
            [[ "$role" == "cto" && "$(basename "$f")" == "designer.md" ]] && continue
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

        # settings.json — Agent Teams enabled, in-process teammate display, team hooks,
        # harness repo granted as additional directory so symlinked plugin
        # files (agents/*, rules/*, commands/*) are readable without a per-file
        # permission prompt.
        cat > "$target_dir/.claude/settings.json" <<JSON
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  },
  "teammateMode": "$teammate_mode",
  "model": "claude-opus-5",
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
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/start_project_gate.py"
          },
          {
            "type": "command",
            "command": "python3 $REPO/hooks/inbox_isolation_clear.py"
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
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/start_project_spawn_nudge.py"
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
        "matcher": "Workflow",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/skill_announce.py"
          }
        ]
      },
      {
        "matcher": "Write",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/spec_overwrite_gate.py"
          },
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/phase2_viewable_gate.py"
          }
        ]
      },
      {
        "matcher": "Write|Edit|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/plan_readonly_gate.py"
          },
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/tasks_md_review_gate.py"
          }
        ]
      },
      {
        "matcher": "SendMessage",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/sendmessage_recipient_gate.py"
          }
        ]
      },
      {
        "matcher": "Agent",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/start_project_gate.py"
          },
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/one_teammate_per_role_gate.py"
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/git_guard.py"
          },
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/spec_overwrite_gate.py"
          }
        ]
      },
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/inbox_isolation_guard.py"
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
  "model": "claude-opus-5",
  "statusLine": {
    "type": "command",
    "command": "python3 $REPO/hooks/cto_statusline.py"
  },
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
          },
          {
            "type": "command",
            "command": "python3 $REPO/hooks/inbox_isolation_clear.py"
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
      },
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 $REPO/hooks/inbox_isolation_guard.py"
          }
        ]
      }
    ]
  }
}
JSON
    fi
}

# Spawn an Orca-managed Claude terminal with HARNESS_ROLE set.
# Claude CEO/CTO sessions launch with --dangerously-skip-permissions so they
# can act without Write/Edit/Bash approval dialogs. Codex CTO uses the Codex
# equivalent in _start_codex_cto.
start_session() {
    local name="$1"
    local cwd="$2"
    local role="$3"
    local orca_role command handle
    if [[ "$role" != cto:* ]]; then
        echo "error: start_session expects cto:<name>, got '$role'." >&2
        return 2
    fi
    orca_role="$role:lead"
    # lead 대화 복원 (2026-07-28) — CEO 와 동일한 세션 id 파일 방식.
    # 팀원(planner/designer/reviewer)은 별도 세션이라 복원되지 않는다 — lead 만
    # 이어지고, 팀은 /start-project 로 재spawn 한다. stop-cto 는 재개 전제라
    # id 파일을 유지하고, delete-cto 만 지운다.
    local resume_str inner
    resume_str=$(_claude_resume_args \
        "$HOME/.harness-claude/cto-session-${role#cto:}.id" "$cwd")
    # 순수 claude 기동 (2026-07-29, A안): `orca claude-teams` 래퍼는 teammate
    # 마다 native split 을 강제로 열어 lead 탭이 leaf 5+개로 불어난다. Agent
    # Teams 런타임은 settings.json 의 env+teammateMode 로 동일하게 동작하고,
    # teammate 열람은 lead 내부 목록(in-process)으로 한다 — 07-23 잠금 설계
    # ("main view = CTO + skill activity 2 pane") 그대로.
    printf -v inner 'cd %q && exec env HARNESS_ROOT=%q HARNESS_ROLE=%q HARNESS_CTO_DIR=%q claude %s--dangerously-skip-permissions' \
        "$cwd" "$REPO" "$role" "$cwd" "$resume_str"
    command=$(_keeper_wrap "cto-${role#cto:}-lead" "$inner")
    handle=$(_orca_create_terminal "$orca_role" "$command" "$cwd") || return 1
    if [[ -n "$resume_str" ]]; then
        echo "  lead 이전 대화 복원 (${resume_str% }) — 팀원은 복원 안 됨, 첫 지시 턴에 자동 재spawn (마커 시딩)"
    fi
    # start_session's display name is `cto-<name>`; skill log tags use only
    # the canonical CTO name (`[cto:<name>]`).
    _orca_ensure_rail "$handle" "${role#cto:}" || return 1
    echo "Orca terminal ready: $name role=$role handle=$handle cwd=$cwd"
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

# Keep the legacy inbox daemon alive through its user service during migration.
# There is deliberately no legacy multiplexer fallback: Orca is the session keeper.
# Step 4 removes this daemon when routing moves to Orca orchestration.
_ensure_harnessd() {
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl --user is-active --quiet harnessd.service 2>/dev/null; then
            echo "harnessd: alive (user service; routing migration pending)"
            return 0
        fi
        if systemctl --user start harnessd.service 2>/dev/null; then
            echo "started harnessd user service (routing migration pending)"
            return 0
        fi
    fi
    echo "warning: harnessd user service unavailable; queued inbox wake is disabled until step 4." >&2
    return 0
}

# install-services — Orca 런타임(orca-harness) + harnessd 를 systemd user 서비스로
# 설치/갱신한다. 부팅 자동시작의 정본은 이제 repo(infra/systemd/*.tmpl)다 —
# 2026-07-22 에 서버 로컬에만 손으로 깔린 유닛을 재현 가능하게 편입한 것.
# 부팅 체인: linger → systemd --user → default.target → orca-harness → harnessd.
# 포트/pairing 주소는 ~/.config/harness-claude/orca-server.env 가 유일 소스 (하드코딩 금지).
_render_service_tmpl() { # <tmpl> <dest>  — @…@ 치환 후 잔존 플레이스홀더면 실패
    sed -e "s|@HOME@|$HOME|g" \
        -e "s|@HARNESS_ROOT@|$REPO|g" \
        -e "s|@SERVICE_PATH@|$_SVC_PATH|g" \
        -e "s|@PYTHON3@|$_SVC_PYTHON3|g" \
        "$1" > "$2" || return 1
    if grep -qE '@[A-Z0-9_]+@' "$2"; then
        echo "error: 미치환 플레이스홀더 잔존: $(grep -oE '@[A-Z0-9_]+@' "$2" | sort -u | tr '\n' ' ')($1)" >&2
        return 1
    fi
}
cmd_install_services() {
    local dry=0 port="" pairing=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry=1; shift ;;
            --port) port="${2:?--port 값 필요}"; shift 2 ;;
            --pairing-address) pairing="${2:?--pairing-address 값 필요}"; shift 2 ;;
            *) echo "usage: $0 install-services [--dry-run] [--port N] [--pairing-address ADDR]" >&2; return 1 ;;
        esac
    done
    # 서비스 PATH — 설치 머신의 실존 경로만으로 조립 (유닛에 남의 환경 하드코딩 방지).
    _SVC_PATH="$HOME/.local/bin"
    [[ -d "$HOME/.pyenv/shims" ]] && _SVC_PATH="$_SVC_PATH:$HOME/.pyenv/shims"
    local node_bin
    node_bin=$(command -v node 2>/dev/null) && _SVC_PATH="$_SVC_PATH:$(dirname "$node_bin")"
    _SVC_PATH="$_SVC_PATH:/usr/local/bin:/usr/bin:/bin"
    # pyenv shim 우선 — command -v 는 셸에 따라 anaconda 등 임의 python 을 잡아
    # 데몬이 남의 env 수명에 묶인다. shim 없을 때만 PATH 해석.
    if [[ -x "$HOME/.pyenv/shims/python3" ]]; then
        _SVC_PYTHON3="$HOME/.pyenv/shims/python3"
    else
        _SVC_PYTHON3=$(command -v python3) || { echo "error: python3 없음" >&2; return 1; }
    fi

    local tmpl_dir="$REPO/infra/systemd" dest_dir
    if [[ $dry -eq 1 ]]; then
        dest_dir=$(mktemp -d)
        _render_service_tmpl "$tmpl_dir/orca-harness.service.tmpl" "$dest_dir/orca-harness.service" || { rm -rf "$dest_dir"; return 1; }
        _render_service_tmpl "$tmpl_dir/harnessd.service.tmpl" "$dest_dir/harnessd.service" || { rm -rf "$dest_dir"; return 1; }
        echo "== dry-run: 렌더 결과 (설치 안 함) =="
        cat "$dest_dir/orca-harness.service" "$dest_dir/harnessd.service"
        rm -rf "$dest_dir"
        return 0
    fi

    command -v systemctl >/dev/null 2>&1 || { echo "error: systemctl 없음 — systemd 환경에서만 설치 가능" >&2; return 1; }

    # env 파일 — 없으면 --port/--pairing-address 필수. 있으면 보존(플래그 주면 재작성).
    local env_file="$HOME/.config/harness-claude/orca-server.env"
    if [[ -n "$port" || -n "$pairing" ]]; then
        [[ -n "$port" && -n "$pairing" ]] || { echo "error: --port 와 --pairing-address 는 함께 지정" >&2; return 1; }
        mkdir -p "$(dirname "$env_file")"
        # 재작성이어도 ORCA_SERVE_EXTRA_ARGS 는 보존한다 — env 파일이 serve 플래그의
        # 유일 소스라 여기서 날리면 --mobile-pairing 이 조용히 사라진다(포트만 바꿔도).
        local extra=""
        extra=$(grep -m1 '^ORCA_SERVE_EXTRA_ARGS=' "$env_file" 2>/dev/null || true)
        (umask 077
         printf 'ORCA_PORT=%s\nORCA_PAIRING_ADDRESS=%s\n' "$port" "$pairing" > "$env_file"
         [[ -n "$extra" ]] && printf '%s\n' "$extra" >> "$env_file"
         true)
        echo "wrote $env_file"
    elif [[ ! -f "$env_file" ]]; then
        echo "error: $env_file 없음 — 최초 설치는 --port N --pairing-address ADDR 필요" >&2
        return 1
    fi

    dest_dir="$HOME/.config/systemd/user"
    mkdir -p "$dest_dir"
    _render_service_tmpl "$tmpl_dir/orca-harness.service.tmpl" "$dest_dir/orca-harness.service" || return 1
    _render_service_tmpl "$tmpl_dir/harnessd.service.tmpl" "$dest_dir/harnessd.service" || return 1
    systemctl --user daemon-reload || return 1
    systemctl --user enable --now orca-harness.service harnessd.service || return 1
    echo "installed+enabled: orca-harness.service harnessd.service (실행 중이던 서비스는 그대로 유지 — 유닛 변경 반영은 다음 (재)시작)"

    # linger 없으면 로그인 전까지 systemd --user 가 안 떠서 부팅 자동시작이 안 된다.
    if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" != "yes" ]]; then
        if loginctl enable-linger "$USER" 2>/dev/null; then
            echo "linger 활성화됨 — 로그인 없이도 부팅 시 자동시작"
        else
            echo "warning: linger 비활성 — 부팅 자동시작하려면: sudo loginctl enable-linger $USER" >&2
            return 1
        fi
    else
        echo "linger: 이미 활성 (부팅 시 로그인 없이 자동시작)"
    fi
}

# 빌드 dir 스폰 가능 검사. plan.md(1단계 신규) **또는** specs/tasks.md(분해 완료 —
# plan 없이 재개) 가 있으면 OK. specs 존재 = 이미 plan 이 있었음을 증명하므로
# fail-closed(§7 plan 선행) 유지 — 둘 다 없는 빈 dir 만 거부.
_build_ready() { [[ -d "$1" ]] && { [[ -f "$1/plan.md" ]] || [[ -f "$1/specs/tasks.md" ]]; }; }

# 카메라 프로젝트의 mediamtx self-host 포트를 .env 에 박는다 (RULES §4/§4.1) —
# backend/frontend 포트와 같은 offset 규율의 연장. 포트 3줄(add-cto flock 블록)
# 다음 단계로, 값 = 시작포트 + (PORT_OFFSET − 1) = base+offset.
#
# db 배선(DATABASE_URL 등)은 여기서 하지 않는다 (2026-07-23 결정): 공유 pg 에 실제
# db 를 만드는 부수효과가 있는데 회수는 `harness db drop`(가드 대상) — 만들기는
# 자동, 치우기는 수동인 비대칭이 생긴다. 게다가 대부분 빌드는 DATABASE_URL 부재 시
# sqlite 폴백으로 도는 구조라(backend/app/database.py) 자동 주입이 오히려 동작을
# 조용히 바꾼다. db 는 필요하다고 판단됐을 때 `harness db env`/`db provision` 으로.
#
# ⚠ 카메라 게이트를 절대 걷어내지 마라 — 전 프로젝트 무조건 주입이 2026-07-21
# 사고였다(RULES §15). 판별은 CEO 가 plan.md 에 선언한 mediamtx 시그널
# (비카메라 plan.md 는 이 리터럴이 0건). tests/smoke.sh [add-cto-wire] 가 핀한다.
_wire_project_env() {
    local dir="$1" env="$1/.env" offset
    [[ -f "$env" ]] || return 0
    offset="$(sed -n 's/^PORT_OFFSET=\([0-9]\{1,\}\)$/\1/p' "$env" | head -1)"
    [[ -n "$offset" ]] || return 0
    grep -qi mediamtx "$dir/plan.md" 2>/dev/null || return 0

    {
        echo "MEDIAMTX_API_PORT=$((9997 + offset))"
        echo "MEDIAMTX_RTSP_PORT=$((8554 + offset))"
        echo "MEDIAMTX_WEBRTC_PORT=$((8889 + offset))"
        echo "MEDIAMTX_ICE_UDP_PORT=$((8189 + offset))"
    } >> "$env"
    harness ports --quiet 2>/dev/null || true
    echo "mediamtx: self-host 포트 4줄 (카메라 시그널 감지 — API $((9997 + offset)))"
}

cmd_add_cto() {
    # 시그니처: <name> (CEO 가 만든 빌드 dir 이름) 또는 plan.md 경로/빌드 dir 1개.
    #   ./run.sh add-cto <name>                          # claude-project/·modules/ 스캔해 resolve
    #   ./run.sh add-cto claude-project/<name>/plan.md   # 경로 직접 지정도 가능
    # 분해는 자동 시작 안 함 — attach 후 /model·/effort 고르고 첫 지시로 시작
    # (시작 마커는 add-cto 가 심는다 — /start-project 타이핑 불필요).
    # 부모 dir 가 빌드타입(축1)·CTO 이름·작업 dir 를 전부 확정한다.
    # 스폰 가능 = plan.md(1단계 신규) 또는 specs/tasks.md(분해 완료 → plan 없이 재개);
    # 둘 다 없으면 실패 (fail-closed). 인자: 위치 인자 1개 + 선택 --fresh.
    # --fresh = CEO --fresh 의 CTO 대응: Claude lead 대화만 새로 시작 (복원 id
    # 폐기). 빌드 dir/스펙/서버/Codex 대화는 유지 — 전부 버리는 건 delete-cto.
    local fresh=0 plan_arg="" _a
    for _a in "$@"; do
        case "$_a" in
            --fresh) fresh=1 ;;
            *)
                if [[ -n "$plan_arg" ]]; then
                    echo "error: add-cto 는 위치 인자 1개 (+선택 --fresh)." >&2
                    return 1
                fi
                plan_arg="$_a" ;;
        esac
    done
    if [[ -z "$plan_arg" ]]; then
        echo "usage: $0 add-cto <name> | <claude-project|modules>/<name>/plan.md [--fresh]" >&2
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
    if ! command -v codex >/dev/null 2>&1; then
        echo "error: 'codex' command not found — add-cto requires both Claude and Codex." >&2
        return 1
    fi
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
        # 카메라면 mediamtx 포트 4줄을 이어서 (lock 밖 — .env 는 이미 이 프로젝트 것으로 확정).
        _wire_project_env "$dir"
    fi

    # 표준 dev.sh 시딩 (2026-08-04, 사용자 결정 — dev.sh 재발명 차단).
    # phase1 이 백지에서 새로 쓰다 규격 미달(quote-editor 14줄 foreground 사고)이
    # 나던 걸, 템플릿 복사로 태어날 때부터 규격화한다. CTO 는 상단 가변부
    # (project_services/pre_up/post_down)만 채운다. 기존 dev.sh 는 안 덮는다.
    if [[ ! -f "$dir/dev.sh" && -f "$REPO/harness/templates/dev.sh" ]]; then
        cp "$REPO/harness/templates/dev.sh" "$dir/dev.sh"
        chmod +x "$dir/dev.sh"
        echo "dev.sh: 표준 템플릿 시딩 (가변부만 채우면 됨 — RULES §13·§5.5)"
    fi

    # /start-project 자동 신호 (2026-08-04, 사용자 결정 — 리셋에서 시딩으로 반전).
    # add-cto 가 시작 마커를 **미리 심는다**: start_project_gate 의 팀 spawn 게이트가
    # 열린 채 뜨고, Stop-훅(start_project_spawn_nudge)이 첫 턴 종료부터 로스터
    # 완성(planner+reviewer)을 압박한다 → 사용자가 /start-project 를 타이핑하지
    # 않아도 attach 후 첫 지시 턴에 팀이 뜬다. /model·/effort 조정 window 는 유지
    # (빈 프롬프트 대기 + 자동 kickoff 없음은 그대로). 알려진 트레이드: 사용자
    # 아닌 stray 턴이 기본 model/effort 로 조기 스폰할 수 있음 — 사용자가 명시
    # 수용했다. /start-project 커맨드는 수동 재신호용으로 유지된다.
    # 매 스폰마다 새로 쓰므로 예전 "stale 마커" 문제(S38)는 정의상 소멸 — 마커는
    # 항상 이번 스폰의 신호다. 이전 회차 spawn claim 은 지운다 (팀원은 lead 와
    # 함께 죽었는데 claim 이 남으면 one_teammate_per_role 게이트가 재스폰을 중복
    # 스폰으로 오판해 차단한다 — /start-project 프롬프트 경로가 하던 정리와 동일).
    mkdir -p "$HOME/.claude/logs/started"
    printf '%s\n' "$name" > "$HOME/.claude/logs/started/$(printf '%s' "$name" | tr -c 'A-Za-z0-9._-' '_').started"
    rm -f "$HOME/.harness-claude/orca-team-spawn-claims/$name"/{planner,designer,reviewer}.claimed 2>/dev/null || true

    # Orca Project 신원 = git repo 경계. 빌드 dir 에 자체 .git 이 없으면 부모
    # harness-claude repo 신원으로 등록돼 워크트리가 없고, 이어지는 terminal
    # create 가 selector_not_found 로 죽는다(대시보드 CTO 버튼 무음 실패). 커밋 0
    # 인 빈 init 만으로 kind=git 등록이 성립한다(rtsp-detection/keypoint 실증).
    # 가드가 .git 부재일 때만 돌므로 최초 add-cto 한 번만 init 하고, 재스폰(완성
    # 후 stop-cto→add-cto 재개)에서는 .git 이 남아 있어 건너뛴다. 커밋·push 는
    # 여기서 하지 않는다 — 여전히 사용자 전용(RULES §1). 만드는 건 빈 저장소뿐이다.
    if [[ ! -e "$dir/.git" ]]; then
        git -C "$dir" init -q -b main \
            || { echo "error: git 저장소 초기화 실패 ($dir)" >&2; return 1; }
        echo "git: 빈 저장소 초기화 ($dir) — 커밋 없음 (최초 add-cto 1회)"
    fi

    local orca_project_id
    orca_project_id=$(_orca_register_project "$dir") || return 1
    echo "Orca Project ready: $name id=$orca_project_id path=$dir"

    write_role_settings "$dir" "cto" "in-process"

    if [[ $fresh -eq 1 ]]; then
        # 돌던 세션을 닫고 복원 id 를 버린다 → lead 가 새 대화로 뜬다.
        # Codex 는 건드리지 않는다 (production 맥락 보존; resume 은 cwd 발굴).
        # ★ 반환값을 반드시 삼킨다 (2026-08-04 실사고). _orca_close_cto 는 탭 close
        # 실패를 **보고용 반환값**으로 올린다 (2026-08-02 설계) — stop/delete 는 그걸
        # 받아 멈추는 게 맞지만, fresh 는 정반대다. 가드 없이 부르면 `set -e` 가
        # add_cto 를 여기서 중단시켜 keeper 3개는 이미 죽고 재기동(start_session·
        # codex·designer)은 하나도 안 돈다 = **"CTO 실행(fresh)" 이 CTO 를 죽이기만
        # 함**. 실측: Orca 런타임/UI 가 갈라진 순간 3역할 전부 tab_not_found → 대시보드
        # 실패 + rtsp-streaming keeper 전멸. 탭 잔해는 재기동을 막을 이유가 못 된다.
        _orca_close_cto "$name" || {
            echo "--fresh: 탭 잔해 있음 (사유는 위) — 재기동은 그대로 진행한다." >&2
            _orca_retire_stale_role_terminals "$name"
        }
        rm -f "$HOME/.harness-claude/cto-session-$name.id" \
              "$HOME/.harness-claude/cto-designer-session-$name.id"
        # 기억 소멸 일관성: 콕핏 rail 이 이전 세션 잔재를 보여주면 안 된다.
        # skill-activity 는 이 CTO 줄을 지우고(delete-cto 와 같은 패턴), teammate
        # 뷰어에는 fresh 경계 시각을 남겨 그 이전 전사를 무시하게 한다.
        [[ -f "$HOME/.harness-claude/skill-activity.log" ]] \
            && sed -i "/\[cto:$name\]/d" "$HOME/.harness-claude/skill-activity.log"
        # 경계 ts 는 Claude 뷰어와 codex 세션 발굴(_codex_resume_args)이 공유한다
        # — 이 이전의 codex rollout 은 다시는 resume 되지 않는다 (codex 도 fresh).
        date +%s > "$HOME/.harness-claude/cto-fresh-$name.ts"
        # claude↔codex 상호 메시지 내역 삭제 (대시보드 mission control 모달의
        # 그 내역). CEO↔CTO 메시지는 남긴다 — 페어 대화만 fresh 대상.
        local fresh_db="$HOME/.harness-claude/db.sqlite"
        [[ -f "$fresh_db" ]] && sqlite3 "$fresh_db" \
            "DELETE FROM msg WHERE (from_role='cto:$name' AND to_role IN ('codex-cto:$name','designer-cto:$name')) OR (from_role IN ('codex-cto:$name','designer-cto:$name') AND to_role='cto:$name')"
        echo "--fresh: Claude·Codex 대화 + 페어 메시지 내역 폐기 (빌드/스펙 유지) — 새 세션으로 시작"
    fi
    start_session "cto-$name" "$dir" "cto:$name" || return 1
    _start_codex_cto_session "$name" "$dir" || return 1
    _start_designer_cto_session "$name" "$dir" || return 1

    # 분해는 자동 시작하지 않는다 — CTO 세션을 빈 claude 프롬프트로 띄워두고,
    # 사용자가 attach 후 /model·/effort 를 고른 뒤 첫 작업 지시를 준다. 시작
    # 마커는 add-cto 가 이미 심었으므로(위) 첫 지시 턴에 팀이 자동 스폰된다 —
    # /start-project 타이핑 불필요 (수동 재신호용으로는 유지). send-keys
    # auto-kickoff 는 여전히 폐기 상태다 — 턴 자체는 사용자가 연다.
    echo "CTO 세션 대기 중 — 분해 자동 시작 안 함 (build_type=$build_type, 디렉토리가 확정)."
    echo "  다음: ./run.sh attach-cto $name → /model · /effort 설정 → 바로 작업 지시 (팀 자동 스폰, /start-project 불필요)"

    echo "attach Claude:   ./run.sh attach-cto $name"
    echo "attach Codex:    ./run.sh attach-codex-cto $name"
    echo "attach Designer: ./run.sh attach-designer-cto $name"
}

# Designer 독립 세션 (2026-07-29 designer 분리 — specs/2026-07-29-designer-cto-
# split-design.md). codex 와 동일한 same-name pair 직군이되 Claude 로 뜬다.
# role 주입은 SessionStart 훅이 HARNESS_ROLE=designer-cto:<name> 을 보고
# plugins/designer-cto/role.md 를 넣는다. 대화 복원 = 세션 id 파일 (lead 와
# 같은 방식; stop-cto 유지 / --fresh·delete-cto 만 폐기).
_start_designer_cto_session() {
    local name="${1:?name required}" dir="${2:?dir required}"
    local resume_str inner command handle
    resume_str=$(_claude_resume_args \
        "$HOME/.harness-claude/cto-designer-session-$name.id" "$dir")
    printf -v inner 'cd %q && exec env HARNESS_ROOT=%q HARNESS_ROLE=%q HARNESS_CTO_DIR=%q claude %s--dangerously-skip-permissions' \
        "$dir" "$REPO" "designer-cto:$name" "$dir" "$resume_str"
    command=$(_keeper_wrap "cto-$name-designer" "$inner")
    handle=$(_orca_create_terminal "cto:$name:designer" "$command" "$dir") || return 1
    if [[ -n "$resume_str" ]]; then
        echo "  designer 이전 대화 복원 (${resume_str% })"
    fi
    echo "Orca Designer terminal ready: cto:$name:designer handle=$handle cwd=$dir"
}

# Start the interactive Codex half of one logical CTO. Orca first writes
# its status hooks to hooks.json; the terminal command then folds those plus
# the harness safety hooks into config.toml before Codex reads either source.
_ensure_codex_hooks() {
    python3 "$REPO/harness/codex_hooks.py" preflight --repo "$REPO"
}

_activate_codex_hooks() {
    python3 "$REPO/harness/codex_hooks.py" activate --repo "$REPO"
}

# Codex 대화 복원 인자 (2026-07-28) — codex 는 세션을 ~/.codex/sessions/ 에
# 전역 저장하고 meta 에 cwd 를 남긴다. `resume --last` 는 cwd 무관 전역 최신이라
# CTO 가 여럿이면 남의 세션을 물어온다 → cwd 정확 매칭으로 발굴한다.
# 가드: 빌드 dir 의 .git 생성시각(birth)보다 오래된 세션은 무시 — delete-cto 후
# 같은 이름으로 재생성했을 때 옛 빌드의 대화가 새 빌드에 스미는 것을 막는다.
# stdout = "resume <id> " 또는 빈 문자열 (codex 는 서브커맨드라 플래그 앞에 온다).
_codex_resume_args() {
    local dir="${1:?dir required}" birth fresh_ts
    birth=$(stat -c %W "$dir/.git" 2>/dev/null || echo 0)
    [[ "$birth" =~ ^[0-9]+$ ]] || birth=0
    # add-cto --fresh 경계 — fresh 이전의 codex 세션도 폐기 대상 (Claude 와 동일
    # 의미). 경계보다 오래된 rollout 은 .git-birth 가드와 같은 축으로 무시한다.
    fresh_ts=$(cat "$HOME/.harness-claude/cto-fresh-$(basename "$dir").ts" 2>/dev/null || echo 0)
    [[ "$fresh_ts" =~ ^[0-9]+$ ]] || fresh_ts=0
    [[ "$fresh_ts" -gt "$birth" ]] && birth=$fresh_ts
    python3 - "$dir" "$birth" <<'PY' 2>/dev/null
import json, os, sys
target, birth = sys.argv[1], int(sys.argv[2])
root = os.path.expanduser("~/.codex/sessions")
candidates = []
for base, _dirs, files in os.walk(root):
    for f in files:
        if f.startswith("rollout-") and f.endswith(".jsonl"):
            p = os.path.join(base, f)
            try:
                candidates.append((os.stat(p).st_mtime, p))
            except OSError:
                pass
candidates.sort(reverse=True)
for mtime, p in candidates[:100]:
    if birth and mtime < birth:
        continue
    try:
        with open(p, encoding="utf-8") as fh:
            meta = json.loads(fh.readline())
    except (OSError, ValueError):
        continue
    payload = meta.get("payload") or {}
    sid = payload.get("session_id") or payload.get("id")
    if payload.get("cwd") == target and isinstance(sid, str) and sid:
        print(f"resume {sid} ", end="")
        break
PY
}

_start_codex_cto_session() {
    local name="$1"
    local dir="$2"
    _ensure_codex_hooks || return 1
    mkdir -p -m 700 "$HOME/.harness-claude"
    # Keep the model configurable through the user's Codex config. Inject only
    # the durable role entrypoint; the role then reads shared RULES/PROCESS.
    local instruction_arg
    instruction_arg="developer_instructions=\"You are this build's Codex developer. Before any work, read and follow $REPO/plugins/codex-cto/role.md. Do not perform planner, designer, or reviewer work.\""
    local codex_cmd handle resume_str inner
    resume_str=$(_codex_resume_args "$dir")
    printf -v inner 'cd %q && python3 %q activate --repo %q && exec env HARNESS_ROOT=%q HARNESS_ROLE=%q codex %s--dangerously-bypass-hook-trust --dangerously-bypass-approvals-and-sandbox --add-dir %q -c %q' \
        "$dir" "$REPO/harness/codex_hooks.py" "$REPO" "$REPO" \
        "codex-cto:$name" "$resume_str" "$HOME/.harness-claude" "$instruction_arg"
    codex_cmd=$(_keeper_wrap "cto-$name-codex" "$inner")
    handle=$(_orca_create_terminal "cto:$name:codex" "$codex_cmd" "$dir") || return 1
    echo "Orca Codex terminal ready: cto:$name:codex handle=$handle cwd=$dir"
    if [[ -n "$resume_str" ]]; then
        echo "  codex 이전 세션 복원 (${resume_str% })"
    fi
}

cmd_attach_codex_cto() {
    local name="${1:?usage: $0 attach-codex-cto <name>}"
    if [[ $# -gt 1 ]]; then
        echo "error: attach-codex-cto takes exactly one <name>." >&2
        return 1
    fi
    if ! [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: name must be kebab-case (lowercase, digits, hyphens)." >&2
        return 1
    fi
    if [[ "$name" == "ceo" ]]; then
        echo "error: 'ceo' is reserved — not a CTO." >&2
        return 1
    fi
    if ! _orca_switch_role "cto:$name:codex"; then
        echo "error: Codex CTO Orca terminal 'cto:$name:codex' is not running." >&2
        echo "       Start it first: ./run.sh add-cto $name" >&2
        return 1
    fi
    echo "focused Orca terminal: harness:cto:$name:codex"
}

cmd_attach_designer_cto() {
    local name="${1:?usage: $0 attach-designer-cto <name>}"
    if [[ $# -gt 1 ]]; then
        echo "error: attach-designer-cto takes exactly one <name>." >&2
        return 1
    fi
    if ! [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: name must be kebab-case (lowercase, digits, hyphens)." >&2
        return 1
    fi
    if [[ "$name" == "ceo" ]]; then
        echo "error: 'ceo' is reserved — not a CTO." >&2
        return 1
    fi
    if ! _orca_switch_role "cto:$name:designer"; then
        echo "error: Designer Orca terminal 'cto:$name:designer' is not running." >&2
        echo "       Start it first: ./run.sh add-cto $name" >&2
        return 1
    fi
    echo "focused Orca terminal: harness:cto:$name:designer"
}

# Non-interactive smoke test for a CTO sandbox. Sends a prompt to a fresh
# claude --print invocation in the CTO's sandbox dir with HARNESS_ROLE set,
# token-bounded by --max-turns (default 10). For real interactive work use
# `./run.sh attach-cto <name>` instead.
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
    local records
    records=$(_orca_harness_terminals) || return 1
    if [[ -z "$records" ]]; then
        echo "(no live harness Orca terminals)"
        return 0
    fi
    printf '%-38s %s\n' ROLE HANDLE
    while IFS=$'\t' read -r role handle; do
        printf '%-38s %s\n' "$role" "$handle"
    done <<< "$records"
}

# Internal: kill every process tied to the project dir — (a) cmdline 이 그
# 경로를 포함하거나 (b) cwd 가 그 dir 아래인 프로세스 (vite 워커처럼 argv 에
# 경로가 없는 자식까지). terminal close만으론 dev 서버가 살아남아 디렉토리를
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
# survive a terminal close + pkill (rtsp 부활 사고, 2026-06-12: 삭제된 빌드의
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

    # Close exact role-owned Orca terminals before destructive directory
    # cleanup so an old agent cannot outlive and recreate the build.
    _orca_close_cto "$name" || return 1
    # ★ Orca Project 등록은 **일부러 남긴다** (2026-07-23, 실측으로 뒤집힌 결정).
    # 앱이 떠 있는 동안 외부에서 등록을 지우면 `worktreeMeta` 항목이 남아 사이드바에
    # 이름 없는 "Unknown" 프로젝트가 생기고, 그건 어느 경로로도 못 지운다:
    # repo 가 사라져 `worktree rm`=repo_not_found, main 워크트리라 --force 도 거부,
    # 상태파일 직접 편집은 런타임이 되덮음. 런타임 `repo.rm`(= UI 삭제가 쓰는 경로)로
    # 지우면 3초간은 깨끗해지지만 **렌더러가 10초 안에 되살린다** — 터미널을 전부
    # 닫고 해도 마찬가지다(실측). 즉 앱 구동 중 완전 제거는 UI 설정 화면에서만 가능하다.
    # 남겨두면 항목이 "이름 있는 정상 프로젝트" 로 유지돼 사용자가 설정에서 지울 수
    # 있다 — 지우려다 못 지우는 유령을 만드는 것보다 낫다.
    # (제거가 필요하면: Orca 설정 → 프로젝트 목록에서 삭제.
    #  오프라인 일괄 정리는 `scripts/orca-prune-ghosts.py --apply`, 앱 종료 후.)
    echo "  - Orca Project 등록 유지 ($dir) — 지우려면 Orca 설정에서 (구동 중 외부 삭제는 Unknown 유령을 남긴다)"

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

    # 세션 복원 id — delete 는 기억까지 버리는 유일한 경로 (stop-cto 는 유지).
    rm -f "$HOME/.harness-claude/cto-session-$name.id"
    rm -f "$HOME/.harness-claude/cto-designer-session-$name.id"
    rm -f "$HOME/.harness-claude/cto-fresh-$name.ts"

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
#   - live Orca terminals titled harness:cto:<name>:<member>
#   - sqlite roles matching cto:*
#   - skill-activity log entries tagged [cto:<name>]
_list_all_cto_names() {
    {
        for base in claude-project; do
            ls -1 "$REPO/$base" 2>/dev/null | grep -v '^ceo$' || true
        done
        _orca_harness_terminals 2>/dev/null \
          | awk -F '\t' '$1 ~ /^cto:/ { split($1, p, ":"); print p[2] }' || true
        sqlite3 "$HOME/.harness-claude/db.sqlite" \
          "SELECT DISTINCT substr(from_role,5) FROM msg WHERE from_role LIKE 'cto:%' \
           UNION SELECT DISTINCT substr(to_role,5) FROM msg WHERE to_role LIKE 'cto:%'" 2>/dev/null || true
        grep -oE '\[cto:[a-z0-9-]+\]' "$HOME/.harness-claude/skill-activity.log" 2>/dev/null \
          | sed -E 's/^\[cto:([a-z0-9-]+)\]$/\1/' || true
    } | sort -u | sed '/^$/d'
}

# Remove every trace of a CTO: Orca terminals, sandbox dir, sqlite rows,
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

# stop-cto — 한 CTO 의 **Claude+Codex 세션만** 정지. delete-cto 와 달리
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
    # 역할 소유 Orca terminal만 닫는다. dev 서버/워커/compose는 건드리지 않는다.
    _orca_close_cto "$name" || return 1
    if [[ -n "$dir" ]]; then
        echo "재개: ./run.sh add-cto ${dir#"$REPO"/}/plan.md"
    else
        echo "재개: ./run.sh add-cto <빌드dir>/plan.md"
    fi
}

cmd_down() {
    # Close every role-owned CTO terminal. CEO remains alive; only stop-ceo
    # may discard that conversation. Unrelated Orca terminals are untouched.
    local records role handle closed=0
    records=$(_orca_harness_terminals) || return 1
    while IFS=$'\t' read -r role handle; do
        [[ "$role" == cto:* ]] || continue
        _orca_cli terminal close --terminal "$handle" --tab --json >/dev/null || return 1
        echo "closed Orca tab $role"
        closed=1
    done <<< "$records"
    if [[ $closed -eq 0 ]]; then
        echo "no harness CTO terminals running"
    else
        echo "all harness CTO terminals closed"
    fi
    # CTO keeper 전수 정리 — 탭만 닫으면 keeper 뒤 agent 가 유령으로 남는다.
    # 소켓 파일 글롭이 유일한 열거 경로. CEO keeper(ceo.sock)는 down 대상이
    # 아니므로 cto- 접두만.
    local sock
    for sock in "$HOME/.harness-claude/keeper/cto-"*.sock; do
        [[ -S "$sock" ]] || continue
        _keeper_kill "$(basename "$sock" .sock)"
        echo "  ✓ killed keeper $(basename "$sock")"
    done
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
    local session="${1:?usage: $0 attach <session>}"
    local role name
    case "$session" in
        ceo) role="ceo" ;;
        codex-cto-*)
            name="${session#codex-cto-}"
            role="cto:$name:codex" ;;
        cto-*)
            name="${session#cto-}"
            role="cto:$name:lead" ;;
        *)
            echo "error: attach expects ceo, cto-<name>, or codex-cto-<name>." >&2
            return 1 ;;
    esac
    if [[ "$role" != "ceo" && ! "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
        echo "error: invalid CTO session '$session'." >&2
        return 1
    fi
    _orca_switch_role "$role" || return 1
    echo "focused Orca terminal: $(_orca_role_title "$role")"
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
             hooks/inbox_isolation_guard.py hooks/inbox_isolation_clear.py \
             plugins/_shared/RULES.md plugins/_shared/PROCESS.md plugins/_shared/CODE_QUALITY.md \
             plugins/ceo/commands/build-project.md plugins/ceo/commands/build-module.md \
             plugins/cto/commands/start-project.md \
             plugins/cto/commands/decompose.md \
             plugins/cto/agents/planner.md plugins/cto/agents/designer.md \
             plugins/designer-cto/role.md \
             plugins/cto/agents/reviewer.md \
             plugins/codex-cto/role.md \
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

    # 5) canon 정합성 (RULE A/B) — Claude 역할 지침과 외부 Codex 역할 지침의
    #    phase 공식 슬라이스가 PROCESS/RULES 와 발산하지 않게 강제한다.
    echo "--- [5] canon 정합성 (RULE A/B) ---"
    local PLN="$REPO/plugins/cto/agents/planner.md"
    local DEV="$REPO/plugins/codex-cto/role.md"
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
        echo "  ✗ quality: codex-cto/role.md 완료증거 5줄 게이트 부재"; canon_ok=0
    fi
    if ! { grep -qE 'Quality Classification Gate' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'BLOCKER' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'SHOULD' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'NIT' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null \
        && grep -qE 'Approval requires' "$REPO/plugins/cto/agents/reviewer.md" 2>/dev/null; }; then
        echo "  ✗ quality: reviewer.md BLOCKER/SHOULD/NIT 승인 게이트 부재"; canon_ok=0
    fi

    # 5e) hybrid team composition — two Claude teammates (designer 는 2026-07-29
    # 독립 세션 분리) + one external Codex. ★2026-08-04 감사: 이 검사가 designer
    # 분리 후에도 'Exactly 3' 을 핀한 채 초록이었다 — start-project.md 의 stale
    # "3" 잔재가 검사를 통과시키는 false-green 상호의존. 불변식은 2가 정본이고,
    # 3 잔재가 되살아나면 아래 negative grep 이 잡는다.
    local START="$REPO/plugins/cto/commands/start-project.md"
    local SPAWN="$REPO/plugins/cto/skills/harness-team-spawn/references/spawn-prompt.md"
    grep -qE 'EXACTLY 2|Exactly 2|정확히 2' "$START" "$SPAWN" 2>/dev/null \
        || { echo "  ✗ hybrid team: start-project/spawn prompt 에 Claude 2명 불변식 부재"; canon_ok=0; }
    grep -qE 'EXACTLY 3|Exactly 3|정확히 3|세 명|세 teammate|three Claude teammates' "$START" "$SPAWN" 2>/dev/null \
        && { echo "  ✗ hybrid team: 3-teammate 잔재 부활 (designer 분리 이전 문구)"; canon_ok=0; }
    grep -qE 'codex-cto-<name>|codex-cto-\{\{name\}\}' "$START" "$DEV" 2>/dev/null \
        || { echo "  ✗ hybrid team: 외부 codex-cto 세션 참조 부재"; canon_ok=0; }
    grep -q 'basename "\$f").*developer.md.*continue' "$REPO/run.sh" 2>/dev/null \
        || { echo "  ✗ hybrid team: Claude developer agent 설치 제외 배선 부재"; canon_ok=0; }

    if [[ $canon_ok -eq 1 ]]; then echo "  ✓ RULE A/B + reviewer + quality 불변식 정합 (복사본 동기화 OK)"; else rc=1; fi

    # [6] CEO terminal presence — advisory (rc 불변). Orca's public terminal
    # metadata has no creation timestamp, so age checks use our start marker.
    # smoke 의 doctor [5] 슬라이스(/[5] canon/,/== doctor:/)에 포함되므로 ⚠/✓/· 만 emit.
    echo "--- [6] CEO Orca terminal (advisory) ---"
    if _orca_terminal_handle ceo >/dev/null 2>&1; then
        echo "  ✓ CEO Orca terminal 살아있음"
    else
        echo "  · CEO Orca terminal 없음 — 스킵"
    fi

    # [7] 부팅 자동시작 — advisory (rc 불변, ⚠/✓/· 만 emit: smoke 의 [5] 슬라이스에 포함).
    # Orca 가 안 뜨면 하네스 전체가 조용히 멈추므로 유닛/linger 상태를 노출한다.
    echo "--- [7] 부팅 자동시작 orca-harness/harnessd (advisory) ---"
    if command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1; then
        local svc
        for svc in orca-harness harnessd; do
            if systemctl --user is-enabled --quiet "$svc.service" 2>/dev/null; then
                echo "  ✓ $svc.service enabled$(systemctl --user is-active --quiet "$svc.service" 2>/dev/null && echo ' + active' || echo ' (inactive)')"
            else
                echo "  ⚠ $svc.service 미설치/disabled — ./run.sh install-services"
            fi
        done
        if [[ "$(loginctl show-user "$USER" -p Linger --value 2>/dev/null)" == "yes" ]]; then
            echo "  ✓ linger 활성 (로그인 없이 부팅 자동시작)"
        else
            echo "  ⚠ linger 비활성 — 부팅 자동시작 안 됨: sudo loginctl enable-linger $USER"
        fi
    else
        echo "  · systemd user 세션 없음 — 스킵"
    fi

    # [8] 미소비 리뷰 리포트 — advisory (rc 불변). 리뷰를 생산은 하는데 소비를
    # 안 하면(=.pending 이 안 지워지면) 치명 지적이 조용히 방치된다. 실제로
    # codex-protocol-review 2026-07-23 리포트(치명 1·중대 4)가 나흘째 미소비였다.
    echo "--- [8] 미소비 리뷰 리포트 (advisory) ---"
    local pend found=0
    while IFS= read -r pend; do
        [[ -n "$pend" ]] || continue
        found=1
        local age_d
        age_d=$(( ( $(date +%s) - $(stat -c %Y "$pend" 2>/dev/null || echo 0) ) / 86400 ))
        echo "  ⚠ ${age_d}일째 미소비: ${pend#$HOME/}"
    done < <(find "$HOME/.harness-claude/reviews" -name '.pending' -type f 2>/dev/null)
    [[ $found -eq 0 ]] && echo "  ✓ 미소비 리뷰 없음" \
        || echo "    → 리포트를 읽고 처리한 뒤 소비하라 (\`/codex-review <p> --consume\` 등)"

    # advisory 인 이유: 위반은 빌드 dir 소유물이고 고치는 주체는 그 CTO 다. 하네스
    # doctor 가 FAIL 로 잠그면 무관한 하네스 작업까지 막힌다. 커밋은 어차피 사용자
    # 전용(§1)이라 시간도 있다 — 여기 역할은 "첫 커밋 전에 눈에 띄게" 까지다.
    echo "--- [9] 빌드 저장소 경계 (RULES §16, advisory) ---"
    local giout
    if giout=$(python3 "$REPO/harness/gitignore_scan.py" 2>&1); then
        echo "  ✓ §16 A 목록이 올라감에 없음 (전 빌드)"
    else
        printf '%s\n' "$giout" | grep -E '^■.*✗|^   ✗' | sed 's/^/  /'
        echo "    → 고치기: ./run.sh git-listup <name> 확인 후 그 빌드 .gitignore 에 추가"
    fi

    # 탭↔프로세스 어긋남. advisory 인 이유: 둘 다 사용자 개입(Orca 재시작 / 세션
    # 정지)이 필요한 상태지 하네스가 자동으로 고칠 것이 아니다. 판정(logical_sessions)
    # 은 이미 이 어긋남을 걸러내지만, 걸러진다고 사라지지는 않으므로 눈에 띄게 둔다.
    echo "--- [10] Orca 탭 ↔ 에이전트 정합 (advisory) ---"
    python3 - "$REPO" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
try:
    from harness import orca_runtime as o
    d = o.drift()
except Exception as exc:                      # Orca 미실행 등 — 진단을 막지 않는다
    print(f"  ⚠ 확인 불가: {exc}")
    raise SystemExit(0)
if not d["ghost_tab"] and not d["orphan_agent"]:
    print("  ✓ 탭과 에이전트가 일치")
    raise SystemExit(0)
for k in d["ghost_tab"]:
    print(f"  ⚠ 유령 탭: {k} — 탭은 있는데 에이전트 없음")
if d["ghost_tab"]:
    print("    → 화면엔 안 보여도 런타임 목록에 남는다. Orca 탭을 닫거나")
    print("      `systemctl --user restart orca-harness` (전 터미널 드랍) 로 정리.")
for k in d["orphan_agent"]:
    print(f"  ⚠ 고아 에이전트: {k} — 프로세스는 도는데 붙을 탭 없음")
if d["orphan_agent"]:
    print("    → 화면 없이 파일을 쓰고 토큰을 태운다. `./run.sh stop-cto <name>` 로 정지.")
PY

    echo "== doctor: $([[ $rc -eq 0 ]] && echo 'ALL CLEAN ✓' || echo 'FAIL ✗ (위 항목 수정 후 재실행)') =="
    return $rc
}

# Start/focus the Orca-owned CEO chat so it survives launcher-shell close;
# revisit via ./run.sh ceo, kill only via ./run.sh stop-ceo.
# harnessd is spawned if missing so new-CTO detection works.
# 대화 복원 인자 (2026-07-28) — pty 가 죽어도(밤새 소멸·재부팅·탭 닫기)
# 트랜스크립트는 디스크에 남는다. SessionStart 훅이 적어둔 세션 id 로 이어 붙인다.
# 없는 id 로 `--resume` 하면 claude 가 "No conversation found" 로 exit 1 → 터미널이
# 그대로 죽으므로, 트랜스크립트 파일이 실재할 때만 붙인다.
# stdout = command 에 이어붙일 인자 문자열(없으면 빈 문자열), stderr = 사람용 note.
_claude_resume_args() {
    local sid_file="${1:?session id file required}" dir="${2:?project dir required}" sid
    [[ -f "$sid_file" ]] || return 0
    sid=$(tr -d '[:space:]' < "$sid_file")
    [[ -n "$sid" ]] || return 0
    if [[ -f "$HOME/.claude/projects/${dir//[\/_.]/-}/$sid.jsonl" ]]; then
        printf -- '--resume %q ' "$sid"
    else
        echo "note: 기록된 세션($sid)의 트랜스크립트가 없어 새 대화로 시작한다." >&2
    fi
}

_ceo_resume_args() {
    _claude_resume_args "$HOME/.harness-claude/ceo-session.id" "${1:?ceo dir required}"
}

# 터미널 keeper (2026-07-28) — Orca 는 클라이언트 연결이 끊기면 서버 쪽 pty 를
# SIGHUP 으로 죽인다 (실측: 14:33 재연결 웨이브, tailscale 경로 유실과 동기).
# 탭 명령을 dtach keeper 로 감싸면 pty 가 죽어도 agent 프로세스는 keeper 뒤에서
# 생존하고, Orca 재스폰(pendingActivationSpawn)이 같은 명령을 재실행하면
# `dtach -A` 가 기존 프로세스에 재접속한다 — 실행 중이던 턴까지 안 끊긴다.
# 백엔드는 dtach 단독 (설치: scripts/install-dtach.sh, sudo 불필요) —
# 멀티플렉서는 사용자 지시로 전면 금지(2026-07-28). dtach 는 세션/
# 프리픽스/상태바 개념이 없는 78KB attach 프록시라 그 사고 클래스 자체가 없다.
# 소켓은 반드시 $HOME 아래 — 전역 /tmp 소켓을 쓰면 HOME 을 격리한 테스트(smoke
# stop-ceo)가 실 keeper 를 참수한다 (2026-07-28 실사고: smoke 가 자기를 낳은
# CEO keeper 를 죽여 CEO 가 smoke 도중 즉사, exit 137 ×2).
# 소켓 파일은 재부팅에도 남지만 stale 이면 -A 가 지우고 새로 만든다 → 그때는
# --resume 이 대화를 복원한다 (2중 방어).
_keeper_sock() {
    printf '%s' "$HOME/.harness-claude/keeper/${1:?role required}.sock"
}

# stdout = keeper 로 감싼 최종 명령. $1=역할(소켓명), $2=안에서 돌릴 셸 명령.
# -E 분리키 비활성(순수 껍데기), -z 서스펜드키 비활성, -r winch TUI 재그리기.
_keeper_wrap() {
    local role="${1:?role required}" inner="${2:?inner command required}"
    mkdir -p "$HOME/.harness-claude/keeper"
    printf '%q -A %q -E -z -r winch bash -c %q' \
        "$HOME/.local/bin/dtach" "$(_keeper_sock "$role")" "$inner"
}

# keeper 종료 = 소켓을 쥔 master 를 죽인다 (안의 agent 는 pty 상실로 함께 종료).
# fuser 가 소켓 소유 프로세스를 정확히 조준한다 — 이름 기반 pkill 금지(RULES §12).
_keeper_kill() {
    local sock
    sock=$(_keeper_sock "${1:?role required}")
    [[ -S "$sock" ]] && fuser -k -TERM "$sock" >/dev/null 2>&1 || true
    rm -f "$sock"
}

cmd_ceo() {
    if ! command -v claude >/dev/null 2>&1; then
        echo "error: 'claude' CLI not found in PATH" >&2
        return 1
    fi
    # --fresh: 기존 CEO 세션(맥락 부패)을 kill 하고 새 대화로 시작 — 하이진 finding #1.
    # 대화 기억이 소멸하므로 명시 플래그로만. stop-ceo 는 idempotent (세션 없으면 무해).
    if [[ "${1:-}" == "--fresh" ]]; then
        cmd_stop_ceo
    fi
    _ensure_harnessd
    local ceo_dir="$REPO/claude-project/ceo"
    mkdir -p "$ceo_dir"
    write_role_settings "$ceo_dir" "ceo"
    # CEO도 CTO와 동일하게 하네스 운영 명령을 권한 프롬프트 없이 수행한다.
    local command handle existed=0
    _orca_terminal_handle ceo >/dev/null 2>&1 && existed=1

    local resume_str inner
    resume_str=$(_ceo_resume_args "$ceo_dir")
    printf -v inner 'cd %q && exec env HARNESS_ROLE=ceo claude %s--dangerously-skip-permissions' \
        "$ceo_dir" "$resume_str"
    command=$(_keeper_wrap ceo "$inner")
    handle=$(_orca_create_terminal ceo "$command") || return 1
    if [[ "$existed" == "0" ]]; then
        mkdir -p "$HOME/.harness-claude"
        date +%s > "$HOME/.harness-claude/ceo-session.started"
    fi
    _orca_cli terminal switch --terminal "$handle" --json >/dev/null || return 1
    echo "CEO Orca terminal 준비·focus 완료 (handle=$handle)."
    if [[ "$existed" == "0" && -n "$resume_str" ]]; then
        echo "  이전 대화 복원 (${resume_str% })"
    fi
    echo "  창을 닫아도 Orca runtime에서 유지 · 재접속=./run.sh ceo · 종료(기억 소멸)=./run.sh stop-ceo"
}

# stop-ceo — CEO Orca terminal을 닫는다. CTO의 stop-cto와 동형: agent
# 프로세스)만 내리고 대화 기억을 버린다. 다음 ./run.sh ceo 는 새 대화로 시작.
# Orca 창만 닫으면 runtime terminal은 살아있다 — 잊고 싶을 때만 이걸 쓴다.
cmd_stop_ceo() {
    local handle rc
    # 기억 소멸의 정본 = 세션 id 파일 삭제. 터미널이 이미 없어도 지운다 —
    # 안 지우면 다음 `./run.sh ceo` 가 --resume 으로 버리려던 대화를 되살린다.
    rm -f "$HOME/.harness-claude/ceo-session.id"
    # keeper 안의 claude 는 탭을 닫아도 살아남는다 — stop 은 keeper 부터 죽인다.
    _keeper_kill ceo
    if handle=$(_orca_terminal_handle ceo 2>/dev/null); then
        _orca_cli terminal close --terminal "$handle" --tab --json >/dev/null || return 1
        echo "CEO Orca terminal 종료 — 대화 기억 소멸. 새로 시작: ./run.sh ceo"
    else
        rc=$?
        if [[ $rc -eq 1 ]]; then
            echo "CEO Orca terminal 없음 (이미 종료됨)."
            return 0
        fi
        _orca_terminal_handle ceo >/dev/null
        return $rc
    fi
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
            # 토큰 정본 = repo .env (사용자 규칙: .env 유일소스). 셸 env 가 있으면 그게 우선.
            # 2026-07-23: 재부팅 후 토큰 없이 떠서 전 API 503 — .env 자동 로드로 클래스 픽.
            if [[ -z "${DASH_TOKEN:-}" && -f "$REPO/.env" ]]; then
                DASH_TOKEN=$(grep -m1 -E '^DASH_TOKEN=' "$REPO/.env" | cut -d= -f2-)
            fi
            export DASH_TOKEN
            mkdir -p "$d/.dash-logs"
            # --reload-dir 로 harness/ 도 감시한다: 대시보드는 harness.cli 를
            # import 해 쓰는데 기본 감시범위(cwd=dashboard/backend)로는 harness/
            # 변경이 반영되지 않아, 디스크 코드는 맞는데 화면만 낡은 상태가 된다
            # (2026-07-29 실측: designer 3자 판정이 대시보드에서만 partial).
            setsid bash -c "cd '$d/backend' && source .venv/bin/activate && exec uvicorn main:app --host 127.0.0.1 --port 8165 --reload --reload-dir '$d/backend' --reload-dir '$REPO/harness'" >"$d/.dash-logs/backend.log" 2>&1 & echo $! >>"$pidf"
            setsid bash -c "cd '$d/frontend' && exec npm run dev" >"$d/.dash-logs/frontend.log" 2>&1 & echo $! >>"$pidf"
            echo "dashboard up — backend :8165, frontend :8166 (logs: dashboard/.dash-logs/)"
            if [[ -n "${DASH_TOKEN:-}" ]]; then
                echo "  제어 토큰 활성 (DASH_TOKEN 설정됨) — 웹에서 같은 토큰 입력 시 mutation 가능"
            else
                echo "  ⚠ DASH_TOKEN 미설정 (repo .env 에도 없음) → 전 API 503. 활성화: .env 에 DASH_TOKEN=<비밀> 추가 후 재기동"
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
  claude/codex = process (one agent brain)
  Orca terminal = session keeper and process boundary
  세션은 창을 닫아도 살아있음; 종료는 stop-ceo/stop-cto/down

── 세션 기동 ──
  ./run.sh ceo                                     # CEO 시작/재접속 (Orca runtime에서 대화 유지)
  ./run.sh ceo --fresh                             # 기존 CEO 세션 kill 후 새 대화 (맥락 부패 리셋; 기억 소멸)
  ./run.sh add-cto <name>                          # CTO 추가 (Claude+Codex 세션; <name> 스캔 resolve)
      # <name> = CEO 가 만든 빌드 dir 이름 → claude-project/·modules/ 중 하나로 resolve (둘 다면 에러).
      # 경로 직접: add-cto claude-project/<name>/plan.md | modules/<name>/plan.md
      # plan.md 없으면 스폰 실패 (1단계: CEO 창에서 /build-project | /build-module)
  ./run.sh add-cto <name> --fresh                  # 대화 리셋: Claude+Codex 대화·페어 메시지·skill로그 초기화 (빌드/스펙 유지; delete-cto 아님)
  ./run.sh attach-cto <name>                       # Claude CTO Orca terminal focus
  ./run.sh attach-designer-cto <name>              # Designer(독립 Claude 세션) terminal focus
  ./run.sh attach-codex-cto <name>                 # Codex CTO Orca terminal focus

── 조회 ──
  ./run.sh ls                                      # 세션 목록
  ./run.sh ports                                   # 포트 레지스트리 (docs/PORT.md)
  ./run.sh schema [<name>]                         # DB 스키마 현황 (테이블·컬럼, 읽기전용)
  ./run.sh git-listup [<name>|<dir>]               # 업로드될 최상위 목록 (.gitignore 반영). name=빌드dir 스캔(tunnel→claude-project/tunnel), 기본=현재 dir
  ./run.sh help

── 종료/삭제 ──
  ./run.sh down                  # 전 세션 kill + dev서버/워커 프로세스 + docker compose 컨테이너 정리
  ./run.sh stop-ceo              # CEO terminal 종료(대화 기억 소멸). Orca 창만 닫으면 대화 유지됨
  ./run.sh stop-cto <name>       # Claude+Codex 세션만 정지 (backend/frontend/compose/dir/specs/포트 유지). 재개: add-cto
  ./run.sh delete-cto <name>     # CTO 완전 삭제 (세션+프로세스+compose 컨테이너+dir+sqlite+로그; 볼륨/이미지 보존)
  ./run.sh delete-cto --all

── 유틸 ──
  ./run.sh test-cto <name> [--max-turns N] "<prompt>"   # 비대화 한 방
  ./run.sh fetch <git-url>       # extract 소스 .sources/ shallow clone

── 점검 ──
  ./run.sh doctor                # 정합 검사 (하네스 수정 후 무조건)
  ./run.sh install-services      # Orca 런타임+harnessd systemd user 서비스 설치/갱신 (부팅 자동시작; infra/systemd/*.tmpl 정본)
  ./run.sh smoke                 # 결정론 스모크 (tests/smoke.sh)
  ./run.sh netbind [<name>]      # 웹서버 외부접속 바인딩 정적 검사 (0.0.0.0, RULES §5.3, 읽기전용). 인자 없으면 전체
  ./run.sh prune-ghosts          # 사이드바 Unknown 유령 정리 — Orca 정지→고아수거→정리→재시작→CEO 복원 (Orca 밖 터미널에서!)
  ./run.sh regress <name> --baseline|--check [--segment A~B]
                                 # 회귀 검사 — 완료된 `Run:` 재실행, 통과→실패만 회귀로 보고 (PROCESS §3 5.4)

── 대시보드 (웹 관리 콘솔) ──
  ./run.sh dashboard up          # backend :8165 + frontend :8166 기동 (detached)
  ./run.sh dashboard down        # 종료 (아무 터미널에서나)
      # 최초 1회 install: dashboard/frontend `npm install`,
      #   dashboard/backend `python -m venv .venv && .venv/bin/pip install -r requirements.txt`

note: ./run.sh down does NOT close CEO — Orca runtime에서 대화 유지. 종료는 ./run.sh stop-ceo.
note: 빌드별 dev 서버는 각 빌드 dir 의 ./dev.sh up|down (run.sh 아님).
EOF
}

case "${1:-}" in
    "")        print_usage ;;
    ceo)       shift; cmd_ceo "$@" ;;
    stop-ceo)  cmd_stop_ceo ;;
    add-cto)   shift; cmd_add_cto "$@" ;;
    delete-cto) shift; cmd_delete_cto "$@" ;;
    stop-cto)  shift; cmd_stop_cto "$@" ;;
    ports)     shift; cmd_ports "$@" ;;
    fetch)     shift; cmd_fetch "$@" ;;
    test-cto)  shift; cmd_test_cto "$@" ;;
    ls)        cmd_ls ;;
    down)      cmd_down ;;
    attach-cto) shift; cmd_attach "cto-${1:?usage: $0 attach-cto <name>}" ;;
    attach-codex-cto) shift; cmd_attach_codex_cto "$@" ;;
    attach-designer-cto) shift; cmd_attach_designer_cto "$@" ;;
    doctor)    cmd_doctor ;;
    install-services) shift; cmd_install_services "$@" ;;
    smoke)     bash "$REPO/tests/smoke.sh" ;;
    prune-ghosts) shift; exec bash "$REPO/scripts/orca-restart-clean.sh" "$@" ;;
    schema)    shift; python3 "$REPO/harness/schema_scan.py" "$@" ;;
    netbind)   shift; python3 "$REPO/harness/netbind_scan.py" "$@" ;;
    regress)   shift; python3 "$REPO/harness/regression_gate.py" "$@" ;;
    dashboard) shift; cmd_dashboard "$@" ;;
    git-listup) shift; cmd_git_listup "$@" ;;
    -h|--help|help) print_usage ;;
    *) echo "unknown command: $1" >&2; print_usage >&2; exit 1 ;;
esac
