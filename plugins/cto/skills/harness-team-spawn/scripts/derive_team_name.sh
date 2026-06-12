#!/usr/bin/env bash
# derive_team_name.sh
#
# Deterministic team-name derivation for harness-claude.
# Format: <cto-name>-<slug>, with <slug>-<8char-hash> as fallback
# when HARNESS_ROLE is missing or malformed (no cto: prefix).
#
# Two modes:
#   1. Derive (default) — emit a computed team name on stdout.
#   2. Validate (--validate) — check that a candidate name follows the
#      <cto-name>-<slug> convention for the current HARNESS_ROLE.
#
# ## Examples
#
#   # Derive: cto:foo + auth-signup → foo-auth-signup
#   HARNESS_ROLE=cto:foo derive_team_name.sh auth-signup
#       → foo-auth-signup            (exit 0)
#
#   # Derive: HARNESS_ROLE unset → fallback with hash
#   HARNESS_ROLE= derive_team_name.sh auth-signup
#       → auth-signup-<8char-hash>   (exit 0)
#
#   # Derive: bare role (no cto: prefix) → fallback with hash
#   HARNESS_ROLE=foo derive_team_name.sh auth-signup
#       → auth-signup-<8char-hash>   (exit 0)
#
#   # Derive: generic slug rejected
#   derive_team_name.sh team
#       → (stderr error)             (exit 2)
#
#   # Validate: name matches <cto-name>-<slug> for current role
#   HARNESS_ROLE=cto:foo derive_team_name.sh --validate foo-auth-signup
#       → (exit 0, no output)
#
#   # Validate: name does NOT match prefix → reject
#   HARNESS_ROLE=cto:foo derive_team_name.sh --validate other-team-name
#       → (stderr error)             (exit 2)
#
# Exit codes:
#   0 — success (derived name on stdout, or validation passed)
#   1 — slug missing (derive mode) or candidate missing (validate mode)
#   2 — slug / name invalid, or HARNESS_ROLE missing in validate mode

set -euo pipefail

# ---------------------------------------------------------------------
# Validate mode
# ---------------------------------------------------------------------
if [[ "${1:-}" == "--validate" ]]; then
    # Read candidate from $2 or stdin.
    candidate="${2:-}"
    if [[ -z "$candidate" ]]; then
        if [[ ! -t 0 ]]; then
            candidate="$(cat)"
            candidate="${candidate//[$'\r\n']}"
        fi
    fi
    if [[ -z "$candidate" ]]; then
        echo "derive_team_name --validate: missing candidate name" >&2
        echo "usage: derive_team_name.sh --validate <name>" >&2
        echo "       echo <name> | derive_team_name.sh --validate" >&2
        exit 1
    fi

    role="${HARNESS_ROLE:-}"
    if [[ -z "$role" || "$role" != cto:* ]]; then
        echo "derive_team_name --validate: HARNESS_ROLE missing or not in cto:<name> form" >&2
        echo "derive_team_name --validate: cannot validate without an owner CTO" >&2
        exit 2
    fi
    cto_name="${role#cto:}"
    if [[ -z "$cto_name" ]]; then
        echo "derive_team_name --validate: HARNESS_ROLE has empty CTO name after cto: prefix" >&2
        exit 2
    fi

    # Must start with <cto-name>- and the rest must be kebab-case ASCII.
    if [[ "$candidate" != "${cto_name}-"* ]]; then
        echo "derive_team_name --validate: '$candidate' does not start with '${cto_name}-' prefix" >&2
        exit 2
    fi
    if ! [[ "$candidate" =~ ^[a-z0-9]+(-[a-z0-9]+)+$ ]]; then
        echo "derive_team_name --validate: '$candidate' contains illegal chars or is not kebab-case ASCII" >&2
        echo "derive_team_name --validate: expected /^[a-z0-9]+(-[a-z0-9]+)+\$/" >&2
        exit 2
    fi
    exit 0
fi

# ---------------------------------------------------------------------
# Derive mode
# ---------------------------------------------------------------------
slug="${1:-}"

if [[ -z "$slug" ]]; then
    echo "derive_team_name: missing slug argument" >&2
    echo "usage: derive_team_name.sh <slug>" >&2
    exit 1
fi

# Slug must be kebab-case ASCII. Reject anything else loudly rather
# than silently coercing — silent coercion produced the wrong name in
# at least one past incident.
if ! [[ "$slug" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
    echo "derive_team_name: slug '$slug' is not kebab-case ASCII" >&2
    echo "derive_team_name: expected /^[a-z0-9]+(-[a-z0-9]+)*\$/" >&2
    exit 2
fi

# Refuse generic slugs that would collide across CTOs even with the
# cto-name prefix removed (defensive — the prefix is the main guard).
case "$slug" in
    team|auto-team|dev-team|agents|default)
        echo "derive_team_name: slug '$slug' is too generic — pick something" >&2
        echo "derive_team_name: that names this specific feature." >&2
        exit 2
        ;;
esac

role="${HARNESS_ROLE:-}"

# Explicit early-out: HARNESS_ROLE must start with cto: for us to use
# it. A bare value like "testbed" (no cto: prefix) is a misconfigured
# env var; do not silently produce "testbed-<slug>" — fall through to
# the hashed fallback so the bad config is visible in the team name.
if [[ -n "$role" && "$role" == cto:* ]]; then
    cto_name="${role#cto:}"
    if [[ -n "$cto_name" ]]; then
        echo "${cto_name}-${slug}"
        exit 0
    fi
fi

# Fallback: <slug>-<8char-hash>. Hash slug + PID + epoch-nanos so two
# simultaneous fallbacks on the same slug produce different names.
hash_input="${slug}-$$-$(date +%s%N 2>/dev/null || date +%s)"
hash="$(printf '%s' "$hash_input" | sha256sum | head -c 8)"

echo "${slug}-${hash}"
exit 0
