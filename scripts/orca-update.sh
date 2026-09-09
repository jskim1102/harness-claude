#!/usr/bin/env bash
# Ubuntu headless Orca AppImage updater — `./run.sh update-orca`.
#
# Download and verification happen before downtime.  The fixed AppImage path is
# intentional: Orca's registered CLI wrappers point at this exact filename.
# Once the service is stopped, every failure path restores the previous image
# and starts the service again.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT="orca-harness.service"
APPIMAGE="$HOME/apps/orca/orca-linux.AppImage"
ORCA_CLI="$HOME/.local/bin/orca"
MIN_VERSION="1.4.151"
RELEASE_API="https://api.github.com/repos/stablyai/orca/releases"
# 재기동 경로에 유닛의 ExecStartPre 수거기가 끼어 있고 그 자체가 TERM →
# 20×0.5s → KILL 로 최대 10초를 먹는다. 그 뒤에야 AppImage 마운트 + Electron
# 부팅 + runtime ready 가 시작된다. 45초였을 땐 버전업 첫 부팅이 조금만 느려도
# 멀쩡한 새 버전을 롤백시킬 수 있었다 (2026-09-01 리뷰).
WAIT_SECONDS="${ORCA_UPDATE_WAIT_SECONDS:-120}"

usage() {
    cat <<'EOF'
usage: ./run.sh update-orca [VERSION] [--from FILE] [--check] [--yes]

Ubuntu 서버의 Orca AppImage를 안전하게 갱신한다.

  VERSION       설치할 stable 버전 (예: 1.4.193 또는 v1.4.193)
                생략하면 GitHub의 최신 stable release
  --from FILE   이미 받은 AppImage를 사용 (VERSION과 함께 사용 불가)
  --check       현재/대상 버전만 확인하고 변경하지 않음
  --yes         중단 경고 확인을 생략 (비대화 실행 시 필수)

반드시 Orca 밖의 터미널(SSH·GNOME Terminal 등)에서 실행한다. 재기동이 CEO·전 CTO
탭을 끊으므로, Orca 안 에이전트 셸에서는 사용자 명시 지시 + HARNESS_USER_OK=orca
마커가 있어야 실행된다.

env:
  ORCA_UPDATE_WAIT_SECONDS  새 runtime ready 대기 (기본 120초)
EOF
}

die() {
    echo "error: $*" >&2
    exit 1
}

version_ge() {
    [[ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | tail -n1)" == "$1" ]]
}

valid_version() {
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][0-9A-Za-z.-]+)?$ ]]
}

appimage_version() {
    local image="$1" output
    output=$(env -u NODE_OPTIONS -u NODE_REPL_EXTERNAL_MODULE \
        ELECTRON_RUN_AS_NODE=1 "$image" -e \
        'const path=require("path");console.log(require(path.join(process.env.APPDIR,"resources","app.asar","package.json")).version)' \
        2>/dev/null) || return 1
    printf '%s\n' "$output" | tr -d '\r' | awk '/^[0-9]+\.[0-9]+\.[0-9]+/{v=$0} END{print v}'
}

runtime_ready() {
    local expected="$1" payload
    payload=$("$ORCA_CLI" status --json 2>/dev/null || true)
    python3 -c '
import json, sys

expected = sys.argv[1]
try:
    payload = json.load(sys.stdin)
    runtime = payload["result"]["runtime"]
except (KeyError, TypeError, ValueError):
    raise SystemExit(1)
raise SystemExit(0 if (
    payload.get("ok") is True
    and runtime.get("state") == "ready"
    and runtime.get("reachable") is True
    and runtime.get("appVersion") == expected
) else 1)
' "$expected" <<<"$payload"
}

wait_runtime() {
    local expected="$1" deadline=$((SECONDS + WAIT_SECONDS))
    while (( SECONDS < deadline )); do
        if systemctl --user is-active --quiet "$UNIT" && runtime_ready "$expected"; then
            return 0
        fi
        sleep 1
    done
    return 1
}

