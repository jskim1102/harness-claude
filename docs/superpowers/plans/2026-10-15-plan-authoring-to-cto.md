# plan.md 작성 주체 CEO → CTO 이관 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** CEO 탭은 빈 빌드 폴더만 만들고, CTO 가 brief 부터 plan.md 작성·확정까지 맡는다. 확정은 사용자 승인 답을 훅이 판정해 잠금 + 팀 스폰 마커 + 카메라 포트 배선을 한 번에 한다.

**Architecture:** 결정론 경계 셋 — (1) `run.sh add-cto` 가 "빈 폴더 = 새 빌드(계획 단계)" 를 판정해 초안 마커를 심고 시작 마커를 보류, (2) `plan_readonly_gate.py` 가 초안 마커로 plan.md 쓰기를 lead 에게만 열고 UserPromptSubmit 에서 "확정/수정할까요?" 승인을 판정, (3) 승인 판정 헬퍼는 `team_hook_common.py` 로 공유. 나머지는 역할 문서(CEO 커맨드 축소, CTO `harness-plan` 스킬 신설, PROCESS/RULES 정합).

**Tech Stack:** Bash (`run.sh`), Python 3.10 표준 라이브러리 훅, Markdown 역할 문서, `tests/smoke.sh`.

**Spec:** `docs/superpowers/specs/2026-10-13-ceo-cto-role-split-design.md`

## Global Constraints

- **git commit/push 금지** — RULES §1. 모든 태스크는 파일 수정까지. (커밋 스텝 없음.)
- README.md 수정 금지 (RULES §1, 사용자 소유). `docs/RUNSH-COMMANDS.txt` 변경 없음 (run.sh 서브커맨드 신설 X, RULES §15).
- 새 슬래시 커맨드 신설 X (`/review-build` 비목표). 기존 두 CEO 커맨드 파일은 **이름 유지** (doctor [2] 가 실존 검사).
- 훅 파일명 `plan_readonly_gate.py` 유지 (살아있는 CTO 세션의 settings.json 이 이 경로를 가리킨다).
- canon 불변식 문구 보존 (doctor [5] / smoke [8]·[13]): PROCESS.md 의 `게이트1·2·3`·phase 순서·`reviewer 호출 필수`, planner.md 의 `phase1 = 환경설정`·`[review]`, role.md/SKILL.md 에 `작업 지시 턴`·`신호 없는 턴`·`work signal`·`substantive user` 문구 금지.
- 마커 경로: 초안 `~/.claude/logs/plan-draft/<name>.draft`, 시작 `~/.claude/logs/started/<name>.started` (safe_key 적용).
- 모든 훅 FAIL OPEN (예외 = allow). UserPromptSubmit 는 절대 exit 2 하지 않는다.
- 문서는 한국어, 기존 문체 유지. 최종: `./run.sh doctor` ALL CLEAN + `./run.sh smoke` FAIL 0.

## Review Focus

1. **계획 중 재스폰** — 초안 마커가 있는 빌드에 `add-cto` 를 다시 치면 시작 마커를 심지 않아야 한다 (심으면 확정 전에 팀이 뜬다). → Task 3 smoke.
2. **남의 빌드 plan.md** — CTO A 가 `claude-project/B/plan.md` 를 쓰면 B 가 초안이어도 차단. → Task 2 smoke.
3. **plan.md 없는 확정** — CTO 가 plan.md 를 쓰기 전에 "확정할까요?" 하고 사용자가 "응" 하면 아무것도 바뀌지 않아야 한다. → Task 2 smoke.
4. **재확정 카메라 포트 중복** — 수정→재확정을 반복해도 `MEDIAMTX_*` 4줄은 한 번만. → Task 2 smoke ([add-cto-wire] D).
5. **`ceo` 폴더** — `claude-project/ceo` 는 plan.md 가 없어 새 규칙상 "새 빌드" 로 읽힌다. `add-cto ceo` 는 명시 거부. → Task 3 smoke.

---

### Task 1: 승인 판정 헬퍼 공유 (`team_hook_common.py`)

**Files:**
- Modify: `hooks/team/team_hook_common.py` (끝에 추가)
- Modify: `hooks/team/start_project_gate.py:62-70, 148-170` (로컬 정의 → import)

**Interfaces:**
- Produces: `team_hook_common.approves(prompt: str) -> bool`, `team_hook_common.last_assistant_text(path: str) -> str`, `team_hook_common.YES_WORDS`, `team_hook_common.NO_RE`
- `start_project_gate._start(name)` 은 **그대로 둔다** (smoke [11] 7번이 `m.STARTED_DIR` 를 패치해 실패 표면화를 본다). Task 2 가 `from start_project_gate import _start` 로 재사용.

- [ ] **Step 1: 헬퍼를 common 으로 옮긴다**

`team_hook_common.py` 끝에 추가 (start_project_gate 의 정의를 이름만 바꿔 이동):

```python
# ---- 사용자 승인 판정 (start_project_gate · plan_readonly_gate 공유) ----
# 두 게이트가 같은 장치를 쓴다: 사용자 프롬프트(모델이 못 꾸밈)가 **직전 CTO
# 메시지의 질문**에 대한 짧은 긍정일 때만 승인. 구현이 갈리면 한쪽만 조여진다.
NO_RE = re.compile(r"아니|ㄴㄴ|싫|말고|하지\s*마|취소|\b(no|nope|stop)\b", re.I)
# 첫 단어 정확 일치만 본다 — 접두 매칭은 "어디까지 했어?"·"해당 부분…" 을 승인으로 오인한다.
YES_WORDS = {"응", "응응", "ㅇ", "ㅇㅇ", "ㅇㅇㅇ", "웅", "어", "네", "네네", "넵", "넵넵", "넹",
             "예", "yes", "y", "yep", "yeah", "sure", "ok", "okay", "오케이", "ㅇㅋ",
             "좋아", "좋아요", "그래", "그래요", "해", "해줘", "해줘요", "해주세요", "해라",
             "ㄱ", "ㄱㄱ", "고", "go", "진행", "진행해", "진행해줘", "진행해주세요", "진행하자",
             "스폰", "스폰해", "스폰해줘", "스폰해주세요", "알았어", "알겠어", "부탁해", "부탁해요",
             "확정", "확정해", "확정해줘", "확정하자", "수정", "수정해", "수정해줘", "수정하자"}


def approves(prompt):
    """짧은 긍정 답("응", "네 진행해", "확정해" …). 부정어가 섞이면 무효."""
    p = (prompt or "").strip()
    if not p or len(p) > 40 or NO_RE.search(p):
        return False
    return re.split(r"[\s,.!?~]+", p.lower())[0] in YES_WORDS


def last_assistant_text(path):
    """transcript 의 마지막 assistant 텍스트 = 사용자가 지금 답하는 CTO 메시지."""
    with open(path, "rb") as fh:
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 1_000_000))  # 긴 세션은 끝부분만 본다
        tail = fh.read().decode("utf-8", "ignore")
    for line in reversed(tail.splitlines()):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        if texts:
            return texts[-1]
    return ""
```

