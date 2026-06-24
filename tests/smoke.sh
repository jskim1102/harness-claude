#!/usr/bin/env bash
# tests/smoke.sh — 하네스 결정론 스모크 스위트.
# 2026-06-12 구현 리뷰(다이나믹 워크플로우 44케이스 + codex)에서 검증된
# 테스트 중 결정론적인 것들을 영구화. 토큰 0, 비파괴 (E2E 스폰 제외 —
# 그건 별도 수동: tests/smoke.sh --e2e).
# 실행: ./run.sh smoke   (또는 bash tests/smoke.sh)
set -u
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"
PASS=0; FAIL=0
ok()   { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad()  { FAIL=$((FAIL+1)); echo "  ✗ $1"; }
check(){ # check <desc> <expected-exit> <cmd...>
  local desc="$1" want="$2"; shift 2
  local out; out=$("$@" 2>&1); local got=$?
  [[ "$got" == "$want" ]] && ok "$desc" || bad "$desc (exit $got != $want) :: $(echo "$out" | head -1)"
}

echo "== [1] run.sh 가드 =="
check "help 동작"                  0 ./run.sh help
check "add-cto plan 없음 → 실패"     1 ./run.sh add-cto claude-project/no-such/plan.md
check "add-cto --module 폐기 안내"   1 ./run.sh add-cto --module
check "add-cto 인자 2개 거부"        1 ./run.sh add-cto a b
check "observe 폐기 안내"            1 ./run.sh observe
check "delete-cto ceo 차단"          1 ./run.sh delete-cto ceo
check "delete-cto 비실존 우아 처리"   0 ./run.sh delete-cto no-such-cto-zz
check "split-cto ceo 차단"           1 ./run.sh split-cto ceo
check "split-cto 비실존 dir 거부"     1 ./run.sh split-cto no-such-build-zz
mkdir -p /tmp/smoke-badbase/x && touch /tmp/smoke-badbase/x/plan.md
check "add-cto 잘못된 base 거부"     1 ./run.sh add-cto /tmp/smoke-badbase/x/plan.md
rm -rf /tmp/smoke-badbase
mkdir -p /tmp/smoke-esc/modules/esc && touch /tmp/smoke-esc/modules/esc/plan.md
check "add-cto 레포 밖 경로 차단"    1 ./run.sh add-cto /tmp/smoke-esc/modules/esc/plan.md
rm -rf /tmp/smoke-esc
out=$(echo "x" | ./run.sh add-cto plan.md 2>&1); [[ $? -ne 0 ]] && ok "add-cto 루트 plan.md 거부" || bad "add-cto 루트 plan.md 거부"

echo "== [2] cto_statusline.py =="
SL="hooks/cto_statusline.py"
mkdir -p /tmp/smoke-sl/specs /tmp/smoke-sl/deep/a/b/c/d/e/f/g
cat > /tmp/smoke-sl/specs/tasks.md <<'EOF'
# Tasks: t
## phase1 — 환경
### phase1.ckpt1 포트
- [x] a
## phase2 — 디자인
### phase2.ckpt1 시안
- [x] b
- [ ] c
### phase2.ckpt2 헤딩만
EOF
o=$(echo '{"workspace":{"current_dir":"/tmp/smoke-sl"}}' | HARNESS_ROLE=cto:t python3 $SL)
[[ "$o" == *"phase2.ckpt1"* && "$o" == *"(2/3)"* ]] && ok "진행중 ckpt + 카운트" || bad "진행중 ckpt :: $o"
o=$(echo '{"workspace":{"current_dir":"/tmp/smoke-sl/deep/a/b/c/d/e/f/g"}}' | python3 $SL)
[[ "$o" == *"phase2.ckpt1"* ]] && ok "깊은 cwd 상향탐색 (7단계+)" || bad "상향탐색 :: $o"
o=$(echo '{"workspace":{"current_dir":"/tmp/no-such-dir-zz"}}' | python3 $SL)
[[ "$o" == *"분해 전"* ]] && ok "tasks.md 없음 → 분해 전" || bad "분해 전 :: $o"
sed -i 's/\[ \]/[x]/' /tmp/smoke-sl/specs/tasks.md
o=$(echo '{"workspace":{"current_dir":"/tmp/smoke-sl"}}' | python3 $SL)
[[ "$o" == *"phase2.ckpt2"* ]] && ok "체크박스 없는 ckpt = 미착수" || bad "헤딩만 ckpt :: $o"
rm -rf /tmp/smoke-sl

echo "== [3] skill_announce.py =="
SA="hooks/team/skill_announce.py"
o=$(echo '{"tool_name":"Skill","tool_input":{"skill":"verify"},"agent_name":"developer"}' | HARNESS_ROLE=ceo python3 $SA 2>&1)
[[ "$o" == *"developer"* && "$o" == *"verify"* ]] && ok "agent_name 표기" || bad "agent_name :: $o"
o=$(echo '{"tool_name":"Skill","tool_input":{"skill":"x"}}' | HARNESS_ROLE=ceo CLAUDE_AGENT_NAME=reviewer python3 $SA 2>&1)
[[ "$o" == *"reviewer"* ]] && ok "env 폴백" || bad "env 폴백 :: $o"
o=$(echo '{"tool_name":"Skill","tool_input":{"skill":"x"}}' | HARNESS_ROLE=ceo python3 $SA 2>&1)
[[ "$o" == *"cto"* ]] && ok "단서 없음 → cto 폴백" || bad "cto 폴백 :: $o"
check "tool_name != Skill 무시"  0 bash -c "echo '{\"tool_name\":\"Bash\"}' | python3 $SA"
check "깨진 JSON fail-open"      0 bash -c "echo 'not-json' | python3 $SA"

echo "== [4] coverage 스캐너 (fail-closed) =="
SC="plugins/cto/skills/harness-task-format/scripts/scan_spec_coverage.sh"
mkdir -p /tmp/smoke-cv/specs
printf '# S\n## Features\n- [F1] a [to-build]\n- [F2] b [supplied:modules/m]\n' > /tmp/smoke-cv/specs/spec.md
printf '# T\n### phase3.ckpt1 x  ← F1\n### phase3.ckpt2 y  ← F2\n' > /tmp/smoke-cv/specs/tasks.md
check "전부 커버 → 0"            0 bash $SC /tmp/smoke-cv/specs/
printf '# T\n### phase3.ckpt1 x  ← F1, ← F9\n' > /tmp/smoke-cv/specs/tasks.md
check "누락+stray → 1"           1 bash $SC /tmp/smoke-cv/specs/
# extract From: 강제 (.sources/ 만 — modules/ 재사용은 면제)
printf '# S\n## Features\n- [F1] crud [supplied:.sources/x/ipcam.py]\n' > /tmp/smoke-cv/specs/spec.md
printf '# T\n### phase3.ckpt1 crud  ← F1\n- [ ] [dev] extract | t.py | copy. From: .sources/x/ipcam.py:L1-9. Run: pytest\n' > /tmp/smoke-cv/specs/tasks.md
check "extract +From: → 0"        0 bash $SC /tmp/smoke-cv/specs/
printf '# T\n### phase3.ckpt1 crud  ← F1\n- [ ] [dev] build crud | t.py | 전부 구현. Run: pytest\n' > /tmp/smoke-cv/specs/tasks.md
check "extract -From: → 1"        1 bash $SC /tmp/smoke-cv/specs/
printf '# S\n## Features\n- [F1] m [supplied:modules/auth]\n' > /tmp/smoke-cv/specs/spec.md
printf '# T\n### phase3.ckpt1 m  ← F1\n- [ ] [dev] mount | app.py | included. Run: pytest\n' > /tmp/smoke-cv/specs/tasks.md
check "modules -From: → 0 (면제)"  0 bash $SC /tmp/smoke-cv/specs/
printf '# S\n## 다른헤딩\n- [F1] a\n' > /tmp/smoke-cv/specs/spec.md
check "ground-truth 없음 → 1"     1 bash $SC /tmp/smoke-cv/specs/
rm -rf /tmp/smoke-cv

echo "== [5] 기타 훅 fail-open =="
check "user_prompt_inbox_check"  0 bash -c "echo '{}' | python3 hooks/user_prompt_inbox_check.py"
check "task_created_format"      0 bash -c "echo '{}' | python3 hooks/team/task_created_format_check.py"
check "task_completed_gate"      0 bash -c "echo '{}' | python3 hooks/team/task_completed_verify_gate.py"
check "teammate_idle"            0 bash -c "echo '{}' | python3 hooks/team/teammate_idle_workcheck.py"

echo "== [6] git_guard (RULES §1·§2·§13 결정론 차단) =="
GG="hooks/git_guard.py"
gg(){ # gg <expect-exit> <command>
  out=$(echo "{\"tool_name\":\"Bash\",\"tool_input\":{\"command\":$(python3 -c "import json,sys;print(json.dumps(sys.argv[1]))" "$2")}}" | python3 $GG 2>/dev/null); got=$?
  [[ "$got" == "$1" ]] && ok "guard[$1]: $2" || bad "guard exit $got != $1 :: $2"
}
gg 2 "git commit -m x"
gg 2 "git push origin main"
gg 2 "git init"
gg 2 "rm -rf src/"
# argument-aware (리뷰 P1): git -C <path> / -c <val> 가 서브커맨드를 못 가리게
gg 2 "git -C . commit -m x"
gg 2 "git -C . reset --hard"
gg 2 "git -C . checkout -- file.py"
gg 2 "git -c user.name=x commit -m y"
# rm 분리/long/대문자 force 변형
gg 2 "rm -r -f src/"
gg 2 "rm --recursive --force src/"
gg 2 "rm -R -f src/"
# git restore: worktree 복원은 파괴(차단), staged-only 는 안전(통과)
gg 2 "git restore file.py"
gg 2 "git restore --staged --worktree file.py"
gg 0 "git restore --staged ."
gg 0 "rm -r src/"
gg 2 "sqlite3 db 'DROP TABLE t'"
gg 2 "psql -c 'ALTER TABLE users ADD COLUMN x int'"
gg 2 "sqlite3 db 'DROP INDEX idx_email'"
gg 0 "alembic upgrade head"
gg 0 "git status"
gg 0 "rm -rf /tmp/x"
gg 2 "docker volume rm rtsp-streaming_ipcam_db"
gg 2 "docker volume prune -f"
gg 2 "docker compose down -v"
gg 2 "docker compose down --volumes"
gg 2 "docker compose -f x.yml down -v"
gg 0 "docker compose down"
gg 0 "$(printf 'docker compose down\nnote: compose down -v 는 git_guard 가 차단')"
gg 0 "docker compose -f x/docker-compose.yml down --remove-orphans"
gg 0 "docker rm -f rtsp-streaming-backend"
gg 0 "HARNESS_USER_OK=fs docker volume rm x"
gg 0 "HARNESS_USER_OK=git git commit -m ok"
# §13 docker build/compose — 개발은 dev 서버, compose 는 '도커화 해' 시만
gg 2 "docker compose up"
gg 2 "docker compose up -d"
gg 2 "docker compose up -d --build"
gg 2 "docker-compose up --build"
gg 2 "docker compose build"
gg 2 "docker build -t app ."
# 예외 ② — 이미지 전용 의존 서비스만 띄우기 (--build 없음) 는 통과
gg 0 "docker compose up -d mediamtx"
gg 0 "docker compose up -d postgres mailhog"
# 사용자 명시('도커화 해') 마커 통과
gg 0 "HARNESS_USER_OK=docker docker compose up -d --build"
gg 0 "HARNESS_USER_OK=docker docker compose build"
# flag 우회 차단 (감사 #1 — regex→shlex 토크나이저): -f/--env-file 끼어도 잡힘
gg 2 "docker compose -f docker-compose.yml up -d --build"
gg 2 "docker compose --env-file .env up -d"
gg 2 "docker-compose -f x.yml up --build"
gg 2 "docker compose -f x.yml build"
gg 2 "/usr/bin/docker compose -p proj up -d"
# 예외 ② — flag + 서비스 명시 up 은 통과
gg 0 "docker compose -f x.yml up -d postgres"
check "git_guard 비Bash 무시"     0 bash -c "echo '{\"tool_name\":\"Edit\"}' | python3 $GG"
check "git_guard 깨진 JSON fail-open" 0 bash -c "echo bad | python3 $GG"

echo "== [7] harness CLI =="
check "roles"                    0 harness roles
check "ports --next 숫자"         0 bash -c "harness ports --next | grep -qE '^[0-9]+$'"
check "ports: RESERVED offset 회피" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.cli import _next_free_offset; assert _next_free_offset([{'offset':1},{'offset':3}])==4, 'offset2=5175 회피 실패'; assert _next_free_offset([{'offset':1},{'offset':3},{'offset':4}])==6, 'offset5=8005 회피 실패'"
check "role regex: codex protocol sender" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.cli import _ROLE_RE; assert _ROLE_RE.match('codex-review:demo'); assert _ROLE_RE.match('codex-protocol-review:harness'); assert not _ROLE_RE.match('codex-protocol-review:bad_name')"
tmp=/tmp/smoke-codex-protocol-review
rm -rf "$tmp"
mkdir -p "$tmp/fakebin" "$tmp/home"
cat > "$tmp/fakebin/codex" <<'PY'
#!/usr/bin/env python3
from pathlib import Path
import sys
args = sys.argv[1:]
prompt = sys.stdin.read()
assert "Codex Protocol Review Agent" in prompt
assert "repo_path:" in prompt and "report_path:" in prompt
out = Path(args[args.index("--output-last-message") + 1])
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text("""# Codex Protocol Review Report

- Target: harness-claude
- Repo path: fake
- Reviewer: Codex protocol-review agent
- Files reviewed: smoke
- Counts by severity: blocker 0, major 0, minor 0, nit 0
- Counts by category: instruction-drift 0, enforcement-gap 0, trust-boundary 0, workflow-risk 0, test-gap 0, quality 0
- Overall risk: low - smoke e2e.

## Findings

No findings.
""", encoding="utf-8")
PY
cat > "$tmp/fakebin/harness" <<EOF
#!/usr/bin/env bash
set -euo pipefail
cd "$REPO"
PYTHONPATH="$REPO" exec python3 -m harness.cli "\$@"
EOF
chmod +x "$tmp/fakebin/codex" "$tmp/fakebin/harness"
out=$(HOME="$tmp/home" PATH="$tmp/fakebin:$PATH" HARNESS_CODEX_REVIEW_FOREGROUND=1 python3 plugins/ceo/scripts/codex_protocol_review_launch.py 2>&1); got=$?
report=$(ls "$tmp"/home/.harness-claude/reviews/codex-protocol-review/harness/review-*.md 2>/dev/null | head -1)
pending="$tmp/home/.harness-claude/reviews/codex-protocol-review/harness/.pending"
inbox=$(HOME="$tmp/home" PATH="$tmp/fakebin:$PATH" HARNESS_ROLE=ceo harness inbox --peek 2>&1)
[[ -f "$pending" ]]; pending_before=$?
consume=$(HOME="$tmp/home" PATH="$tmp/fakebin:$PATH" python3 plugins/ceo/scripts/codex_protocol_review_launch.py <<<'--consume' 2>&1)
[[ "$got" == "0" && -n "$report" && -f "$report" && "$pending_before" == "0" && "$inbox" == *"codex-protocol-review:harness"* && "$inbox" == *"Overall risk: low - smoke e2e."* && "$consume" == *"consumed:"* && ! -f "$pending" ]] \
  && ok "codex-protocol-review fake e2e" || bad "codex-protocol-review fake e2e :: got=$got out=$(echo "$out" | head -1) inbox=$(echo "$inbox" | head -1) consume=$(echo "$consume" | head -1)"
check "daemon import"            0 python3 -c "import harness.daemon"
o=$(grep -c "observe 화면" harness/daemon.py)
[[ "$o" == "0" ]] && ok "daemon 메시지에 observe 없음" || bad "daemon observe 잔재"
check "stall: tasks 미완 카운트" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.daemon import _parse_tasks_incomplete as f; assert f('- [ ] a\n- [✅] b\n- [!] c\n- [x] d')==2, f('got %d' % f('- [ ] a\n- [✅] b\n- [!] c\n- [x] d'))"
check "stall: verdict 결정론" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.daemon import _stall_verdict as v; assert v(True,False,2,400) is True; assert v(False,False,2,400) is False; assert v(True,True,2,400) is False; assert v(True,False,0,400) is False; assert v(True,False,2,100) is False"

echo "== [8] canon 정합성 (doctor [5] RULE A/B + quality) =="
# 현 canon 은 정합 → doctor [5] 섹션이 clean 통과해야 (위반 echo 없음).
d=$(./run.sh doctor 2>&1)
sec5=$(echo "$d" | sed -n '/\[5\] canon/,/== doctor:/p')
[[ "$sec5" == *"불변식 정합"* && "$sec5" != *"✗"* ]] \
  && ok "doctor [5] canon clean 통과" || bad "doctor [5] canon :: $(echo "$sec5" | grep '✗' | head -1)"
if [[ -f plugins/_shared/CODE_QUALITY.md ]] \
  && grep -q "improves or preserves code health" plugins/_shared/CODE_QUALITY.md \
  && grep -q "Correctness" plugins/_shared/CODE_QUALITY.md \
  && grep -q "Rollback" plugins/_shared/CODE_QUALITY.md; then
  ok "quality contract 정본 존재"
else
  bad "quality contract 정본 누락"
fi
if grep -q "Completion Evidence" plugins/cto/agents/developer.md \
  && grep -q "Changed:" plugins/cto/agents/developer.md \
  && grep -q "Tests:" plugins/cto/agents/developer.md \
  && grep -q "Existing pattern followed:" plugins/cto/agents/developer.md \
  && grep -q "Edge/risk considered:" plugins/cto/agents/developer.md \
  && grep -q "Rollback:" plugins/cto/agents/developer.md; then
  ok "developer completion evidence 5줄"
else
  bad "developer completion evidence 게이트 누락"
fi
if grep -q "Quality Classification Gate" plugins/cto/agents/reviewer.md \
  && grep -q "BLOCKER" plugins/cto/agents/reviewer.md \
  && grep -q "SHOULD" plugins/cto/agents/reviewer.md \
  && grep -q "NIT" plugins/cto/agents/reviewer.md \
  && grep -q "Approval requires" plugins/cto/agents/reviewer.md; then
  ok "reviewer BLOCKER/SHOULD/NIT 승인 게이트"
else
  bad "reviewer quality 승인 게이트 누락"
fi
# sentinel 결정론 단위 재현 (canon 파일 비건드림 — tmp 위반 문자열로 grep 로직만 검증).
GATE='docker화 해|docker화|사용자 명시|시만|계획된 ckpt 가|only on|Never Docker compose'
viol=$'phase3 진입 시 docker compose up -d --build 로 전 서비스를 띄운다'
hit=$(printf '%s\n' "$viol" | grep -E 'phase3' | grep -E 'compose up' | grep -vE "$GATE" || true)
[[ -n "$hit" ]] && ok "sentinel: 게이트 없는 phase3+compose up → 위반 검출" || bad "sentinel 위반 미검출"
clean=$'phase3+ 는 dev 서버로 돌린다 — compose up 은 사용자 명시 시만'
hit=$(printf '%s\n' "$clean" | grep -E 'phase3' | grep -E 'compose up' | grep -vE "$GATE" || true)
[[ -z "$hit" ]] && ok "sentinel: 게이트 문구 있는 줄 → 통과" || bad "sentinel false-positive :: $hit"

echo
echo "== smoke: PASS $PASS / FAIL $FAIL =="
[[ $FAIL -eq 0 ]] || exit 1
