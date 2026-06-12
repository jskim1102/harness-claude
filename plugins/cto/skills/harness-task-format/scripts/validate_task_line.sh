#!/usr/bin/env bash
# validate_task_line.sh
#
# Mirror of the TaskCreated hook regex
# (hooks/team/task_created_format_check.py). Pipe a candidate task
# subject + description body on stdin, OR pass it as a single argv
# string. Exit 0 if the hook would accept; non-zero with a specific
# reason on stderr otherwise.
#
# Hook rules (kept in sync — if the hook changes, update this):
#   1. presence of [plan|design|dev|review] tag (case-insensitive)
#   2. at least two literal `|` characters
#   3. a `Run:` token followed by at least one non-whitespace char
#   4. bypass: `[skip-format-check]` (case-insensitive substring)
#
# Usage:
#   echo "[dev] add X | src/x.ts | tests pass. Run: npm test" \
#     | scripts/validate_task_line.sh
#   scripts/validate_task_line.sh "[dev] add X | src/x.ts | tests pass. Run: npm test"

set -euo pipefail

if [[ $# -gt 0 ]]; then
    body="$*"
else
    body="$(cat)"
fi

if [[ -z "$(printf '%s' "$body" | tr -d '[:space:]')" ]]; then
    echo "task-format: empty input" >&2
    exit 2
fi

# Bypass check — substring, case-insensitive (mirrors hook's text.lower()).
lower_body="$(printf '%s' "$body" | tr '[:upper:]' '[:lower:]')"
if [[ "$lower_body" == *"[skip-format-check]"* ]]; then
    exit 0
fi

errors=()

# 1. Role tag — case-insensitive match for one of the four canonical roles.
if ! grep -qiE '\[(plan|design|dev|review)\]' <<<"$body"; then
    errors+=("missing [role] tag — use one of [plan] [design] [dev] [review]")
fi

# 2. At least two pipe characters.
# `grep -o '|' ... | wc -l` — grep exits 1 when no pipes match, which would
# kill the script under `set -e -o pipefail`. Tolerate that here so the
# "no pipes" case is treated as `pipe_count=0` rather than a hard error.
pipe_count="$(grep -o '|' <<<"$body" | wc -l | tr -d '[:space:]' || true)"
if [[ "$pipe_count" -lt 2 ]]; then
    errors+=("missing pipe-delimited slots — need '| <files> | <acceptance>' ($pipe_count of 2 pipes present)")
fi

# 3. `Run: <non-whitespace>` — matches the hook regex `\bRun:\s*\S`.
if ! grep -qE '\bRun:[[:space:]]*[^[:space:]]' <<<"$body"; then
    errors+=("missing Run: <command> — verification command is required")
fi

if [[ ${#errors[@]} -eq 0 ]]; then
    exit 0
fi

echo "task-format: rejected" >&2
for e in "${errors[@]}"; do
    echo "  - $e" >&2
done
echo "task-format: required shape:" >&2
echo "  [role] <verb> <what> | <file paths> | <acceptance>. Run: <command>" >&2
echo "  (or add [skip-format-check] for a coordination / research task)" >&2
exit 3
