#!/usr/bin/env bash
# gen_image.sh — designer-cto design-max ③ assets 생성용 gpt-image-1 래퍼.
# usage: gen_image.sh "<prompt>" <out.png> [size] [quality]
#   size 기본 1024x1024, quality 기본 low (≈$0.011/장).
# 키: ~/.harness-claude/openai.env (OPENAI_API_KEY=sk-... 1줄). 부재/형식불량 = exit 2
#   → 호출측은 assets 스킵하고 brief.md 에 "자산 생성 대기" 표기 (degrade).
set -euo pipefail

ENV_FILE="$HOME/.harness-claude/openai.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "gen_image: $ENV_FILE 없음 — assets 스킵 (degrade)" >&2; exit 2
fi
if ! grep -qE '^OPENAI_API_KEY=sk-[A-Za-z0-9_-]+$' "$ENV_FILE"; then
    echo "gen_image: 키 형식 불량 ($ENV_FILE) — OPENAI_API_KEY=sk-... 1줄이어야 함" >&2; exit 2
fi
# shellcheck disable=SC1090
source "$ENV_FILE"

prompt="${1:?usage: gen_image.sh \"<prompt>\" <out.png> [size] [quality]}"
out="${2:?usage: gen_image.sh \"<prompt>\" <out.png> [size] [quality]}"
size="${3:-1024x1024}"
quality="${4:-low}"

resp="$(mktemp)"
trap 'rm -f "$resp"' EXIT

body=$(python3 - "$prompt" "$size" "$quality" <<'PY'
import json, sys
print(json.dumps({"model": "gpt-image-1", "prompt": sys.argv[1],
                  "size": sys.argv[2], "quality": sys.argv[3]}))
PY
)
curl -s https://api.openai.com/v1/images/generations \
    -H "Authorization: Bearer $OPENAI_API_KEY" \
    -H "Content-Type: application/json" \
    -d "$body" > "$resp"

python3 - "$resp" "$out" <<'PY'
import base64, json, sys
d = json.load(open(sys.argv[1]))
if "error" in d:
    sys.exit("gen_image: API error: " + d["error"]["message"][:200])
open(sys.argv[2], "wb").write(base64.b64decode(d["data"][0]["b64_json"]))
print("saved", sys.argv[2], "| tokens:", d.get("usage", {}).get("total_tokens"))
PY