- [ ] **Step 2: start_project_gate 가 import 한다**

`start_project_gate.py` 에서 `NO_RE`·`YES_WORDS`·`_approves`·`_last_assistant_text` 정의를 지우고:

```python
from team_hook_common import read_payload, allow, block, LOG_DIR, approves, last_assistant_text  # noqa: E402
```

`_approved_spawn_question` 안의 `_approves(prompt)` → `approves(prompt)`, `_last_assistant_text(path)` → `last_assistant_text(path)`. `ASK_RE`·`_start`·`TEAM_ROLES` 는 그대로.

- [ ] **Step 3: 검증**

Run: `python3 -m py_compile hooks/team/team_hook_common.py hooks/team/start_project_gate.py && bash tests/smoke.sh 2>&1 | sed -n '/== \[11\]/,/== \[12\]/p' | grep -c '✗'`
Expected: `0`

---

### Task 2: plan 잠금 게이트 (초안/잠금 + 확정·수정 승인 + 카메라 배선)

**Files:**
- Modify: `hooks/team/plan_readonly_gate.py` (전면 재작성 — 파일명 유지)
- Modify: `run.sh:1053-1068` (`_wire_project_env` 멱등), `run.sh:606-619` (CTO settings UserPromptSubmit 에 게이트 추가)
- Test: `tests/smoke.sh` [6c] 확장, [add-cto-wire] (D) 추가

**Interfaces:**
- Consumes: `team_hook_common.approves/last_assistant_text/safe_key/LOG_DIR/repo_root`, `start_project_gate._start(name)`
- Produces: `DRAFT_DIR = ~/.claude/logs/plan-draft/`, `draft_marker(name) -> path`; 확정 시 stdout 1줄 (UserPromptSubmit 컨텍스트). Task 3 의 run.sh 가 같은 마커 경로를 쓴다: `$HOME/.claude/logs/plan-draft/<safe>.draft`.

- [ ] **Step 1: smoke [6c] 를 새 계약으로 바꾼다 (실패 확인용)**

[6c] 블록을 다음으로 교체 (기존 7 케이스 유지 + 초안·승인 케이스):

