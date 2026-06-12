#!/usr/bin/env bash
# check_relay_prefix.sh
#
# Validate that a candidate SendMessage body is a well-formed relay
# payload. Read body on stdin, exit 0 if OK, non-zero with an
# explanation on stderr otherwise.
#
# Intended use:
#   echo "$msg_body" | check_relay_prefix.sh && SendMessage ...
#
# Or wire into a PreToolUse hook on SendMessage to fail-fast on
# malformed relay payloads.
#
# Exit codes:
#   0 — OK (no relay tag, or well-formed relay payload).
#   2 — empty body.
#   3 — tag found but not at prefix (embedded mid-sentence).
#   4 — tag with no body (bare `[user-q]` or `[user-a]`).
#   5 — multiple tags in one body (paste error).

set -u
set -o pipefail

body="$(cat)"

if [[ -z "$body" ]]; then
    echo "relay-check: empty body" >&2
    exit 2
fi

# Trim leading whitespace.
trimmed="$(printf '%s' "$body" | sed -E 's/^[[:space:]]+//')"

# Detect any user-q / user-a tag anywhere — if none, skip checks
# (this message is not a relay payload).
if ! grep -qE '\[user-[qa]\]' <<<"$body"; then
    exit 0
fi

# Fast-path: bare tag with no body (trimmed body is exactly the tag).
bare="$(printf '%s' "$trimmed" | sed -E 's/[[:space:]]+$//')"
if [[ "$bare" == "[user-q]" || "$bare" == "[user-a]" ]]; then
    echo "relay-check: ${bare} tag with no body" >&2
    exit 4
fi

# Prefix check: the tag must be at position 0 of the trimmed body.
if [[ "$trimmed" =~ ^\[user-q\][[:space:]] ]]; then
    tag="user-q"
elif [[ "$trimmed" =~ ^\[user-a\][[:space:]] ]]; then
    tag="user-a"
else
    echo "relay-check: [user-q]/[user-a] tag found but not at prefix" >&2
    echo "relay-check: place the tag at the very start of the message," >&2
    echo "             followed by a single space, then the body." >&2
    echo "relay-check: offending body (first 120 chars):" >&2
    echo "  $(printf '%s' "$trimmed" | head -c 120)" >&2
    exit 3
fi

# Count tags across the whole body — sed processes per-line, so we
# check the raw body before stripping. Two or more tags = paste error.
tag_count="$(grep -oE '\[user-[qa]\]' <<<"$body" | wc -l | tr -d '[:space:]')"
if [[ "$tag_count" -gt 1 ]]; then
    echo "relay-check: $tag_count relay tags in one body — paste error?" >&2
    echo "relay-check: relay payloads carry exactly one tag at the prefix." >&2
    exit 5
fi

# Body after tag must be non-empty. Strip only the prefix (first line).
after_tag="$(printf '%s' "$trimmed" | awk -v t="$tag" 'NR==1{sub("^\\["t"\\][[:space:]]+","")}1')"
if [[ -z "$(printf '%s' "$after_tag" | tr -d '[:space:]')" ]]; then
    echo "relay-check: [$tag] tag with no body" >&2
    exit 4
fi

exit 0
