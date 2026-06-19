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

echo "== [6] git_guard (RULES §1·§2 결정론 차단) =="
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
gg 0 "$(printf 'docker compose up -d --build\nnote: compose down -v 는 git_guard 가 차단')"
gg 0 "docker compose -f x/docker-compose.yml down --remove-orphans"
gg 0 "docker rm -f rtsp-streaming-backend"
gg 0 "HARNESS_USER_OK=fs docker volume rm x"
gg 0 "HARNESS_USER_OK=git git commit -m ok"
check "git_guard 비Bash 무시"     0 bash -c "echo '{\"tool_name\":\"Edit\"}' | python3 $GG"
check "git_guard 깨진 JSON fail-open" 0 bash -c "echo bad | python3 $GG"

echo "== [7] harness CLI =="
check "roles"                    0 harness roles
check "ports --next 숫자"         0 bash -c "harness ports --next | grep -qE '^[0-9]+$'"
check "ports: RESERVED offset 회피" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.cli import _next_free_offset; assert _next_free_offset([{'offset':1},{'offset':3}])==4, 'offset2=5175 회피 실패'; assert _next_free_offset([{'offset':1},{'offset':3},{'offset':4}])==6, 'offset5=8005 회피 실패'"
check "daemon import"            0 python3 -c "import harness.daemon"
o=$(grep -c "observe 화면" harness/daemon.py)
[[ "$o" == "0" ]] && ok "daemon 메시지에 observe 없음" || bad "daemon observe 잔재"
check "stall: tasks 미완 카운트" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.daemon import _parse_tasks_incomplete as f; assert f('- [ ] a\n- [✅] b\n- [!] c\n- [x] d')==2, f('got %d' % f('- [ ] a\n- [✅] b\n- [!] c\n- [x] d'))"
check "stall: verdict 결정론" 0 python3 -c "import sys; sys.path.insert(0,'.'); from harness.daemon import _stall_verdict as v; assert v(True,False,2,400) is True; assert v(False,False,2,400) is False; assert v(True,True,2,400) is False; assert v(True,False,0,400) is False; assert v(True,False,2,100) is False"

echo
echo "== smoke: PASS $PASS / FAIL $FAIL =="
[[ $FAIL -eq 0 ]] || exit 1