```bash
echo "== [6c] plan_readonly_gate (plan.md 잠금 — 초안은 lead 만, 확정 후 차단) =="
# 2026-10-15: 계획 작성이 CTO 로 왔다. 초안 마커(~/.claude/logs/plan-draft/<name>.draft)
# 가 있을 때 **lead 만** 쓰고, 없으면(기존 빌드·확정 후) 지금처럼 차단한다.
PRG="$REPO/hooks/team/plan_readonly_gate.py"
PRD="$HOME/.claude/logs/plan-draft"; mkdir -p "$PRD"; rm -f "$PRD"/*.draft
prg(){ # prg <expect-exit> <tool> <file_path> <desc> [role] [transcript]
  local role="${5:-cto:demo}" tp="${6:-/x/lead.jsonl}"
  local out; out=$(echo "{\"tool_name\":\"$2\",\"tool_input\":{\"file_path\":\"$3\"},\"transcript_path\":\"$tp\"}" | HARNESS_ROLE="$role" python3 $PRG 2>/dev/null); local got=$?
  [[ "$got" == "$1" ]] && ok "$4" || bad "$4 (exit $got != $1)"
}
prg 2 Write /r/claude-project/demo/plan.md       "잠금: claude-project 루트 plan.md Write 차단"
prg 2 Edit  /r/modules/demo/plan.md              "잠금: modules 루트 plan.md Edit 차단"
prg 2 MultiEdit /r/claude-project/demo/plan.md   "★MultiEdit 도 차단(file_path 같은 우회로)"
prg 0 Write /r/claude-project/demo/specs/plan.md "중첩 specs/plan.md 통과(루트 한정)"
prg 0 Write /r/other/demo/plan.md                "비빌드 부모 통과"
prg 0 Write /r/claude-project/demo/specs/tasks.md "다른 파일명 통과"
prg 0 Read  /r/claude-project/demo/plan.md       "Read 통과 (읽기는 정당)"
touch "$PRD/demo.draft"
prg 0 Write /r/claude-project/demo/plan.md       "★초안: lead 의 자기 빌드 plan.md Write 허용"
prg 0 Edit  /r/modules/demo/plan.md              "초안: Edit 도 허용"
prg 2 Write /r/claude-project/demo/plan.md       "초안이어도 teammate(/subagents/) 차단" cto:demo /x/subagents/y.jsonl
prg 2 Write /r/claude-project/demo/plan.md       "초안이어도 designer-cto 차단" designer-cto:demo
prg 2 Write /r/claude-project/other/plan.md      "★남의 빌드 plan.md 는 초안 무관 차단"
rm -f "$PRD/demo.draft"
prg 2 Write /r/claude-project/demo/plan.md       "마커 삭제 = 다시 잠금"
check "plan_readonly_gate 깨진 JSON fail-open" 0 bash -c "echo bad | python3 $PRG"
grep -q "plan_readonly_gate.py" "$REPO/run.sh" \
  && ok "plan_readonly_gate: run.sh Write|Edit matcher 배선됨" || bad "plan_readonly_gate: run.sh 배선 누락"
# 확정·수정 승인 (UserPromptSubmit) — 사용자 프롬프트 + 직전 CTO 질문. 빌드 dir 은
# payload cwd (lead 의 cwd = 빌드 dir). 카메라 배선은 run.sh 의 _wire_project_env 를
# source 해 쓴다 — harness 는 스텁으로 가로챈다(실 PORT.md 보호).
PLD="$SMOKE_HOME/plan-lock"; mkdir -p "$PLD/claude-project/pl-cam" "$PLD/claude-project/pl-plain" "$PLD/bin"
printf '#!/usr/bin/env bash\nexit 0\n' > "$PLD/bin/harness"; chmod +x "$PLD/bin/harness"
PLM="$HOME/.claude/logs/started"; mkdir -p "$PLM"
_pl_tr() { python3 -c 'import json,sys; print(json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":sys.argv[1]}]}}, ensure_ascii=False))' "$2" > "$1"; }
_pl_say() { # _pl_say <name> <transcript> <prompt>
  python3 -c 'import json,sys; print(json.dumps({"hook_event_name":"UserPromptSubmit","prompt":sys.argv[1],"transcript_path":sys.argv[2],"cwd":sys.argv[3]}, ensure_ascii=False))' "$3" "$2" "$PLD/claude-project/$1" \
    | PATH="$PLD/bin:$PATH" HARNESS_ROLE="cto:$1" python3 "$PRG" 2>/dev/null; }
_pl_tr "$PLD/ask-confirm.jsonl" "plan.md 를 다 썼습니다. plan.md 확정할까요?"
_pl_tr "$PLD/ask-edit.jsonl" "요구사항이 바뀌어 계획을 고쳐야 합니다. plan.md 수정할까요?"
_pl_tr "$PLD/ask-other.jsonl" "alembic upgrade head 승인해 주시면 진행합니다."
# (1) plan.md 없는 확정 → 무시
touch "$PRD/pl-cam.draft"; rm -f "$PLM/pl-cam.started"
_pl_say pl-cam "$PLD/ask-confirm.jsonl" "응" >/dev/null
[[ -f "$PRD/pl-cam.draft" && ! -f "$PLM/pl-cam.started" ]] \
  && ok "★확정: plan.md 없으면 무시 (마커 유지, 시작 마커 없음)" || bad "확정: plan.md 없는데 잠금/스폰됨"
# (2) 카메라 plan 확정 → 초안 삭제 + 시작 마커 + claim 정리 + MEDIAMTX 4줄
printf '# Plan: pl-cam\n## 1. Build Type\n- deliverable: project\n## 5. Constraints\n- mediamtx self-host\n' > "$PLD/claude-project/pl-cam/plan.md"
printf 'PORT_OFFSET=81\nBACKEND_PORT=8081\n' > "$PLD/claude-project/pl-cam/.env"
mkdir -p "$HOME/.harness-claude/orca-team-spawn-claims/pl-cam"; : > "$HOME/.harness-claude/orca-team-spawn-claims/pl-cam/planner.claimed"
pl_out=$(_pl_say pl-cam "$PLD/ask-confirm.jsonl" "응")
[[ ! -f "$PRD/pl-cam.draft" ]] && ok "★확정: 초안 마커 삭제 = 잠금" || bad "확정 후 초안 마커 잔존"
[[ -f "$PLM/pl-cam.started" ]] && ok "★확정: 시작 마커 기록 (팀 스폰 신호)" || bad "확정 후 시작 마커 없음"
[[ ! -f "$HOME/.harness-claude/orca-team-spawn-claims/pl-cam/planner.claimed" ]] && ok "확정: 이전 claim 정리" || bad "확정 후 claim 잔존"
pl_want=$'MEDIAMTX_API_PORT=10078\nMEDIAMTX_RTSP_PORT=8635\nMEDIAMTX_WEBRTC_PORT=8970\nMEDIAMTX_ICE_UDP_PORT=8270'
[[ "$(grep '^MEDIAMTX_' "$PLD/claude-project/pl-cam/.env")" == "$pl_want" ]] \
  && ok "★확정: 카메라 MEDIAMTX 4줄 = base+offset (offset 81)" || bad "확정: 카메라 포트 불일치 :: $(grep '^MEDIAMTX_' "$PLD/claude-project/pl-cam/.env" | tr '\n' ' ')"
[[ "$pl_out" == *"plan.md 확정"* ]] && ok "확정: 컨텍스트 1줄 출력" || bad "확정: stdout 컨텍스트 없음 :: $pl_out"
prg 2 Write "$PLD/claude-project/pl-cam/plan.md" "확정 후 lead 도 plan.md 차단" cto:pl-cam
# (3) 수정 승인 → 초안 마커 재생성, 시작 마커 그대로
_pl_say pl-cam "$PLD/ask-edit.jsonl" "응" >/dev/null
[[ -f "$PRD/pl-cam.draft" ]] && ok "★수정 승인: 초안 마커 재생성 (잠금 해제)" || bad "수정 승인 후 초안 마커 없음"
# (4) 재확정 → 4줄 중복 없음 (멱등)
_pl_say pl-cam "$PLD/ask-confirm.jsonl" "네" >/dev/null
[[ "$(grep -c '^MEDIAMTX_' "$PLD/claude-project/pl-cam/.env")" == "4" ]] \
  && ok "★재확정: MEDIAMTX 4줄 유지 (중복 없음)" || bad "재확정: MEDIAMTX 중복 :: $(grep -c '^MEDIAMTX_' "$PLD/claude-project/pl-cam/.env")줄"
# (5) 비카메라 확정 → 0줄 (2026-07-21 전 프로젝트 주입 사고 회귀 탐지)
printf '# Plan: pl-plain\n- 그냥 REST API\n' > "$PLD/claude-project/pl-plain/plan.md"
printf 'PORT_OFFSET=82\n' > "$PLD/claude-project/pl-plain/.env"; touch "$PRD/pl-plain.draft"
_pl_say pl-plain "$PLD/ask-confirm.jsonl" "응" >/dev/null
[[ "$(grep -c '^MEDIAMTX_' "$PLD/claude-project/pl-plain/.env")" == "0" ]] \
  && ok "★비카메라 확정: MEDIAMTX 0줄" || bad "비카메라에 mediamtx 주입"
# (6) 무효 답 — 거절 / 다른 질문 / 다른 지시
rm -f "$PRD/pl-plain.draft" "$PLM/pl-plain.started"; touch "$PRD/pl-plain.draft"
_pl_say pl-plain "$PLD/ask-confirm.jsonl" "아니 아직" >/dev/null
[[ -f "$PRD/pl-plain.draft" && ! -f "$PLM/pl-plain.started" ]] && ok "거절('아니 아직') → 무변화" || bad "거절인데 확정됨"
_pl_say pl-plain "$PLD/ask-other.jsonl" "응" >/dev/null
[[ -f "$PRD/pl-plain.draft" && ! -f "$PLM/pl-plain.started" ]] && ok "다른 질문의 '응' → 무변화" || bad "다른 질문의 '응'을 확정으로 오인"
rm -f "$PRD/pl-plain.draft"
_pl_say pl-plain "$PLD/ask-other.jsonl" "응" >/dev/null
[[ ! -f "$PRD/pl-plain.draft" ]] && ok "다른 질문의 '응' → 초안 마커 생성 안 함" || bad "다른 질문의 '응'을 수정 승인으로 오인"
# (7) 비-CTO(ceo) 는 no-op
echo '{"hook_event_name":"UserPromptSubmit","prompt":"응","transcript_path":"'"$PLD/ask-confirm.jsonl"'","cwd":"'"$PLD/claude-project/pl-plain"'"}' | HARNESS_ROLE=ceo python3 "$PRG" >/dev/null 2>&1; [[ $? -eq 0 ]] \
  && ok "plan gate: 비-CTO 세션 → no-op 통과" || bad "plan gate: 비-CTO no-op 실패"
grep -q '"hooks/team/plan_readonly_gate.py"' "$REPO/run.sh" \
  && ok "plan gate: run.sh UserPromptSubmit 배선됨" || bad "plan gate: UserPromptSubmit 배선 누락"
```

