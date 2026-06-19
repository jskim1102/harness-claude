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

# 무태그 Feature: '## Features' 의 '- [F<n>]' 줄은 반드시 [to-build] 또는
# [supplied:<출처>] 태그를 달아야 한다 (PROCESS.md §2 / build-* 포맷). 무태그면
# from-scratch vs 재료(modules/extract) 구분이 사라져 supplied 재구현 차단이
# 무력화된다 (리뷰 P1). ground-truth 추출 regex 가 태그를 안 보던 구멍.
untagged="$(awk '
  /^## Features/{f=1; next}
  /^#{2,}[[:space:]]/{f=0}
  f && /^- \[F[0-9]+\]/ && !/\[to-build\]/ && !/\[supplied:/ {
    match($0, /\[F[0-9]+\]/); print substr($0, RSTART+1, RLENGTH-2)
  }
' "$spec" || true)"

# 역참조: tasks.md 의 '← F<n>' 토큰 전부 (ckpt 헤딩 위치 무관 — 토큰 단위).
refs="$(grep -oE '←[[:space:]]*F[0-9]+' "$tasks" | grep -oE 'F[0-9]+' | sort -u || true)"

rc=0
echo "== untagged features (no [to-build]/[supplied:]) =="
while IFS= read -r feat; do [[ -z "$feat" ]] && continue
  echo "  UNTAGGED: $feat — add [to-build] or [supplied:<출처>]"; rc=1
done <<<"$untagged"
echo "== omissions (in ## Features, no covering ckpt) =="
while IFS= read -r feat; do [[ -z "$feat" ]] && continue
  grep -qxF "$feat" <<<"$refs" || { echo "  MISSING: $feat"; rc=1; }
done <<<"$features"
echo "== stray refs (in tree, not in ## Features) =="
while IFS= read -r ref; do [[ -z "$ref" ]] && continue
  grep -qxF "$ref" <<<"$features" || { echo "  STRAY: $ref"; rc=1; }
done <<<"$refs"
# 무참조 ckpt: 모든 '### …ckptN…' 헤딩은 '← F<n>' 역참조를 1개 이상 달아야 한다
# (PROCESS.md §2 — 모든 ckpt 가 spec 라벨 역참조). 무참조 ckpt = 어떤 feature 에도
# 안 묶인 작업 = 추적 안 되는 scope creep (리뷰 P1). 단방향(feature→ckpt)만 보던 구멍.
echo "== unreferenced ckpts (heading has no ← F<n>) =="
unref_ckpts="$(awk '
  /^###[[:space:]].*ckpt[0-9]/ && !/←[[:space:]]*F[0-9]+/ {
    line=$0; sub(/^###[[:space:]]*/, "", line); print line
  }
' "$tasks" || true)"
while IFS= read -r ck; do [[ -z "$ck" ]] && continue
  echo "  NO ← F: $ck"; rc=1
done <<<"$unref_ckpts"

# extract-supplied (축3=extract) 라벨: '[supplied:<v>]' 에서 v 가 modules/ 로
# 시작 안 하는 것 (= 원본 코드 복사 대상). modules/ 재사용은 USAGE.md 계약
# 통합이라 원본 라인 인용 불요 — extract(.sources/ 등 원본코드 복사)만 대상.
# 규칙: extract feature 를 덮는 ckpt 의 task 에 'From:' 원본 포인터가 반드시
# 1개 이상 있어야 한다 (planner 가 원본을 안 읽고 산문으로 재구성하는 것 차단).
extract_feats="$(awk '
  /^## Features/{f=1; next}
  /^#{2,}[[:space:]]/{f=0}
  f && /^- \[F[0-9]+\]/ && /\[supplied:/ {
    s=$0; sub(/.*\[supplied:[[:space:]]*/, "", s); sub(/[]].*/, "", s)
    if (s !~ /^modules\//) { match($0, /\[F[0-9]+\]/); print substr($0, RSTART+1, RLENGTH-2) }
  }
' "$spec" | sort -u | tr '\n' ' ' || true)"

echo "== extract ckpts missing From: source pointer (축3=extract) =="
if [[ -n "${extract_feats// }" ]]; then
  miss="$(awk -v feats="$extract_feats" '
    BEGIN{ n=split(feats, a, /[ ]+/); for(i=1;i<=n;i++) if(a[i]!="") sup[a[i]]=1 }
    function close_ckpt(){ if (ckpt!="" && need && !from) print "  NO From: " ckpt " (← " reflist ")" }
    /^###[[:space:]]/{
      close_ckpt(); from=0; need=0; reflist=""
      ckpt=$0; sub(/[[:space:]]*←.*/, "", ckpt); sub(/^###[[:space:]]*/, "", ckpt)
      h=$0
      while (match(h, /←[[:space:]]*F[0-9]+/)) {
        t=substr(h, RSTART, RLENGTH); sub(/.*F/, "F", t)
        if (t in sup){ need=1; reflist=reflist (reflist==""?"":",") t }
        h=substr(h, RSTART+RLENGTH)
      }
      next
    }
    /^#{1,2}[[:space:]]/{ close_ckpt(); ckpt=""; need=0; from=0; next }
    /From:/{ if (ckpt!="") from=1 }
    END{ close_ckpt() }
  ' "$tasks" || true)"
  if [[ -n "$miss" ]]; then echo "$miss"; rc=1; fi
fi

[[ $rc -eq 0 ]] && echo "scan: complete — every feature covered, no stray refs, extract ckpts cite From:."
exit $rc
