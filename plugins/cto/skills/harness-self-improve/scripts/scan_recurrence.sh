#!/usr/bin/env bash
# Advisory recurrence scanner for harness-self-improve. READ-ONLY.
#
# Scans the accumulated project memory + per-spec learnings/decisions for facts
# that recurred across >=2 distinct surfaces (different specs, or a spec AND the
# project-memory file). Cross-surface recurrence is the signal that a spec-local
# learning has *earned* a promotion proposal — the thing harness-remember parks
# as "candidate for RULES if it recurs" but nothing else measures. Also surfaces
# unresolved [conflict?] markers and [unverified] low-confidence parks so the
# retro can resolve or re-test them.
#
# This script DECIDES NOTHING. It emits a digest for the model to triage; the
# actual routing/promotion goes through the harness-remember gate (explicit
# user/CTO approval). It never edits a file and never runs git (RULES §1).
# Fail-open: exit 0 even with no input.
#
# Usage: scan_recurrence.sh [PROJECT_ROOT]   (default: $PWD)
set -u
export LC_ALL=C

root="${1:-$PWD}"
mem="$root/.claude/harness-memory.md"
specs="$root/specs"

tmp_all="$(mktemp)" || exit 0
trap 'rm -f "$tmp_all"' EXIT

# Strip the "- [category] " bullet prefix, lowercase, collapse whitespace, trim.
# A fact is matched on its content, not its category tag, so a [learning] in one
# spec and a hand-filed [conflict?]-free restatement elsewhere still align.
norm() {
  sed -E 's/^[[:space:]]*-[[:space:]]*(\[[^]]*\][[:space:]]*)?//' \
    | tr 'A-Z' 'a-z' \
    | tr -s '[:space:]' ' ' \
    | sed -E 's/^ +//; s/ +$//'
}

# Emit "FILE\tNORM" for each bullet line, deduplicated WITHIN the file (so the
# same note twice in one file is not miscounted as recurrence).
collect() {
  local f="$1" line n
  [ -f "$f" ] || return 0
  while IFS= read -r line; do
    # [conflict?]/[unverified] facts have their own buckets below — keep them OUT
    # of the recurrence corpus. Test the RAW line: norm() strips the tag, so a
    # post-norm check never matches (a recurring conflict would leak as a
    # promotion candidate, breaking the "never adjudicate" boundary).
    case "$line" in
      *'[conflict?]'*|*'[unverified]'*) continue ;;
    esac
    n="$(printf '%s' "$line" | norm)"
    # Drop empties and trivially short lines (<8 chars of signal).
    [ "${#n}" -ge 8 ] || continue
    printf '%s\t%s\n' "$f" "$n"
  done < <(grep -E '^[[:space:]]*-[[:space:]]' "$f" 2>/dev/null)
}

{
  collect "$mem"
  if [ -d "$specs" ]; then
    # 새 구조: specs/ 는 평면 (slug 하위 디렉토리 없음) — 직접 + 하위 둘 다 수집
    collect "$specs/learnings.md"
    collect "$specs/decisions.md"
    for d in "$specs"/*/; do
      [ -d "$d" ] || continue
      collect "${d}learnings.md"
      collect "${d}decisions.md"
    done
  fi
} | sort -u > "$tmp_all"

echo "== recurrence (same fact on >=2 surfaces — promotion candidates) =="
if [ -s "$tmp_all" ]; then
  # $1=file $2=norm. Within-file dedup already done, so counting a norm across
  # rows = number of distinct surfaces it appears on.
  awk -F'\t' '{c[$2]++} END {for (k in c) if (c[k]>=2) printf "%dx\t%s\n", c[k], k}' \
    "$tmp_all" | sort -rn -k1 | head -20
  [ -z "$(awk -F'\t' '{c[$2]++} END {for (k in c) if (c[k]>=2) print k}' "$tmp_all")" ] \
    && echo "(none — nothing recurred across surfaces yet)"
else
  echo "(no memory/learnings/decisions surfaces found)"
fi

echo
echo "== unresolved conflicts (route to a human, do not adjudicate) =="
grep -rIEn '\[conflict\?\]' "$mem" "$specs" 2>/dev/null | head -20 \
  || true
grep -rIEq '\[conflict\?\]' "$mem" "$specs" 2>/dev/null || echo "(none)"

echo
echo "== low-confidence parks (re-test or drop) =="
grep -rIEn '\[unverified\]' "$mem" "$specs" 2>/dev/null | head -20 \
  || true
grep -rIEq '\[unverified\]' "$mem" "$specs" 2>/dev/null || echo "(none)"

exit 0