> 주의: `grep -q '"hooks/team/plan_readonly_gate.py"'` 대신 실제 템플릿 문자열에 맞춰
> `grep -c 'plan_readonly_gate.py' run.sh` 가 **2 이상**인지 본다 (Write 매처 + UserPromptSubmit).

- [ ] **Step 2: 실패 확인**

Run: `bash tests/smoke.sh 2>&1 | sed -n '/== \[6c\]/,/== \[6d\]/p' | grep -c '✗'`
Expected: `>= 10` (초안 허용·확정·수정 케이스 전부 실패)

- [ ] **Step 3: `_wire_project_env` 멱등 + settings 배선**

`run.sh` `_wire_project_env` 의 `grep -qi mediamtx ... || return 0` 다음 줄에:

```bash
    # 멱등 — 확정 훅(plan_readonly_gate)과 add-cto 가 둘 다 부른다 (2026-10-15).
    grep -q '^MEDIAMTX_API_PORT=' "$env" && return 0
```

CTO settings.json 템플릿의 `UserPromptSubmit` hooks 배열에 `start_project_gate.py` 다음으로 추가:

```json
          {
            "type": "command",
            "command": "python3 $REPO/hooks/team/plan_readonly_gate.py"
          },
```

- [ ] **Step 4: 게이트 재작성**

`hooks/team/plan_readonly_gate.py` 전체:

