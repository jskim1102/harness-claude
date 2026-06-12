#!/usr/bin/env bash
# build-codex-review-agent.sh — hand the build spec to Codex so Codex authors
# the cross-model CODE-REVIEW agent. BUILD phase only: Codex writes the agent
# artifacts into plugins/codex-review/. It does NOT run a review here. The
# RUN-phase entry (run-review.sh) is one of the artifacts Codex produces (spec
# section 9).
#
# Spec: docs/superpowers/specs/2026-06-09-codex-review-agent-design.md
#
# Usage:
#   ./build-codex-review-agent.sh                 # DRY-RUN: print the codex command + prompt
#   ./build-codex-review-agent.sh --go            # actually run codex exec
#   ./build-codex-review-agent.sh --go --spec <md> --out <dir>
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SPEC="$REPO/docs/superpowers/specs/2026-06-09-codex-review-agent-design.md"
OUT="$REPO/plugins/codex-review"
RULES="$REPO/plugins/_shared/RULES.md"
GO=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --go) GO=1; shift ;;
    --spec) SPEC="$2"; shift 2 ;;
    --out)  OUT="$2";  shift 2 ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "error: unknown arg $1" >&2; exit 2 ;;
  esac
done

[[ -f "$SPEC" ]]  || { echo "error: spec not found: $SPEC" >&2; exit 1; }
[[ -f "$RULES" ]] || echo "warning: shared rules not found: $RULES (continuing)" >&2
command -v codex >/dev/null || { echo "error: codex CLI not on PATH" >&2; exit 1; }
codex login status >/dev/null 2>&1 || { echo "error: codex not logged in (run: codex login)" >&2; exit 1; }

SPEC_REL="${SPEC#"$REPO/"}"
OUT_REL="${OUT#"$REPO/"}"
RULES_REL="${RULES#"$REPO/"}"
LASTMSG="$(mktemp -t codex-review-build-lastmsg.XXXXXX.md)"

read -r -d '' PROMPT <<EOF || true
You are building a new agent for the harness-claude system. This is the BUILD
phase: you AUTHOR the agent's artifacts. You do NOT run any code review now.

STEP 1 — internalize the contract:
- Read the full build spec: $SPEC_REL
- Read and obey the harness shared rules: $RULES_REL

STEP 2 — author the cross-model CODE-REVIEW agent under $OUT_REL/ exactly as
spec section 9 requires:
  1. AGENT.md      — the reviewer's definition/prompt run at review time (Codex
                     runtime): its role, the section 6 method + finding
                     categories (correctness / security / spec-divergence /
                     quality), the section 7 report schema, and the read-only /
                     no-commit constraints.
  2. scaffolding   — a review runner + report writer (your structure; runnable).
                     It may use your own 'codex' review tooling or a structured
                     prompt, but it must review the WHOLE project codebase, not
                     a git diff (harness projects are greenfield, no base).
  3. run-review.sh — the RUN-phase entry the CEO calls with a per-run context
                     packet: the target PROJECT PATH, the spec/README contract
                     paths, and a report OUTPUT PATH. It reads the project
                     source + spec, reviews per section 6, writes the section 7
                     structured report to the harness-side output path (OUTSIDE
                     the target project), and sends a summary to the CEO over
                     the message bus. Verify exact flags with: harness send --help
                     (expected: harness send --from codex-review:<project> --to ceo --body-stdin).
  4. README.md     — how to invoke, what it produces, the cross-model rationale.

HARD CONSTRAINTS (non-negotiable):
- The agent you build is a REVIEWER: it READS the target's full source + spec,
  but it must NEVER modify the target source and NEVER commit.
- Decorrelation: the value is that a DIFFERENT model (you, Codex) reviews code
  Claude built. Review independently; do not assume Claude's choices are correct.
- Do NOT modify anything outside $OUT_REL/ (the report goes to the harness-side
  report path, not into the target project).
- Do NOT run git commit / push anywhere.
- Match harness conventions: message bus = the 'harness' CLI; rules = $RULES_REL.

When finished, print a concise summary of every file you created and any
assumptions or decisions you made.
EOF

CMD=( codex exec
  --cd "$REPO"
  --sandbox workspace-write
  --skip-git-repo-check
  --output-last-message "$LASTMSG"
  - )

echo "=== Codex CODE-REVIEW agent BUILD handoff -> Codex ==="
echo "spec : $SPEC_REL"
echo "out  : $OUT_REL/   (Codex writes agent artifacts here)"
echo "rules: $RULES_REL"
echo "codex: $(codex --version 2>/dev/null)  [$(codex login status 2>/dev/null | head -1)]"
echo "cmd  : ${CMD[*]}   (prompt on stdin)"
echo "last-message capture: $LASTMSG"
echo

if [[ "$GO" -ne 1 ]]; then
  echo "--- DRY-RUN (no codex invocation). Prompt that WOULD be sent: ---"
  echo "$PROMPT"
  echo
  echo ">> review, then run with --go to execute."
  exit 0
fi

mkdir -p "$OUT"
printf '%s' "$PROMPT" | "${CMD[@]}"
echo
echo "=== Codex build finished. Artifacts under: $OUT_REL/ ==="
ls -la "$OUT" 2>/dev/null || true
echo "--- Codex final message ($LASTMSG) ---"
cat "$LASTMSG" 2>/dev/null || true