requested=""
from_file=""
check_only=0
assume_yes=0
while [[ $# -gt 0 ]]; do
    case "$1" in
        --from)
            [[ $# -ge 2 ]] || die "--from 뒤에 AppImage 경로가 필요하다"
            from_file="$2"
            shift 2
            ;;
        --check)
            check_only=1
            shift
            ;;
        --yes|-y)
            assume_yes=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        -*)
            die "알 수 없는 옵션: $1"
            ;;
        *)
            [[ -z "$requested" ]] || die "VERSION은 하나만 지정할 수 있다"
            requested="${1#v}"
            shift
            ;;
    esac
done

[[ -z "$from_file" || -z "$requested" ]] || die "VERSION과 --from은 함께 사용할 수 없다"
[[ "$WAIT_SECONDS" =~ ^[1-9][0-9]*$ ]] || die "ORCA_UPDATE_WAIT_SECONDS는 양의 정수여야 한다"
[[ "$(uname -s)" == "Linux" ]] || die "update-orca는 Linux AppImage 서버 전용이다"

case "$(uname -m)" in
    x86_64|amd64) release_asset="orca-linux.AppImage" ;;
    aarch64|arm64) release_asset="orca-linux-arm64.AppImage" ;;
    *) die "지원하지 않는 Linux 아키텍처: $(uname -m)" ;;
esac

for command_name in curl flock python3 sha256sum sort stat systemctl; do
    command -v "$command_name" >/dev/null 2>&1 || die "필수 명령이 없다: $command_name"
done
[[ -x "$APPIMAGE" ]] || die "현재 AppImage가 없거나 실행 불가: $APPIMAGE"
[[ -x "$ORCA_CLI" ]] || die "Orca CLI wrapper가 없거나 실행 불가: $ORCA_CLI"

# 이 명령은 Orca 런타임을 내렸다 올린다 — Orca 안에서 실행하면 자기 발판을 부순다.
#
# 판정 기준을 tty 에서 **ORCA env 존재**로 바꿨다 (2026-09-01 실측). 예전 가드는
# `[[ -t 0 ]] && ORCA env` 여서 에이전트 도구 셸이 그냥 통과했는데, 그 셸이야말로
# Orca 안에 있다: env 에 ORCA_APP_VERSION 이 있고, 재기동의 ExecStartPre
# (`orca-reap-orphans.sh`)가 **유닛 cgroup 밖 Orca 프로세스 = CEO·전 CTO 탭**을
# TERM/KILL 한다 (수거기 --dry-run 으로 이 세션의 orca-ide 가 고아로 분류되는 것
# 확인). 즉 에이전트 한 줄로 하네스 전체가 끊길 수 있었다. `--from` 은 checksum
# 검증이 없어 임의 AppImage 로 런타임을 갈아끼우는 통로이기도 하다.
#
#   · 대화형(tty) Orca 터미널  → 무조건 거부. updater 자신의 셸이 죽어 롤백조차
#                                 못 돌므로 마커로도 열지 않는다.
#   · 비대화형(에이전트) 셸    → 사용자가 명시 지시한 경우에만
#                                 `HARNESS_USER_OK=orca` 마커로 통과 (RULES §1 규약).
if env | grep -q '^ORCA_APP_VERSION=\|^ORCA_AGENT_HOOK_ENDPOINT='; then
    if [[ -t 0 ]]; then
        die "Orca 터미널 안에서는 실행할 수 없다. SSH·GNOME Terminal 등 Orca 밖에서 실행하라"
    fi
    if [[ ",${HARNESS_USER_OK:-}," != *",orca,"* ]]; then
        die "Orca 안의 에이전트 셸에서는 실행할 수 없다 — 재기동이 CEO·전 CTO 탭을 끊는다.
       Orca 밖 터미널(SSH·GNOME Terminal)에서 실행하거나, 사용자가 명시 지시한
       경우에만 마커를 붙여라: HARNESS_USER_OK=orca ./run.sh update-orca ..."
    fi
    echo "warn: Orca 안에서 실행 중 — 사용자 마커(HARNESS_USER_OK=orca)로 통과한다." >&2
    echo "warn: 재기동 시 CEO·전 CTO Orca 탭이 모두 끊긴다." >&2
fi

lock_dir="$HOME/.config/harness-claude"
mkdir -p "$lock_dir"
exec 9>"$lock_dir/orca-update.lock"
flock -n 9 || die "다른 Orca 업데이트가 이미 진행 중이다"