```python
#!/usr/bin/env python3
"""plan_readonly_gate — 빌드 루트 `plan.md` 의 쓰기 주체와 잠금을 결정론으로 강제한다.

2026-10-15 역할 재분할: `plan.md` 는 **CTO lead 가 계획 단계에 쓴다** (예전엔 CEO
산출물). 그래서 게이트는 "무조건 읽기전용" 에서 "초안이면 lead 만 쓰기, 확정되면
잠금" 으로 바뀐다. 잠금이 없으면 만들다가 계획을 결과에 맞춰 고친다 — 이 게이트가
생긴 이유는 그대로다.

상태 = 초안 마커 유무: `~/.claude/logs/plan-draft/<name>.draft`
  - 있음 = 초안. lead(`HARNESS_ROLE=cto:<name>`, transcript 가 `/subagents/` 아님)가
    **자기 빌드**의 plan.md 를 Write/Edit/MultiEdit 할 수 있다.
  - 없음 = 잠금. 차단. **기존 빌드는 마커가 없으니 그대로 잠금 (이관 0).**
  - 마커를 만드는 곳: `run.sh add-cto` (빈 폴더 = 새 빌드), "plan.md 수정할까요?" 승인.
  - 마커를 지우는 곳: "plan.md 확정할까요?" 승인.

게이트:
  - PreToolUse(Write|Edit|MultiEdit): file_path 가 `<claude-project|modules>/<name>/plan.md`
    이고 (초안 ∧ lead ∧ 자기 빌드) 가 아니면 차단. planner·reviewer(`/subagents/`)·
    designer-cto 는 초안이어도 차단. `specs/plan.md` 같은 하위 경로·다른 이름은 통과.
  - UserPromptSubmit: 사용자 답이 짧은 긍정이고 직전 CTO 메시지가
      "plan.md 확정할까" → 확정: plan.md 실존 확인 → 초안 마커 삭제 → 시작 마커
        (start_project_gate._start — 팀 스폰 신호 + claim 정리) → 카메라 포트 배선
        (run.sh `_wire_project_env`, 멱등) → stdout 1줄(컨텍스트).
      "plan.md 수정할까" → 초안 마커 생성(잠금 해제) → stdout 1줄.
    승인 판정은 reviewer 스폰 질문과 같은 장치(team_hook_common.approves) —
    사용자 프롬프트(모델이 못 꾸밈) + 직전 CTO 메시지의 질문. 다른 질문의 "응" 은 무효.
    빌드 dir = payload cwd (lead 의 cwd = 빌드 dir). 절대 exit 2 하지 않는다.

스코프: CTO project settings.json 에만 배선 (run.sh 의 cto 분기: Write|Edit|MultiEdit
+ UserPromptSubmit). CEO 템플릿엔 없다.

알려진 fail-open 범위(의도적): Bash 경유 쓰기(`cat > plan.md`), codex 세션,
settings 재생성 전의 기존 세션. 기존 게이트들과 같은 posture 다.

FAIL OPEN: 어떤 예외/미지 상태든 allow — 가드는 트립와이어가 아니다.
"""
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from team_hook_common import (  # noqa: E402
    read_payload, allow, block, LOG_DIR, safe_key, repo_root, approves, last_assistant_text,
)
from start_project_gate import _start  # noqa: E402  (시작 마커 + claim 정리 — 구현 하나)

BUILD_BASES = ("claude-project", "modules")
DRAFT_DIR = os.path.join(LOG_DIR, "plan-draft")
ASK_CONFIRM_RE = re.compile(r"plan\.md\s*(를|을)?\s*확정할까")
ASK_EDIT_RE = re.compile(r"plan\.md\s*(를|을)?\s*수정할까")


def _note(msg):
    try:
        print(f"[plan_readonly_gate] {msg}", file=sys.stderr)
    except Exception:
        pass


def _cto_name():
    role = os.environ.get("HARNESS_ROLE", "")
    return role.split(":", 1)[1] if role.startswith("cto:") else ""


def draft_marker(name):
    return os.path.join(DRAFT_DIR, safe_key(name) + ".draft")


def _tool_input(payload):
    return payload.get("tool_input") or payload.get("toolInput") or {}


def _build_root_plan_name(path):
    """path 가 <claude-project|modules>/<name>/plan.md 이면 <name>, 아니면 None.

    루트 한정 — `specs/plan.md` 같은 중첩 plan.md 는 대상 아님(오탐 방지).
    """
    if not path:
        return None
    norm = os.path.normpath(path)
    parent, base = os.path.split(norm)
    if base != "plan.md":
        return None
    grandparent = os.path.dirname(parent)
    if os.path.basename(grandparent) not in BUILD_BASES:
        return None
    return os.path.basename(parent)


def _build_dir(payload):
    """payload cwd 가 <…>/<claude-project|modules>/<name> 이면 그 경로."""
    cwd = str(payload.get("cwd") or "")
    if cwd and os.path.basename(os.path.dirname(cwd)) in BUILD_BASES and os.path.isdir(cwd):
        return cwd
    return ""


def _wire_ports(build_dir):
    """카메라 포트 배선 — run.sh 의 _wire_project_env 를 그대로 쓴다 (구현 하나, 멱등)."""
    run_sh = os.path.join(repo_root(), "run.sh")
    try:
        subprocess.run(
            ["bash", "-c", 'source "$1" >/dev/null 2>&1; _wire_project_env "$2"', "_", run_sh, build_dir],
            check=False, timeout=30, capture_output=True,
        )
    except Exception as exc:
        _note(f"카메라 포트 배선 실패 ({type(exc).__name__}: {exc}) — 수동: .env 의 MEDIAMTX_* 확인")


def _on_prompt(payload, name):
    prompt = payload.get("prompt") or payload.get("user_prompt") or ""
    if not approves(prompt):
        return
    path = payload.get("transcript_path") or payload.get("transcriptPath") or ""
    try:
        asked = last_assistant_text(path) if path else ""
    except Exception as exc:
        _note(f"승인 판정 실패 ({type(exc).__name__}: {exc})")
        return
    marker = draft_marker(name)
    if ASK_CONFIRM_RE.search(asked):
        build_dir = _build_dir(payload)
        if not build_dir or not os.path.isfile(os.path.join(build_dir, "plan.md")):
            _note("확정 무시 — plan.md 가 없다 (먼저 plan.md 를 쓰고 다시 물어라)")
            return
        if not os.path.exists(marker):
            _note("확정 무시 — 초안 상태가 아니다 (이미 잠김)")
            return
        try:
            os.remove(marker)
        except Exception as exc:
            _note(f"초안 마커 삭제 실패 ({type(exc).__name__}: {exc}) — plan.md 가 잠기지 않았다")
            return
        _start(name)
        _wire_ports(build_dir)
        print("[plan_readonly_gate] plan.md 확정 — 잠금 + 시작 마커 기록. 이 턴에 팀(planner·reviewer)을 스폰하고 분해 지시를 기다린다. "
              "카메라 빌드면 .env 에 MEDIAMTX_* 4줄이 들어갔다.")
    elif ASK_EDIT_RE.search(asked):
        try:
            os.makedirs(DRAFT_DIR, exist_ok=True)
            with open(marker, "w") as fh:
                fh.write(name + "\n")
        except Exception as exc:
            _note(f"초안 마커 생성 실패 ({type(exc).__name__}: {exc}) — plan.md 는 여전히 잠김")
            return
        print("[plan_readonly_gate] plan.md 수정 승인 — 잠금 해제(초안). 수정 후 다시 'plan.md 확정할까요?' 로 묻는다.")


def main():
    payload = read_payload()
    event = payload.get("hook_event_name") or payload.get("hookEventName") or ""
    name = _cto_name()

    if event == "UserPromptSubmit":
        if name:
            try:
                _on_prompt(payload, name)
            except Exception as exc:
                _note(f"UserPromptSubmit 처리 실패 ({type(exc).__name__}: {exc})")
        allow()  # 입력 게이트 아님 — 절대 차단하지 않는다

    tool = payload.get("tool_name") or payload.get("toolName") or ""
    if tool not in ("Write", "Edit", "MultiEdit"):
        allow()
    target = _build_root_plan_name(_tool_input(payload).get("file_path") or _tool_input(payload).get("filePath") or "")
    if target is None:
        allow()

    tp = payload.get("transcript_path") or payload.get("transcriptPath") or ""
    is_lead = bool(name) and "/subagents/" not in tp
    if is_lead and target == name and os.path.exists(draft_marker(name)):
        allow("PreToolUse", payload, reason="plan.md 초안 — lead 쓰기 허용")

    if is_lead and target == name:
        why = ("plan.md 잠김 (확정됨). 계획을 바꿔야 하면 이유 한 줄 + 'plan.md 수정할까요?' 로 "
               "사용자에게 묻고 턴을 끝내라 — 승인 답이 잠금을 푼다. 계획-현실 괴리는 specs/spec.md·"
               "specs/tasks.md 갱신으로 (재분해 규모면 사용자에게 — RULES §17).")
    elif is_lead:
        why = f"plan.md 쓰기 차단 — 남의 빌드({target})다. 네 빌드는 {name}."
    else:
        why = ("plan.md 쓰기 차단 — plan.md 는 lead CTO 가 계획 단계에 쓰고 확정 후 잠근다. "
               "teammate·designer 는 쓰지 않는다. 계획에 의문이 있으면 ## 6 Open Questions 를 "
               "사용자에게 질문으로 올려라 (harness-relay-qa).")
    block("PreToolUse", payload, why)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: [add-cto-wire] (D) 멱등 케이스 추가** — (C) 다음에:

```bash
# (D) 멱등 — 확정 훅과 add-cto 가 둘 다 부른다 (2026-10-15). 두 번 불러도 4줄.
_wire_run "$WIRE_TMP/cam" >/dev/null 2>&1
[[ "$(grep -c '^MEDIAMTX_' "$WIRE_TMP/cam/.env")" == "4" ]] \
  && ok "★멱등: 재호출해도 MEDIAMTX 4줄 (중복 없음)" || bad "재호출 시 MEDIAMTX 중복 :: $(grep -c '^MEDIAMTX_' "$WIRE_TMP/cam/.env")줄"
