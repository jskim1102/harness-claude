#!/usr/bin/env bash
# scan_spec_coverage.sh — 커버리지 기계 검증 (fail-closed, PROCESS §2 장치1).
# spec.md '## Features' 의 [F<n>] 라벨 vs tasks.md ckpt 헤딩의 '← F<n>' 역참조 대조.
# 미커버 Feature(omission) + 선언 안 된 역참조(stray) 를 출력한다.
# GATE INPUT — nonzero 면 분해 미완, segment 진행 금지.
# Exit: 0 clean / 1 omission(s)/stray ref(s)/no-ground-truth / 2 usage error.
set -euo pipefail
export LC_ALL=C
specdir="${1:-}"
[[ -z "$specdir" ]] && { echo "usage: $0 specs/" >&2; exit 2; }
spec="$specdir/spec.md"; tasks="$specdir/tasks.md"
[[ -f "$spec" && -f "$tasks" ]] || { echo "scan: need spec.md AND tasks.md under $specdir" >&2; exit 2; }

# Ground-truth 라벨: '## Features' 블록 안의 `- [F<n>] ...` 줄의 F<n> 토큰.
# 다음 헤딩(^#{2,})에서 블록 종료 — 하위 헤딩의 라인이 새지 않게.
features="$(awk '
  /^## Features/{f=1; next}
  /^#{2,}[[:space:]]/{f=0}
  f && /^- \[F[0-9]+\]/{ match($0, /\[F[0-9]+\]/); print substr($0, RSTART+1, RLENGTH-2) }
' "$spec" | sort -u || true)"

# Ground-truth 없으면 검증 불가 — fail-closed (조용한 exit 0 금지).
if [[ -z "$features" ]]; then
  echo "scan: spec.md has no '- [F<n>]' lines under '## Features' — coverage gate cannot run." >&2
  echo "      planner must list features as '- [F1] <기능> [to-build|supplied:<출처>]'." >&2
  exit 1
fi

# 역참조: tasks.md 의 '← F<n>' 토큰 전부 (ckpt 헤딩 위치 무관 — 토큰 단위).
refs="$(grep -oE '←[[:space:]]*F[0-9]+' "$tasks" | grep -oE 'F[0-9]+' | sort -u || true)"

rc=0
echo "== omissions (in ## Features, no covering ckpt) =="
while IFS= read -r feat; do [[ -z "$feat" ]] && continue
  grep -qxF "$feat" <<<"$refs" || { echo "  MISSING: $feat"; rc=1; }
done <<<"$features"
echo "== stray refs (in tree, not in ## Features) =="
while IFS= read -r ref; do [[ -z "$ref" ]] && continue
  grep -qxF "$ref" <<<"$features" || { echo "  STRAY: $ref"; rc=1; }
done <<<"$refs"
[[ $rc -eq 0 ]] && echo "scan: complete — every feature covered, no stray refs."
exit $rc
