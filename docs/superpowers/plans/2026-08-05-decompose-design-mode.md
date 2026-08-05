# /decompose --design (design-max) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/decompose --design` 의 design-max 모드를 문서 계약 + 최소 헬퍼로 구현 — 사용자↔designer-cto 직접 대화, mobbin 초안(refs/brief/assets), Claude Design 수동 왕복, lead 비관여.

**Architecture:** 실행 주체가 사용자라 코드 변경은 최소 — 역할 문서 4개에 계약을 박고, gpt-image-1 curl 래퍼 스크립트 1개만 추가. 결정론 게이트 추가 없음 (spec: 과잉 게이트 금지).

**Tech Stack:** markdown 역할 문서, bash + curl + python3(json/base64), OpenAI Images API (gpt-image-1).

**Spec:** `docs/superpowers/specs/2026-08-05-decompose-design-mode-design.md`

## Global Constraints

- **git commit/push 절대 금지** — RULES §1, 사용자 명시 지시 시만. 이 계획의 모든 태스크는 파일 수정까지만 한다 (커밋 스텝 없음).
- README.md 생성/수정 금지 (RULES §1).
- canon 불변식 문구 보존 (doctor [5] grep): PROCESS.md 의 `게이트1·2·3`, phase 순서(환경설정/프론트/백엔드), `reviewer 호출 필수` 문구를 삭제·변형하지 않는다. 추가만 한다.
- 일반 `/decompose` 경로(lead inbox 발주)는 문구 하나도 안 바꾼다 — design-max 는 분기 추가.
- 문서는 한국어, 기존 파일 문체/포맷 유지.
- 최종 검증: `./run.sh doctor` ALL CLEAN + `./tests/smoke.sh` FAIL 0.

---

### Task 1: decompose.md `--design` 절 교체

**Files:**
- Modify: `plugins/cto/commands/decompose.md:20-27`

**Interfaces:**
- Produces: `specs/design-mode` 마커 계약 (기존 유지) + design-max 요약 문구. Task 2·3·4 의 문서가 이 절을 참조한다.

- [ ] **Step 1: 현행 절 확인**

Run: `sed -n '15,28p' plugins/cto/commands/decompose.md`
Expected: `**강화 내용은 아직 정의 전**` 문구 존재.

- [ ] **Step 2: 절 교체 (Edit)**

old_string (정확히 이 블록):
```
- **`--design` 디자인 강화 모드** — designer-cto 의 능력을 끌어올리는 분해.
  **강화 내용은 아직 정의 전** (CEO/사용자 논의 중) — 현재는 일반 모드와 동일하게
  분해하되, 다음 한 가지만 추가한다:
  - `<빌드dir>/specs/design-mode` 파일에 `design-max` 한 줄을 기록한다 —
    이후 훅/designer-cto 세션이 읽을 모드 마커 (독립 세션이라 명령 인자가 안
    닿으므로 파일이 전달로다). 이미 있으면 그대로 둔다.
  강화 규칙이 확정되면 이 절이 그 내용으로 교체된다 — 그 전까지 자체 판단으로
  "디자인 심화" 를 임의 발명하지 않는다.
```

new_string:
```
- **`--design` 디자인 강화 모드 (design-max)** — phase2 디자인을 사용자↔designer-cto
  직접 대화로 진행하는 모드 (정본: `docs/superpowers/specs/2026-08-05-decompose-design-mode-design.md`).
  분해 자체는 일반 모드와 동일하되 다음 두 가지가 다르다:
  - `<빌드dir>/specs/design-mode` 파일에 `design-max` 한 줄을 기록한다 —
    이후 CTO/designer-cto 세션이 읽을 모드 마커 (독립 세션이라 명령 인자가 안
    닿으므로 파일이 전달로다). 이미 있으면 그대로 둔다.
  - planner 는 phase2 의 `[design]` task acceptance 에 design-max 산출물 계약을
    명시한다: `specs/design/refs/`(mobbin 레퍼런스 이미지) + `specs/design/brief.md`
    (상세 브리프) + `specs/design/assets/`(AI 생성 자산, 키 없으면 스킵) +
    `specs/design/handoff/`(Claude Design 핸드오프 번들 정합).
  phase2 실행 시 CTO 는 발주하지 않는다 — "phase2 시작하세요 (design-max —
  designer 탭에서 진행)" 안내 후 비관여, 사용자가 산출물 경로를 통보하면 그때
  Codex 프론트 구현을 발주한다 (PROCESS.md phase2 design-max 분기 참조).
```