```

- [ ] **Step 6: 통과 확인**

Run: `bash tests/smoke.sh 2>&1 | grep -E '^== |✗' | sed -n '/\[6c\]/,/\[6d\]/p'; bash tests/smoke.sh 2>&1 | tail -3`
Expected: [6c] 에 ✗ 없음, 총계 FAIL 0 (기존 bulk-receipe-v2 netbind 제외 조건은 현행 유지).

---

### Task 3: `run.sh add-cto` — 빈 폴더 = 새 빌드(계획 단계)

**Files:**
- Modify: `run.sh:1035-1038` (`_build_ready` 주석·정의), `run.sh:1104-1137` (resolve 분기), `run.sh:1198-1216` (마커 시딩), `run.sh:1282-1288` (안내 문구), `run.sh:2316-2319` (help)
- Test: `tests/smoke.sh` [1] + 라이프사이클 블록 뒤 `[plan-phase]` 신설

**Interfaces:**
- Consumes: 초안 마커 경로 `$HOME/.claude/logs/plan-draft/<safe>.draft` (Task 2 와 동일 safe_key: `tr -c 'A-Za-z0-9._-' '_'`)
- Produces: 새 빌드일 때 `new_build=1`, 안내 문구 "첫 메시지 = brief".

- [ ] **Step 1: smoke 먼저**

[1] 에 추가: `check "add-cto ceo 거부(CEO 작업공간)" 1 ./run.sh add-cto ceo`

라이프사이클 블록(`add-cto/stop-cto 정상 경로`) 바로 뒤에:

```bash
echo "== [plan-phase] add-cto 빈 폴더 = 새 빌드(계획 단계) (2026-10-15) =="
# CEO 탭 /build-project <name> 이 빈 폴더만 만든다. add-cto 는 plan.md 도 specs/tasks.md
# 도 없는 폴더를 "계획 단계" 로 띄운다: 초안 마커 O, 시작 마커 X (확정 때 심는다).
mkdir -p "$CODEX_TMP/repo/claude-project/plan-smoke"
: > "$ORCA_LOG"; : > "$ORCA_STATE"; rm -f "$ORCA_STATE.repos"
if (
  source "$REPO/run.sh" >/dev/null 2>&1
  set +e
  REPO="$CODEX_TMP/repo"; PATH="$CODEX_TMP/bin:$PATH"
  HOME="$CODEX_TMP/home"; export HOME
  CODEX_HOME="$CODEX_TMP/codex-home"; export CODEX_HOME
  _check_claude_version(){ return 0; }; _ensure_harnessd(){ :; }
  write_role_settings(){ :; }
  cmd_add_cto plan-smoke >/dev/null 2>&1 || exit 1
  [[ -f "$HOME/.claude/logs/plan-draft/plan-smoke.draft" ]] || exit 2
  [[ ! -f "$HOME/.claude/logs/started/plan-smoke.started" ]] || exit 3
  [[ -f "$CODEX_TMP/repo/claude-project/plan-smoke/.env" ]] || exit 4
  # 계획 중 재스폰(plan.md 는 썼지만 아직 초안) → 시작 마커 여전히 X
  : > "$CODEX_TMP/repo/claude-project/plan-smoke/plan.md"
  cmd_add_cto plan-smoke >/dev/null 2>&1 || exit 5
  [[ ! -f "$HOME/.claude/logs/started/plan-smoke.started" ]] || exit 6
  # 확정(초안 마커 삭제) 후 재스폰 → 기존 빌드 규칙 = 시작 마커 시딩
  rm -f "$HOME/.claude/logs/plan-draft/plan-smoke.draft"
  cmd_add_cto plan-smoke >/dev/null 2>&1 || exit 7
  [[ -f "$HOME/.claude/logs/started/plan-smoke.started" ]] || exit 8
  cmd_stop_cto plan-smoke >/dev/null 2>&1; cmd_delete_cto plan-smoke >/dev/null 2>&1
); then
  ok "★add-cto 빈 폴더: 초안 마커 O · 시작 마커 X · 포트 배정 O / 초안 중 재스폰 마커 X / 확정 후 시딩"
else
  bad "add-cto 계획 단계 경로 실패 (exit $?)"
fi
```

- [ ] **Step 2: 실패 확인** — Run: `bash tests/smoke.sh 2>&1 | grep -A1 'plan-phase'` Expected: `✗`

- [ ] **Step 3: run.sh 수정**

`_build_ready` 정의를 교체:

```bash
# 빌드 dir 스폰 가능 검사 (2026-10-15 역할 재분할): 빌드 dir 이 **존재하면** 스폰한다.
#   - plan.md 또는 specs/tasks.md 있음 = 기존 빌드 (지금과 같음)
#   - 둘 다 없음 = 새 빌드(계획 단계) — CEO 탭 /build-project <name> 이 만든 빈 폴더.
#     초안 마커를 심고 시작 마커는 심지 않는다 (plan.md 확정 훅이 심는다).
# 폴더 자체가 없으면 거부 (오타 방지). `ceo` 는 CEO 작업공간이라 거부.
_build_ready() { [[ -d "$1" ]]; }
_build_new()   { [[ -d "$1" && ! -f "$1/plan.md" && ! -f "$1/specs/tasks.md" ]]; }
_draft_marker() { printf '%s/.claude/logs/plan-draft/%s.draft' "$HOME" "$(printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '_')"; }
```

bare-name 분기: `_hits` 0개 에러 문구 → `"error: '$plan_arg' 빌드 dir 없음 — CEO 창에서 /build-project <name> | /build-module <name> 으로 먼저 만들어라."`. 그 앞에 `[[ "$plan_arg" == "ceo" ]] && { echo "error: 'ceo' 는 CEO 작업공간 — CTO 로 띄울 수 없다." >&2; return 1; }`. 경로 분기의 `_build_ready` 실패 문구 → `"error: 빌드 dir 없음"` (이미 `-d` 검사가 앞에 있으므로 분기 자체 제거 가능). `name` 확정 직후에도 `[[ "$name" == "ceo" ]]` 거부.

마커 시딩 블록을:

```bash
    mkdir -p "$HOME/.claude/logs/started" "$HOME/.claude/logs/plan-draft"
    local new_build=0 draft; draft="$(_draft_marker "$name")"
    if _build_new "$dir"; then
        new_build=1
        printf '%s\n' "$name" > "$draft"
        echo "계획 단계: plan.md 없음 → 초안 마커 ($draft). 팀 스폰 마커는 plan.md 확정 때 심는다."
    fi
    if [[ ! -f "$draft" ]]; then
        printf '%s\n' "$name" > "$HOME/.claude/logs/started/$(printf '%s' "$name" | tr -c 'A-Za-z0-9._-' '_').started"
    else
        echo "초안 중: 시작 마커 미시딩 (확정 훅이 심는다)"
    fi
    rm -f "$HOME/.harness-claude/orca-team-spawn-claims/$name"/{planner,designer,reviewer}.claimed 2>/dev/null || true
```

(주석의 "시작 마커를 미리 심는다" 설명은 유지하되 "초안이면 보류" 한 줄 추가. `rm -f "$HOME/.claude/logs/started` 문자열은 **절대 쓰지 않는다** — smoke 회귀 핀.)

