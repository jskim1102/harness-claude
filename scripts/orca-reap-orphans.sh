#!/usr/bin/env bash
# orca-harness 유닛 **밖에서** 살아남은 Orca 프로세스를 거둔다.
#
# 왜 필요한가 (2026-07-23): 유닛이 죽으면(core-dump/exit-code 실측) AppImage 가
# 띄운 자식들이 systemd --user 직속으로 재부모화돼 살아남는다. 그러면 유닛은
# failed 인데 Orca 프로세스는 8개씩 떠 있는 상태가 되고, `systemctl stop` 은
# 그것들에 닿지 않고 `start` 는 자원을 물고 있는 고아와 충돌한다 —
# "종료·실행이 맘대로 안 되는" 증상의 정체.
#
# 유닛의 ExecStartPre 로도 호출돼, 매 기동 전에 잔존물을 먼저 거둔다.
#
# ⚠ Orca 안의 터미널(CEO·CTO 포함)은 전부 죽는다. SSH 등 Orca 밖에서 실행하라.
set -uo pipefail

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

# 유닛 소속 판정은 **cgroup 정본**으로 한다. `systemctl status` 출력 파싱은 형식이
# 흔들려 살아있는 서비스를 고아로 오판했다(2026-07-23 실측) — 그대로 죽였으면 정상
# 구동 중인 Orca 를 참수할 뻔했다. cgroup.procs 는 커널이 주는 정확한 멤버십이다.
cg=$(systemctl --user show orca-harness -p ControlGroup --value 2>/dev/null)
in_unit=""
if [[ -n "$cg" && -r "/sys/fs/cgroup${cg}/cgroup.procs" ]]; then
    in_unit=" $(tr '\n' ' ' < "/sys/fs/cgroup${cg}/cgroup.procs") "
elif [[ -n "$cg" ]]; then
    # cgroup 을 못 읽으면 판정 불가 — 오폭보다 중단이 낫다 (fail-closed).
    echo "error: 유닛 cgroup 을 읽을 수 없다 ($cg) — 소속 판정 불가로 중단." >&2
    exit 1
fi
unit_pids=" $(systemctl --user show orca-harness -p MainPID --value 2>/dev/null) "

# Orca 판정은 argv 가 아니라 **실행 파일(/proc/<pid>/exe)** 로 한다. 예전의
# `pgrep -f 'orca-ide|orca-linux\.AppImage'` 는 argv 부분문자열 매치라, 2026-10-06
# `update-orca --from …/orca-linux.AppImage…` 를 돌리던 업데이터 셸(과 그 부모 도구 셸)을
# Orca 로 오판해 SIGKILL 했다 — 롤백 트랩도 못 돈 채 죽어 결과가 운에 맡겨졌다.
# 파일명만 언급한 셸·에디터·grep 은 exe 가 bash/python 이라 여기서 걸러진다.
_is_orca_exe() {
    case "$1" in
        */orca-ide) return 0 ;;              # Electron 본체·zygote·renderer·CLI(RUN_AS_NODE)
        */orca-linux.AppImage*) return 0 ;;  # AppImage 런타임 부모 (.bak/.failed 로 개명돼도)
        /tmp/.mount_orca-*/*) return 0 ;;    # 마운트에서 뜬 헬퍼 (chrome_crashpad_handler 등)
    esac
    return 1
}

targets=()
for d in /proc/[0-9]*; do
    pid=${d#/proc/}
    [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
    exe=$(readlink "$d/exe" 2>/dev/null) || continue   # 남의 프로세스·커널스레드는 못 읽음 → 스킵
    exe=${exe% (deleted)}
    _is_orca_exe "$exe" || continue
    [[ "$in_unit$unit_pids" == *" $pid "* ]] && continue
    targets+=("$pid")
done

if [[ ${#targets[@]} -eq 0 ]]; then
    echo "고아 Orca 프로세스 없음."
    exit 0
fi

echo "유닛 밖 Orca 프로세스 ${#targets[@]}개:"
for p in "${targets[@]}"; do
    ps -o pid=,etime=,args= -p "$p" 2>/dev/null | cut -c1-100
done

if [[ $DRY -eq 1 ]]; then
    echo "(--dry-run — 아무것도 죽이지 않았다)"
    exit 0
fi

# TERM 먼저, 안 죽는 것만 KILL. 여기서 죽는 것에 사용자 터미널이 포함된다.
kill -TERM "${targets[@]}" 2>/dev/null
for _ in $(seq 1 20); do
    still=0
    for p in "${targets[@]}"; do kill -0 "$p" 2>/dev/null && still=1; done
    [[ $still -eq 0 ]] && break
    sleep 0.5
done
for p in "${targets[@]}"; do kill -0 "$p" 2>/dev/null && kill -KILL "$p" 2>/dev/null; done

left=0
for p in "${targets[@]}"; do kill -0 "$p" 2>/dev/null && left=$((left+1)); done
echo "정리 완료 (잔존 $left)"
exit 0