current_version=$(appimage_version "$APPIMAGE") || die "현재 AppImage 버전을 읽지 못했다"
valid_version "$current_version" || die "현재 AppImage 버전 형식이 잘못됐다: $current_version"

stage=""
metadata_file=""
backup=""
target_version=""
download_url=""
expected_size=""
expected_sha256=""
critical=0
installed_new=0
completed=0

cleanup() {
    local rc=$?
    local failed_path=""
    trap - EXIT INT TERM

    if [[ $critical -eq 1 && $completed -eq 0 ]]; then
        echo "error: 업데이트 실패 — 이전 AppImage로 롤백한다" >&2
        set +e
        systemctl --user stop "$UNIT" >/dev/null 2>&1
        if [[ $installed_new -eq 1 && -f "$APPIMAGE" ]]; then
            failed_path="$APPIMAGE.${target_version}.failed.$(date +%Y%m%d-%H%M%S)"
            mv -- "$APPIMAGE" "$failed_path"
        fi
        if [[ -n "$backup" && -f "$backup" ]]; then
            mv -- "$backup" "$APPIMAGE"
            chmod 0755 "$APPIMAGE"
        fi
        if [[ -x "$APPIMAGE" ]] && systemctl --user start "$UNIT"; then
            echo "rollback: $current_version 복원·서비스 재기동 완료" >&2
            [[ -n "$failed_path" ]] && echo "failed image: $failed_path" >&2
        else
            echo "error: 자동 복구 실패 — $APPIMAGE 및 $backup 상태를 확인하라" >&2
        fi
        set -e
        rc=1
    fi

    if [[ -n "$stage" && -f "$stage" ]]; then
        rm -f -- "$stage"
    fi
    if [[ -n "$metadata_file" && -f "$metadata_file" ]]; then
        rm -f -- "$metadata_file"
    fi
    exit "$rc"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [[ -n "$from_file" ]]; then
    [[ -f "$from_file" ]] || die "--from 파일이 없다: $from_file"
    mkdir -p "$(dirname "$APPIMAGE")"
    stage=$(mktemp "$(dirname "$APPIMAGE")/.orca-linux.AppImage.new.XXXXXX")
    cp -- "$from_file" "$stage"
    chmod 0755 "$stage"
    target_version=$(appimage_version "$stage") || die "새 AppImage 버전을 읽지 못했다: $from_file"
    valid_version "$target_version" || die "새 AppImage 버전 형식이 잘못됐다: $target_version"
    source_label="$from_file"
else
    if [[ -n "$requested" ]]; then
        valid_version "$requested" || die "VERSION 형식이 잘못됐다: $requested"
        release_endpoint="$RELEASE_API/tags/v$requested"
    else
        release_endpoint="$RELEASE_API/latest"
    fi

    metadata_file=$(mktemp)
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
        --retry 3 --max-time 30 -H 'Accept: application/vnd.github+json' \
        --output "$metadata_file" "$release_endpoint"

    release_meta=$(python3 -c '
import json, sys

asset_name = sys.argv[1]
try:
    release = json.load(sys.stdin)
except (TypeError, ValueError) as exc:
    print(f"invalid GitHub release response: {exc}", file=sys.stderr)
    raise SystemExit(1)
tag = release.get("tag_name")
assets = [item for item in release.get("assets", []) if item.get("name") == asset_name]
if release.get("draft") is True or release.get("prerelease") is True:
    print("refusing draft or prerelease build", file=sys.stderr)
    raise SystemExit(1)
if not isinstance(tag, str) or len(assets) != 1:
    print(f"release metadata missing tag or unique {asset_name}", file=sys.stderr)
    raise SystemExit(1)
asset = assets[0]
values = [tag.removeprefix("v"), asset.get("browser_download_url"),
          asset.get("size"), asset.get("digest")]
if not all(value is not None for value in values):
    print("release asset is missing URL, size, or digest", file=sys.stderr)
    raise SystemExit(1)
print("\t".join(map(str, values)))
' "$release_asset" < "$metadata_file") || die "GitHub release metadata를 해석하지 못했다"
    IFS=$'\t' read -r target_version download_url expected_size expected_digest <<<"$release_meta"
    expected_sha256="${expected_digest#sha256:}"

    valid_version "$target_version" || die "release 버전 형식이 잘못됐다: $target_version"
    [[ -z "$requested" || "$target_version" == "$requested" ]] \
        || die "요청 버전($requested)과 release 버전($target_version)이 다르다"
    [[ "$expected_size" =~ ^[1-9][0-9]*$ ]] || die "release 파일 크기가 잘못됐다"
    [[ "$expected_digest" == sha256:* && "$expected_sha256" =~ ^[0-9a-f]{64}$ ]] \
        || die "release SHA-256 digest가 없거나 잘못됐다"
    expected_url="https://github.com/stablyai/orca/releases/download/v${target_version}/${release_asset}"
    [[ "$download_url" == "$expected_url" ]] || die "예상 밖의 release URL: $download_url"
    source_label="$download_url"
fi

version_ge "$target_version" "$MIN_VERSION" \
    || die "Orca $target_version은 최소 지원 버전 $MIN_VERSION보다 오래됐다"

echo "current: $current_version ($APPIMAGE)"
echo "target:  $target_version"
echo "source:  $source_label"

if [[ "$target_version" == "$current_version" ]]; then
    echo "already up to date"
    exit 0
fi
version_ge "$target_version" "$current_version" \
    || die "downgrade는 지원하지 않는다: $current_version -> $target_version"

if [[ $check_only -eq 1 ]]; then
    echo "update available: $current_version -> $target_version"
    exit 0
fi

systemctl --user is-active --quiet "$UNIT" \
    || die "$UNIT가 실행 중이 아니다. 먼저 서비스 상태를 복구한 뒤 업데이트하라"

if [[ $assume_yes -eq 0 ]]; then
    [[ -t 0 ]] || die "비대화 실행에서는 --yes가 필요하다"
    echo
    echo "Orca runtime을 잠시 중지하므로 모든 탭 연결이 끊긴다. keeper 대화는 보존된다."
    read -r -p "계속할까? [y/N] " answer
    [[ "$answer" == "y" || "$answer" == "Y" ]] || { echo "cancelled"; exit 0; }
fi

if [[ -z "$stage" ]]; then
    mkdir -p "$(dirname "$APPIMAGE")"
    stage=$(mktemp "$(dirname "$APPIMAGE")/.orca-linux.AppImage.new.XXXXXX")
    echo "download: $release_asset ($expected_size bytes)"
    curl --proto '=https' --tlsv1.2 --fail --show-error --location \
        --retry 3 --output "$stage" "$download_url"
    actual_size=$(stat -c '%s' "$stage")
    [[ "$actual_size" == "$expected_size" ]] \
        || die "다운로드 크기 불일치: expected=$expected_size actual=$actual_size"
    actual_sha256=$(sha256sum "$stage" | awk '{print $1}')
    [[ "$actual_sha256" == "$expected_sha256" ]] \
        || die "다운로드 SHA-256 불일치"
    chmod 0755 "$stage"
    downloaded_version=$(appimage_version "$stage") \
        || die "검증된 AppImage에서 버전을 읽지 못했다"
    [[ "$downloaded_version" == "$target_version" ]] \
        || die "AppImage 버전 불일치: release=$target_version image=$downloaded_version"
fi

stamp=$(date +%Y%m%d-%H%M%S)
backup="$APPIMAGE.${current_version}.bak"
[[ ! -e "$backup" ]] || backup="$backup.$stamp"

echo "stop:    $UNIT"
systemctl --user stop "$UNIT"
critical=1

mv -- "$APPIMAGE" "$backup"
mv -- "$stage" "$APPIMAGE"
stage=""
chmod 0755 "$APPIMAGE"
installed_new=1

echo "start:   $UNIT"
if ! systemctl --user start "$UNIT"; then
    die "새 Orca 서비스 기동 실패"
fi
if ! wait_runtime "$target_version"; then
    die "${WAIT_SECONDS}초 안에 Orca $target_version runtime이 ready가 되지 않았다"
fi

completed=1
critical=0
echo "updated: $current_version -> $target_version"
echo "backup:  $backup"
echo "Mac Orca에서 kim_3090 host가 Connected로 바뀌는지 확인하라."