말미 안내: `new_build=1` 이면
```
echo "CTO 세션 대기 중 — 계획 단계 (plan.md 없음, build_type=$build_type)."
echo "  다음: ./run.sh attach-cto $name → /model · /effort 설정 → 첫 메시지 = 만들고 싶은 것(brief). CTO 가 plan.md 를 쓰고 '확정할까요?' 로 묻는다."
```
아니면 기존 문구.

help: `# <name> = CEO 가 만든 빌드 dir 이름` → `# <name> = 빌드 dir 이름 (CEO 창 /build-project <name> 이 빈 폴더 생성)`, `# plan.md 없으면 스폰 실패 (1단계: …)` → `# 폴더 있고 plan.md 없음 = 계획 단계로 기동 (CTO 가 brief 부터 plan.md 작성) / 폴더 없음 = 실패`.

- [ ] **Step 4: 통과** — Run: `bash -n run.sh && bash tests/smoke.sh 2>&1 | tail -3` Expected: FAIL 0.

---

### Task 4: CTO 쪽 문서 — `harness-plan` 스킬 신설 + 정합

**Files:**
- Create: `plugins/cto/skills/harness-plan/SKILL.md`
- Modify: `plugins/cto/role.md` (정체성·허용/금지·부팅 시퀀스·/msg-ceo), `plugins/cto/commands/msg-ceo.md`, `plugins/cto/skills/harness-team-spawn/SKILL.md` "When To Spawn", `hooks/session_start.py` STARTUP OVERRIDE, `plugins/_shared/PROCESS.md` §1 타임라인 + 131행, `plugins/_shared/RULES.md` §4(218행)·§7(451행)·§16(633행)·신설 §19, `plugins/cto/agents/planner.md`(3·22·36·47·51행), `plugins/cto/skills/harness-relay-qa/references/skill-batching.md`(11·18-19·23행), `plugins/cto/rules/agent-team-protocol.md`(33행), `harness/gitignore_scan.py`(40행 라벨)

**Interfaces:**
- Produces: 스킬 이름 `harness-plan` (role.md 부팅 0단계·STARTUP OVERRIDE·team-spawn 이 참조). 질문 문구 정본 `plan.md 확정할까요?` / `plan.md 수정할까요?` (Task 2 의 regex 와 일치).

- [ ] **Step 1: `harness-plan/SKILL.md` 작성** — frontmatter `name: harness-plan`, description: "Author and confirm the build's plan.md with the user. Use on a CTO's first turn when the build dir has no plan.md (planning phase — start marker absent), and whenever the user asks to change the plan. Ends by asking `plan.md 확정할까요?`." 본문 = 기존 `build-project.md`/`build-module.md` 절차 이관(brainstorming 축2·축3·재사용 경계(모듈) → Library Check fail-closed → 조건부 understand-anything / `$HARNESS_ROOT/run.sh fetch` → plan.md 템플릿 6칸(deliverable 는 디렉토리로 확정) → plan-ceo-review → 확정 질문 단독 턴), 금지(분해 X, 코드 X, 팀 스폰 X, 확정 전 Codex 발주 X), 계획 변경 절차("수정할까요?" → 승인 → 수정 → 재확정), deep-research 제안 게이트, 모듈 vs 프로젝트 차이(프론트 단순 / 디자인 중요).

- [ ] **Step 2: role.md** — 정체성 1번째 bullet "plan.md(CEO 작성)를 받아" → "계획 단계에 사용자와 `plan.md` 를 쓰고 확정한 뒤(harness-plan)"; 허용 목록에 "`plan.md` 작성·수정 — 초안(계획 단계) 또는 '수정할까요?' 승인 후만 (plan_readonly_gate 결정론)"; 금지 목록의 "`plan.md` 수정 (CEO 산출물 …)" → "잠긴 `plan.md` 수정 — '수정할까요?' 승인 없이 X"; 부팅 시퀀스 앞에 "0. **plan.md 없음 = 계획 단계.** 시작 마커도 없다 — 팀을 스폰하지 말고 `harness-plan` 으로 brief 부터 묻는다 ('시작' 만 와도). 확정 승인 턴에 훅이 시작 마커를 심으니 그 턴에 3번(팀 spawn)으로 이어간다."; 메시지 절 `/msg-ceo` = 하네스 문제 신고 전용.

- [ ] **Step 3: 나머지 정합** — 각 파일의 "CEO 작성/CEO-authored/CEO left" 를 "CTO lead 가 계획 단계에 사용자와 작성·확정" 으로; PROCESS §1 표 1~2행을 spec 의 흐름(0 폴더 생성 · 1 스폰 · 1 계획 · 1 확정 · 2 팀 대기)으로; RULES §19 신설(10줄: 주체·초안/잠금·승인 질문 두 개·enforcer); session_start STARTUP OVERRIDE 에 계획 단계 bullet; team-spawn "When To Spawn" 에 "No marker **and no plan.md** = planning phase: do not spawn and do not ask `스폰할까요?` — run `harness-plan`; the confirm approval seeds the marker."; msg-ceo.md description/본문.

- [ ] **Step 4: 검증** — Run: `./run.sh doctor 2>&1 | tail -3; bash tests/smoke.sh 2>&1 | tail -3; grep -rn "CEO 산출물\|CEO-authored\|CEO 작성" plugins/cto plugins/_shared hooks/session_start.py` Expected: doctor ALL CLEAN, FAIL 0, grep 0건.

---

### Task 5: CEO 쪽 — 커맨드 축소 + role.md

**Files:**
- Modify: `plugins/ceo/commands/build-project.md`, `plugins/ceo/commands/build-module.md` (전면 교체), `plugins/ceo/role.md`
- Test: `tests/smoke.sh` 문구 핀 (Task 4 의 grep 과 같은 블록에 추가)

- [ ] **Step 1: build-project.md**

