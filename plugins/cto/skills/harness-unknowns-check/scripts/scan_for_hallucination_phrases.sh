#!/usr/bin/env bash
# scan_for_hallucination_phrases.sh
#
# Grep a spec dir (or individual file) for the four canonical
# anti-pattern phrases that signal LLM hallucination in spec /
# design / review docs. Exits 0 if clean, non-zero with file:line
# hits otherwise.
#
# Intended use:
#   scan_for_hallucination_phrases.sh specs/
#   scan_for_hallucination_phrases.sh specs/spec.md
#   scan_for_hallucination_phrases.sh --cross-check specs/
#
# Or wire into a PreToolUse hook on Write/Edit for paths matching
# specs/ — see SKILL.md "On-demand hook hint".
#
# Exit codes:
#   0  clean — no phrases found
#   1  hits found — non-empty list printed to stdout
#   2  bad usage / target not found
#   3  cross-check mode: phrase appears in 2+ files (cross-doc drift)

set -euo pipefail

# Phrases to match (case-insensitive). Kept tight — see
# references/anti-pattern-phrases.md for rationale.
phrases=(
    "assume the user wants"
    "typical pattern is"
    "standard convention says"
    "the framework usually"
)

cross_check=0
target=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --cross-check)
            cross_check=1
            shift
            ;;
        -h|--help)
            sed -n '2,/^$/p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            if [[ -z "$target" ]]; then
                target="$1"
            else
                echo "scan: too many positional args" >&2
                exit 2
            fi
            shift
            ;;
    esac
done

if [[ -z "$target" ]]; then
    echo "scan: usage: $0 [--cross-check] <file-or-dir>" >&2
    exit 2
fi

if [[ ! -e "$target" ]]; then
    echo "scan: target not found: $target" >&2
    exit 2
fi

# Build the alternation pattern for grep -E.
# Escape nothing — the phrases are plain text.
pattern="$(IFS='|'; echo "${phrases[*]}")"

# Decide what files to scan. If target is a dir, scan *.md in it.
# If a file, scan that file.
files=()
if [[ -d "$target" ]]; then
    while IFS= read -r -d '' f; do
        files+=("$f")
    done < <(find "$target" -maxdepth 2 -type f -name '*.md' -print0)
else
    files+=("$target")
fi

if [[ ${#files[@]} -eq 0 ]]; then
    echo "scan: no .md files under $target" >&2
    exit 2
fi

# Grep all files. -n = line numbers, -i = case-insensitive,
# -H = always show filename, -E = extended regex.
hits="$(grep -niHE "$pattern" "${files[@]}" 2>/dev/null || true)"

if [[ -z "$hits" ]]; then
    # Clean.
    exit 0
fi

if [[ "$cross_check" -eq 1 ]]; then
    # Cross-check mode: report phrases that appear in 2+ distinct
    # files in the same dir. Useful for spotting cross-doc drift
    # (spec.md and design.md both inheriting the same assumption).
    # We compare by phrase, not by full line.
    cross_drift=0
    for phrase in "${phrases[@]}"; do
        # Count distinct files containing this phrase.
        # grep -l exits 1 when no matches — tolerate that under pipefail.
        distinct_files="$( { grep -liE "$phrase" "${files[@]}" 2>/dev/null || true; } | sort -u | wc -l | tr -d '[:space:]')"
        if [[ "$distinct_files" -ge 2 ]]; then
            echo "cross-drift: \"$phrase\" appears in $distinct_files files:"
            { grep -liE "$phrase" "${files[@]}" 2>/dev/null || true; } | sort -u | sed 's/^/  /'
            cross_drift=1
        fi
    done

    # Print regular hits too.
    echo "$hits"
    if [[ "$cross_drift" -eq 1 ]]; then
        exit 3
    fi
    exit 1
fi

# Normal mode: print hits and exit non-zero.
echo "$hits"
echo "" >&2
echo "scan: ${#files[@]} file(s) scanned, hallucination phrases found above." >&2
echo "scan: convert each to a ## Unknowns entry with a resolution path." >&2
echo "scan: see references/anti-pattern-phrases.md for the conversion recipe." >&2
exit 1
