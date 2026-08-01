#!/usr/bin/env bash
# keeper 백엔드 dtach 설치 (sudo 불필요, ~/.local/bin). 재현성 정본 —
# fresh clone 에서 keeper 가 "dtach 없음" 으로 죽으면 이 스크립트 1회.
# 왜 dtach: Orca 가 클라이언트 끊김 때 pty 를 죽이는 것을 방어하는 생존 껍데기.
# tmux 는 사용자 지시로 전면 금지(2026-07-28) — dtach 는 세션/프리픽스/상태바
# 개념이 없는 78KB 단일 바이너리라 멀티플렉서 사고 클래스 자체가 없다.
set -euo pipefail
command -v gcc >/dev/null || { echo "error: gcc 필요"; exit 1; }
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
git clone --depth 1 https://github.com/crigler/dtach "$tmp/dtach"
cd "$tmp/dtach"
./configure >/dev/null
make >/dev/null
mkdir -p "$HOME/.local/bin"
cp dtach "$HOME/.local/bin/dtach"
echo "installed: $HOME/.local/bin/dtach ($("$HOME/.local/bin/dtach" --help 2>&1 | head -1))"