```markdown
---
description: 새 프로젝트 빌드 폴더 생성 — 빈 폴더만 만든다 (계획·brainstorming·plan.md 는 CTO 탭의 몫). Usage: /build-project <name>
argument-hint: <name>
---

# /build-project <name>

빈 폴더 `claude-project/<name>/` 하나를 만든다. **그게 전부다.** brainstorming·Library
Check·plan.md 작성은 CTO 가 계획 단계에 한다 (`plugins/cto/skills/harness-plan`).

!name='$0'; root="${HARNESS_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"; [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "error: name must be kebab-case (lowercase, digits, hyphens). Usage: /build-project <name>"; exit 1; }; [[ "$name" != "ceo" ]] || { echo "error: 'ceo' 는 CEO 작업공간"; exit 1; }; [[ -n "$root" && -d "$root/claude-project" ]] || { echo "error: HARNESS_ROOT 미확인 — ./run.sh ceo 로 재기동"; exit 1; }; for b in claude-project modules; do [[ -e "$root/$b/$name" ]] && { echo "error: $b/$name 이미 존재 — 기존 빌드면 ./run.sh add-cto $name, 다른 이름을 쓰려면 다시"; exit 1; }; done; mkdir -p "$root/claude-project/$name" && echo "created: claude-project/$name/ (빈 폴더)" && printf '다음 — 새 터미널에서:\n  ./run.sh add-cto %s        # 계획 단계로 기동 (plan.md 없음 = CTO 가 brief 부터)\n  ./run.sh attach-cto %s     # /model · /effort 설정 → 첫 메시지 = 만들고 싶은 것\n' "$name" "$name"

## CEO 가 하는 것 / 하지 않는 것

- 위 출력을 사용자에게 그대로 보여준다. 끝.
- **하지 않는다**: brainstorming, Library Check, plan.md 작성, 축2·축3 추론, 이름 제안
  대화. 사용자가 이름 없이 "프로젝트 만들어" 라고 하면 이름(kebab-case) 하나만 묻고
  이 커맨드를 다시 친다. brief 는 CTO 탭에서 말하라고 안내.
- `add-cto`·`attach-cto` 를 CEO 가 실행하지 않는다 (사용자가 새 터미널에서).

ARGUMENTS: $ARGUMENTS
```

build-module.md 는 `modules/<name>/` 로 같은 구조 (모듈 설명 2줄: 재사용 기능 단위, 프론트 단순 — 상세는 CTO 의 harness-plan).

- [ ] **Step 2: role.md** — "무엇을 하지 않는가" 첫 bullet 의 "단 하나의 예외가 plan.md 초안" 삭제 → "빌드 산출물(plan.md 포함)을 만들거나 고치지 않는다"; 두 번째 bullet "plan.md 초안 외" 삭제; "무엇을 하는가" 제목 "+ 1단계 plan 작성자" 삭제; 0번 → "**새 빌드 폴더 생성.** `/build-project <name>`·`/build-module <name>` = 빈 폴더만. 계획은 CTO."; 1번 라우팅 문구의 "`plan.md` 의 해결이면 … CTO 라우팅" 유지; 2번 `/msg-ceo` = 하네스 문제 신고 전용; 3번 → "사용자가 CEO 창에서 특정 빌드 지시를 주면 **그 CTO 탭에서 직접** 말하라고 안내 (굳이 CEO 경유를 원할 때만 /msg-cto)"; 5번 "예외 = plan.md 초안 작성" 삭제; "포트 충돌 조율" 절 삭제.

- [ ] **Step 3: smoke 문구 핀** — Task 4 Step 4 의 grep 를 smoke [8] 뒤에 추가:

```bash
echo "== [plan-owner] plan.md 주체 = CTO (2026-10-15 역할 재분할 회귀 핀) =="
po_hits=$(grep -rln "CEO 산출물\|CEO-authored\|CEO 작성\|plan.md 초안" "$REPO/plugins/cto" "$REPO/plugins/_shared" "$REPO/plugins/ceo/role.md" "$REPO/hooks/session_start.py" 2>/dev/null | grep -v "폐기\|이력" || true)
[[ -z "$po_hits" ]] && ok "plan.md = CEO 산출물 문구 0건" || bad "plan.md CEO 주체 문구 잔존 :: $(echo "$po_hits" | tr '\n' ' ')"
for f in build-project build-module; do
  grep -qiE "brainstorming|plan-ceo-review|## 4\. Requirements" "$REPO/plugins/ceo/commands/$f.md" \
    && bad "CEO $f.md 가 아직 계획 절차를 품음" || ok "CEO $f.md = 폴더 생성 전용"
  grep -q 'mkdir -p "\$root/' "$REPO/plugins/ceo/commands/$f.md" && ok "CEO $f.md 폴더 생성 !-line" || bad "CEO $f.md 폴더 생성 라인 없음"
done
grep -q "name: harness-plan" "$REPO/plugins/cto/skills/harness-plan/SKILL.md" && ok "CTO harness-plan 스킬 실존" || bad "harness-plan 스킬 없음"
grep -q "plan.md 확정할까요" "$REPO/plugins/cto/skills/harness-plan/SKILL.md" && ok "harness-plan: 확정 질문 문구 = 게이트 regex 와 일치" || bad "harness-plan 확정 질문 문구 불일치"
grep -q "harness-plan" "$REPO/plugins/cto/role.md" && ok "role.md 가 harness-plan 참조" || bad "role.md harness-plan 미참조"
```

- [ ] **Step 4: 검증** — doctor ALL CLEAN + smoke FAIL 0. `!`-line 은 임시 root 로 실행 검증: `HARNESS_ROOT=$(mktemp -d) …` 로 kebab 거부·중복 거부·생성 3케이스를 smoke [plan-owner] 에 넣는다 (파일에서 `!` 줄을 추출해 `$0` 를 치환).

---

### Task 6: 색인·help 정합 + 최종 검증

**Files:**
- Modify: `docs/instruction-authority.md` (행 추가: "plan.md 작성 주체·잠금"; hybrid spawn 행 Notes 에 "새 빌드는 확정 승인이 시딩")
- Modify: `run.sh` help (Task 3 에서 이미), `harness/gitignore_scan.py` 라벨 (Task 4)

- [ ] **Step 1: authority 행**

```
| plan.md 작성 주체·잠금 (계획 단계 lead 만 쓰기 · 확정 후 잠금 · "확정/수정할까요?" 승인 = 훅 판정) | `RULES.md` §19 | `hooks/team/plan_readonly_gate.py`(PreToolUse Write|Edit|MultiEdit + UserPromptSubmit), `run.sh add-cto`(빈 폴더 = 초안 마커, 시작 마커 보류), `plugins/cto/skills/harness-plan/SKILL.md`(절차), `tests/smoke.sh` [6c]·[plan-phase]·[plan-owner] | 결정론(hook) | 2026-10-15 역할 재분할: CEO 는 `/build-project <name>` 로 빈 폴더만; 확정 승인이 잠금+시작 마커+카메라 포트(`_wire_project_env` 멱등)를 한 번에 |
```

- [ ] **Step 2: 최종** — Run: `./run.sh doctor; ./run.sh smoke 2>&1 | tail -5`. Expected: ALL CLEAN, FAIL 0. 그리고 `git status --short | wc -l` 로 변경 파일 목록을 사용자 보고에 싣는다. README 는 안 건드렸음을 보고.