- [ ] **Step 3: 검증**

Run: `grep -c "design-max" plugins/cto/commands/decompose.md && ! grep -q "정의 전" plugins/cto/commands/decompose.md && echo OK`
Expected: 카운트 ≥ 3, `OK`.

---

### Task 2: designer-cto role.md 에 Design-Max 절 신설 + LATER.md 항목

**Files:**
- Modify: `plugins/designer-cto/role.md` ("## Fixed Skills — project builds" 절 바로 앞에 삽입)
- Modify: `docs/LATER.md` (말미에 항목 1개 추가)

**Interfaces:**
- Consumes: Task 1 의 마커·산출물 계약 명칭 (`specs/design-mode`, `specs/design/refs|brief.md|assets|handoff`).
- Produces: designer 가 따를 실행 절차 + `scripts/gen_image.sh` 호출 계약 (Task 5 가 구현).

- [ ] **Step 1: 삽입 위치 확인**

Run: `grep -n "## Fixed Skills — project builds" plugins/designer-cto/role.md`
Expected: 58 근처 1행.

- [ ] **Step 2: 절 삽입 (Edit)**

old_string:
```
## Fixed Skills — project builds (this exact order)
```

new_string:
```
## Design-Max 모드 (specs/design-mode 마커 존재 시 — 이 절이 아래 Fixed Skills 를 대체)

`<빌드dir>/specs/design-mode` 에 `design-max` 가 있으면 phase2 는 **사용자와 이
터미널에서 직접 대화**로 진행한다. CTO inbox 발주를 기다리지 않는다. 정본:
`docs/superpowers/specs/2026-08-05-decompose-design-mode-design.md`.

1. **레퍼런스 확정** — 두 경로:
   - A) 네가 mobbin MCP(`search_flows`/`search_screens`/`search_sections`)로
     검색해 스크린샷 후보를 제시하고 사용자가 pick.
   - B) 사용자가 mobbin URL 을 주면 URL 에서 앱 이름을 추출해 MCP 검색으로
     역매칭 (URL 직접 fetch 는 403 — 시도하지 마라), 스크린샷을 보여주며
     "이 화면 맞아?" 컨펌.
   확정 즉시 `curl -sL -o specs/design/refs/<이름>.webp <image_url>` 로 저장한다
   — `mobbin.com/api/mcp/short/<id>` 는 서명 URL 이라 만료 전(검색 직후)에 받아야
   한다. 인증 불필요, 768px webp.
2. **초안 제작** — `specs/design/` 아래:
   - `refs/` — 위 레퍼런스 이미지 팩.
   - `brief.md` — 페이지 구조·컴포넌트·인터랙션·수용기준 + 레퍼런스 매핑
     ("로그인 폼 구조 = refs/ig-login.webp 우측" 식) + 생성자산 매핑.
   - `assets/` — 레퍼런스에서 재사용 불가한 사진·일러스트 대체물.
     `plugins/designer-cto/scripts/gen_image.sh "<프롬프트>" specs/design/assets/<이름>.png`
     (기본 1024x1024 low ≈ $0.011/장, 필요시 3·4번째 인자로 size·quality).
     키 파일(`~/.harness-claude/openai.env`) 부재 시 스크립트가 exit 2 —
     그때는 ①② 만으로 진행하고 brief.md 에 "자산 생성 대기" 를 표기한다.
3. **사용자 Claude Design 작업 대기** — 사용자가 refs/assets 로 디자인시스템을
   만들고 brief.md 로 implement 한다. 너는 질문에 답하고 brief 를 갱신할 뿐,
   재촉하지 않는다.
4. **핸드오프 정합** — 사용자가 "Hand off to Claude Code" 번들(tokens css +
   html + 프롬프트)을 `specs/design/handoff/` 에 두면: tokens 를 구현계약
   (`specs/design/web-contract.md`)에 반영하고, handoff HTML 을 컴포넌트·
   레이아웃·반응형 계약으로 번역한다. 캔버스 결과와 계약이 어긋난 채 넘기지 마라.
5. **완료** — `tasks.md` 의 `[design]` 행을 `- [✅]` 로 직접 Edit 하고 산출물
   경로를 사용자에게 보고한다. lead-CTO 통보는 사용자 몫이다 (너는 inbox 로
   CTO 에 완료보고를 보내되, 착수 신호는 사용자→CTO 발화다).

## Fixed Skills — project builds (this exact order)
```

