#!/usr/bin/env bash
# Orca 를 완전히 내리고(고아 포함) 유령을 정리한 뒤 되살린다 — `./run.sh prune-ghosts`.
#
# 왜 껐다 켜야 하나 (2026-07-23): Orca 런타임이 상태를 메모리에 들고 있어, 구동 중
# 외부에서 지운 항목을 몇 초 안에 되살린다. 앱이 내려간 동안에만 정리가 남는다.
#
# 왜 고아 수거가 필수인가 (2026-07-28 실측): `systemctl stop` 후에도 AppImage 가
# `/tmp/.mount_orca-*/orca-ide` 로 재실행된 프로세스들이 살아남고, 그러면
# prune 스크립트가 "Orca 실행 중" 으로 정확히 거부한다. pkill 패턴 수동 조합은
# 오늘 밤 사용자가 직접 밟은 함정 — 수거는 cgroup 정본 reaper 에 맡긴다.
#
# ⚠ Orca 를 내리면 그 안의 모든 터미널 pty 가 죽는다. keeper(dtach) 뒤의
#   CEO/CTO agent 프로세스는 살아남고, 마지막 단계의 `run.sh ceo` 가 재접속한다.
#   단, 이 스크립트 자체는 반드시 **Orca 밖 터미널**(SSH 등)에서 돌려야 한다 —
#   Orca 터미널에서 돌리면 자기 셸이 중간에 죽어 Orca 가 내려간 채로 남는다.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT=orca-harness.service

# Orca **대화형** 터미널 감지 — 진짜 위험은 "Orca pty 위의 대화형 셸" 이다
# (Orca 가 내려가면 pty 와 함께 셸이 죽어 스크립트가 중간에 끊긴다).
# env 만 보면 keeper(dtach) 뒤에서 pty 없이 도는 CEO 의 도구 셸까지 오탐한다 —
# 그쪽은 pty 가 없어 Orca 사망에 면역이다 (2026-07-28 실측: stop+pkill 생존).
# 판정 = ORCA env 존재 AND stdin 이 tty (대화형).
if env | grep -q '^ORCA_APP_VERSION=\|^ORCA_AGENT_HOOK_ENDPOINT=' && [ -t 0 ]; then
    echo "error: 여기는 Orca 터미널이다 — Orca 를 내리면 이 셸도 같이 죽는다." >&2
    echo "       Orca 밖의 터미널(SSH·GNOME Terminal 등)에서 다시 실행하라." >&2
    exit 1
fi

echo "== 0/6 원격 클라이언트 접속 검사"
# 2026-07-28 실측: 정리 105/107 성공 후 정확히 2개(자식 워크스페이스)가 부활했다.
# 서버 파일·웹스토리지·히스토리 전수 그렙으로 서버측 소스는 배제 — 남는 유일한
# 기록 보유자는 **접속 중이던 원격 Orca 앱**(재연결 때 자기 화면 상태를 서버로
# 되밀어 넣는다). 그래서 정리 중 클라이언트 접속은 결정론으로 차단한다.
PORT=$(grep -oE '[0-9]+' "$HOME/.config/harness-claude/orca-server.env" 2>/dev/null | head -1)
PORT=${PORT:-6768}
clients=$(ss -tn state established "( sport = :$PORT )" 2>/dev/null | tail -n +2 \
          | awk '{print $NF}' | grep -v '^127\.' | sort -u || true)
if [[ -n "$clients" ]]; then
    echo "error: 원격 Orca 클라이언트가 접속 중이다 — 정리해도 클라이언트가 유령을 되살린다." >&2
    echo "$clients" | sed 's/^/       접속: /' >&2
    echo "       노트북/폰의 Orca 앱을 완전히 종료(창 닫기 아님, Quit)한 뒤 다시 실행하라." >&2
    exit 1
fi
echo "  접속 클라이언트 없음 — 진행"

echo "== 1/6 정리 대상 미리보기"
python3 "$REPO/scripts/orca-prune-ghosts.py" | tail -8

echo
echo "== 2/6 Orca 중지 ($UNIT)"
systemctl --user stop "$UNIT"

echo "== 3/6 고아 수거 (cgroup 정본 reaper)"
bash "$REPO/scripts/orca-reap-orphans.sh"
for _ in $(seq 1 20); do
    pgrep -f 'orca-ide|orca-linux\.AppImage' >/dev/null 2>&1 || break
    sleep 0.5
done
if pgrep -af 'orca-ide|orca-linux\.AppImage' | grep -v orca-restart-clean; then
    echo "error: Orca 프로세스가 아직 살아있다 — 정리하지 않고 복구 기동한다." >&2
    systemctl --user start "$UNIT" || true
    exit 1
fi

echo "== 4/6 유령 정리"
python3 "$REPO/scripts/orca-prune-ghosts.py" --apply | tail -3

echo
echo "== 5/6 Orca 재시작 + CEO 복원"
systemctl --user start "$UNIT"
for _ in $(seq 1 30); do
    orca status --json 2>/dev/null | grep -q '"reachable": true' && break
    sleep 1
done
"$REPO/run.sh" ceo

echo
echo "== 6/6 자가 검증 — 런타임이 유령을 되살리지 않았는가"
# 런타임은 상태를 메모리에 들고 있다가 이벤트 때 파일로 흘린다. 프로브 터미널을
# 하나 만들었다 닫아 강제로 상태를 흘리게 한 뒤, 새로 쓰인 파일을 재검한다.
# (지난 부활 사고는 재기동 9분 뒤 파일 재기록에서 드러났다 — 그걸 지금 앞당겨 본다.)
probe=$(orca terminal create --worktree "path:$REPO" --title "harness:prune-verify" \
        --command "true" --json 2>/dev/null \
        | python3 -c 'import json,sys;print(json.load(sys.stdin)["result"]["terminal"]["handle"])' \
        2>/dev/null || true)
[[ -n "$probe" ]] && orca terminal close --terminal "$probe" --tab --json >/dev/null 2>&1
sleep 3
verify=$(python3 "$REPO/scripts/orca-prune-ghosts.py")
if [[ "$verify" == *"정리할 고아 없음"* ]]; then
    echo "VERDICT: CLEAN — 고아 0, 부활 없음."
    echo "완료. 클라이언트(노트북/폰) Orca 를 새로고침하면 Unknown 이 사라져 있다."
else
    echo "VERDICT: RESURRECTED — 런타임이 일부를 되살렸다:" >&2
    echo "$verify" | tail -15 >&2
    exit 1
fi