- [ ] **Step 3: LATER.md 항목 추가 (Edit, 파일 말미)**

추가할 내용 (기존 목록 형식에 맞춰):
```
- **designer role.md 죽은 "Claude Design MCP push" 계약 정리** — role.md:43-56 의
  미세조정 루프(DesignSync push→캔버스→export)는 2026-07-29 이후 실사용 0회 +
  2026-08-05 실측으로 캔버스(Projects 탭)는 도구 접근 불가 확정. design-max 는
  수동 왕복으로 대체 완료 — 일반 모드의 이 절을 실태에 맞게 재작성/폐기할지 판단.
```

- [ ] **Step 4: 검증**

Run: `grep -c "Design-Max" plugins/designer-cto/role.md && grep -q "gen_image.sh" plugins/designer-cto/role.md && grep -q "MCP push" docs/LATER.md && echo OK`
Expected: 카운트 ≥ 1, `OK`.

---

### Task 3: PROCESS.md phase2 design-max 분기

**Files:**
- Modify: `plugins/_shared/PROCESS.md:41` (표에 행 추가), `plugins/_shared/PROCESS.md:330-337` (§5 phase2 절에 분기 추가)

**Interfaces:**
- Consumes: Task 1·2 의 마커/산출물 명칭.
- Produces: CTO/designer 세션에 주입되는 공정 정본의 design-max 분기.

- [ ] **Step 1: 표 행 추가 (Edit)**

old_string:
```
| 3 phase2 프론트 | designer-cto → Codex developer | CTO 가 inbox 로 designer 발주 → 시안 → 사용자가 Claude Design 캔버스에서 미세조정 → 계약 확정 → Codex가 실제 프론트 코드 구현 → dev 서버 기동 | 🤖 |
```

new_string:
```
| 3 phase2 프론트 | designer-cto → Codex developer | CTO 가 inbox 로 designer 발주 → 시안 → 사용자가 Claude Design 캔버스에서 미세조정 → 계약 확정 → Codex가 실제 프론트 코드 구현 → dev 서버 기동 | 🤖 |
| 3 phase2 (design-max) | 사용자 ↔ designer-cto → Codex developer | `specs/design-mode` 마커 시: CTO 는 "phase2 시작하세요" 안내 후 비관여 → 사용자↔designer 직접 대화(mobbin refs·brief·AI assets) → 사용자가 Claude Design 완성 후 핸드오프 번들 회수 → designer 계약 정합 → 사용자가 CTO 에 산출물 통보 → CTO 가 Codex 발주 | 🤚 대화 |
```

- [ ] **Step 2: §5 phase2 절에 분기 추가 (Edit)**

old_string:
```
### phase2 프론트 디자인 (designer-cto → Codex developer)
```

new_string:
```
### phase2 프론트 디자인 (designer-cto → Codex developer)
- **design-max 분기** (`specs/design-mode` 마커): CTO 발주·아래 고정 스킬 체인 대신
  designer role.md "Design-Max 모드" 절차를 따른다 — 사용자 직접 대화, 산출물 =
  `specs/design/refs/ + brief.md + assets/ + handoff/`. CTO 는 사용자 통보 후에만
  Codex 발주. 게이트2(dev 서버 3줄 URL 검수)는 동일하게 적용.
```

- [ ] **Step 3: canon 불변식 무손상 검증**

Run: `./run.sh doctor 2>&1 | sed -n '/canon 정합성/,/^---/p'`
Expected: `✓ RULE A/B + reviewer + quality 불변식 정합` (✗ 없음).

---

### Task 4: cto/role.md lead 비관여 규칙

**Files:**
- Modify: `plugins/cto/role.md:35` (designer 행)

**Interfaces:**
- Consumes: Task 3 의 PROCESS.md 분기 (참조 대상).
- Produces: lead-CTO 세션 지침의 design-max 행동 규칙.

- [ ] **Step 1: 행 교체 (Edit)**

old_string:
```
| `designer` (독립 세션) | `designer-cto:{{name}}` + `plugins/designer-cto/role.md` | phase2 프론트 디자인 — `harness send` 로만 소통 |
```

new_string:
```
| `designer` (독립 세션) | `designer-cto:{{name}}` + `plugins/designer-cto/role.md` | phase2 프론트 디자인 — `harness send` 로만 소통. **design-max**(`specs/design-mode` 존재) 면 발주하지 않는다: "phase2 시작하세요 (design-max — designer 탭에서 진행)" 안내 후 비관여, 사용자가 산출물 경로를 통보하면 그때 Codex 발주 (PROCESS.md phase2 design-max 분기) |
```

- [ ] **Step 2: 검증**

Run: `grep -c "design-max" plugins/cto/role.md`
Expected: ≥ 2.

---

### Task 5: gen_image.sh 헬퍼 스크립트

**Files:**
- Create: `plugins/designer-cto/scripts/gen_image.sh` (실행권한)

**Interfaces:**
- Consumes: `~/.harness-claude/openai.env` (`OPENAI_API_KEY=sk-...` 1줄, 600).
- Produces: `gen_image.sh "<prompt>" <out.png> [size=1024x1024] [quality=low]` → out.png 저장, stdout 에 `saved <path> | tokens: N`. 키 파일 부재/형식 불량 = exit 2 (degrade 신호).

- [ ] **Step 1: 스크립트 작성 (Write)**

```bash
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
```

Run: `chmod +x plugins/designer-cto/scripts/gen_image.sh`

- [ ] **Step 2: 문법 검증**

Run: `bash -n plugins/designer-cto/scripts/gen_image.sh && echo syntax-OK`
Expected: `syntax-OK`.

- [ ] **Step 3: degrade 경로 테스트 (키 부재)**

Run: `HOME=/tmp/nokey-$$ plugins/designer-cto/scripts/gen_image.sh "x" /tmp/x.png; echo "exit=$?"`
Expected: stderr 에 `없음 — assets 스킵`, `exit=2`.

- [ ] **Step 4: 인자 누락 테스트**

Run: `plugins/designer-cto/scripts/gen_image.sh 2>&1 | head -1; echo "exit=$?"` (실키 환경)
Expected: usage 메시지, exit ≠ 0.

- [ ] **Step 5: 라이브 1장 테스트 (비용 ≈ $0.011)**

Run: `plugins/designer-cto/scripts/gen_image.sh "minimal abstract test pattern, two colors" /tmp/gen-smoke.png && file /tmp/gen-smoke.png`
Expected: `saved /tmp/gen-smoke.png | tokens: <N>` + `PNG image data`.

---

### Task 6: 최종 결정론 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: doctor**

Run: `./run.sh doctor`
Expected: `== doctor: ALL CLEAN ✓ ==` (advisory ⚠ 기존 3건 무관).

- [ ] **Step 2: smoke 전체**

Run: `./tests/smoke.sh 2>&1 | tail -3`
Expected: `FAIL 0` (기준선 461 PASS + 변동 없음).

- [ ] **Step 3: 일반 모드 무변경 확인**

Run: `git diff --stat plugins/ docs/ | tail -8`
Expected: 변경 파일 = decompose.md·designer-cto/role.md·PROCESS.md·cto/role.md·LATER.md·(신규)gen_image.sh 뿐. 다른 plugins 파일 0.

## Self-Review 결과

- Spec 커버리지: 변경 목록 5개 → Task 1~5 일대일 대응, 검증 = Task 6. 게이트2 유지·역할 경계·degrade 규칙 모두 role/PROCESS 문구에 포함.
- Placeholder: 없음 — 모든 Edit 는 old/new_string 전문, 스크립트 전문 포함.
- 명칭 일관성: `specs/design-mode`·`specs/design/refs|brief.md|assets|handoff`·`gen_image.sh` — Task 1·2·3·4 전부 동일 표기 확인.
- 커밋 스텝 없음 (RULES §1) — 완료 후 커밋 여부는 사용자 지시.
