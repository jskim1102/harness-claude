#!/usr/bin/env python3
"""PreToolUse(Bash) guard — RULES §1·§2 의 비가역 명령을 결정론으로 차단.

배경 (plans/harness.md "시스템 점검" / docs/LATER.md "Hard rule 결정론 강제"):
CEO/CTO 는 --dangerously-skip-permissions 로 돌아 권한 확인창이 없다.
RULES.md 는 advisory(모델 신뢰) — 모델이 "지금 커밋하는 게 좋겠다"고
합리화하면 막을 게 없었다. 이 훅이 Bash 명령을 실행 직전에 가로채
패턴 매칭으로 거부한다.

차단 카테고리:
  git   — commit / commit --amend / push / tag / reset --hard / rebase /
          checkout -- / restore(worktree 복원) / init, gh pr create|merge / gh release
          (전역옵션 `-C <path>`·`-c <val>` 가 끼어도 서브커맨드 탐지)
  fs    — rm -rf(-fr, -r -f 변형 포함) / find -delete / dd of= / mkfs / wipefs /
          docker volume rm|prune / docker compose down -v|--volumes (볼륨=데이터 삭제;
          compose down·docker rm 은 통과)
  db    — DROP TABLE|DATABASE / TRUNCATE / WHERE 없는 DELETE FROM /
          ALTER TABLE / DROP COLUMN|INDEX (raw ad-hoc DDL — RULES §9 는
          스키마 변경을 migration 전용으로 강제. alembic/ORM 은 CLI 를
          안 거치므로 통과; sqlite3·psql·mysql 직접 호출만 차단)

사용자 허가 통로 (override):
  사용자가 명시적으로 시킨 작업("커밋해")은 명령 앞에 마커를 붙여 실행:
      HARNESS_USER_OK=git <명령>
  마커는 명령줄에 그대로 남아 감사(audit) 가능하다. 마커를 사용자 지시
  없이 붙이는 것은 RULES §1 위반 — 훅은 합리화 사고를 막는 장치지
  적대적 에이전트 방어가 아니다 (full bash 환경에서 완전 차단은 불가).

예외:
  - 하네스 자체 스크립트 경유 작업(run.sh delete-cto 등)은 이 훅을 거치지
    않는 별도 프로세스라 영향 없음. 에이전트의 Bash tool 호출만 가드.
  - /tmp 아래 rm -rf 는 허용 (테스트 fixture 정리).

fail-open 아님 — 이 훅은 GATE: 매칭되면 exit 2 + stderr 사유 (Claude Code 가
명령을 실행하지 않고 사유를 모델에 보여줌). 매칭 안 되면 exit 0.
훅 자체 오류는 fail-open (exit 0) — 가드 버그로 시스템 마비 방지.
"""
import json
import re
import sys

OVERRIDE_RE = re.compile(r"\bHARNESS_USER_OK=(\w[\w,-]*)")

# git 전역 옵션(서브커맨드 앞에 오는 것) — 서브커맨드 탐지 전에 소비한다.
# 값을 받는 -C <path> / -c <name=val> 와 --git-dir=… 류가 끼어도 서브커맨드를
# 놓치지 않게 한다. (이전 `(-\S+\s+)*` 는 `git -C . commit` 의 `.` 에서 끊겨
# commit 을 못 봤다 — 리뷰 P1.) 값받는 형(-c/-C)을 일반 -\S+ 보다 먼저 둬서
# 다음 토큰을 값으로 소비하게 한다.
_G = (
    r"(?:\s+(?:-[cC]\s+\S+"
    r"|--(?:git-dir|work-tree|namespace|exec-path|super-prefix|config-env)(?:=\S+|\s+\S+)"
    r"|-\S+))*"
)

# rm 의 recursive·force 플래그를 각각 독립 lookahead 로 본다 (한 토큰 -rf 뿐
# 아니라 -r -f 분리형, --recursive --force long 형, 대문자 -R 까지). 같은 줄
# ([^\n|;&] = 연산자·줄 안 넘음) 안에서만 본다.
_REC = r"(?=[^\n|;&]*\s(?:-\w*[rR]\w*|--recursive)(?:\s|$))"
_FRC = r"(?=[^\n|;&]*\s(?:-\w*f\w*|--force)(?:\s|$))"

# (category, pattern, human reason)
RULES = [
    # ── git (RULES §1) ──
    ("git", r"\bgit" + _G + r"\s+commit\b", "git commit"),
    ("git", r"\bgit" + _G + r"\s+push\b", "git push"),
    ("git", r"\bgit" + _G + r"\s+tag\b", "git tag"),
    ("git", r"\bgit" + _G + r"\s+init\b", "git init"),
    ("git", r"\bgit" + _G + r"\s+reset\s+--hard\b", "git reset --hard"),
    ("git", r"\bgit" + _G + r"\s+rebase\b", "git rebase"),
    ("git", r"\bgit" + _G + r"\s+checkout\s+--\s", "git checkout --"),
    ("git", r"\bgh\s+pr\s+(create|merge)\b", "gh pr create/merge"),
    ("git", r"\bgh\s+release\b", "gh release"),
    # ── fs (RULES §2) ──
    ("fs", r"\brm" + _REC + _FRC, "rm -rf"),
    ("fs", r"\bfind\b[^|;&]*-delete\b", "find -delete"),
    ("fs", r"\bdd\s+[^|;&]*\bof=/dev/", "dd of=/dev/*"),
    ("fs", r"\bmkfs\b", "mkfs"),
    ("fs", r"\bwipefs\b", "wipefs"),
    # docker volume 파괴 (데이터 손실 = §2). 06-12 stale volume 사고 + [26] 위반
    # (developer 가 CEO 보호 볼륨을 compose down -v 로 삭제 — git_guard 미차단이 원인).
    # `compose down`(볼륨 보존)·`docker rm`(컨테이너; run.sh _down_compose_stack 사용)은 통과.
    ("fs", r"\bdocker\s+volume\s+rm\b", "docker volume rm (볼륨 삭제)"),
    ("fs", r"\bdocker\s+volume\s+prune\b", "docker volume prune"),
    # 한 줄 안에서만 매칭 ([^|;&\n] = 줄 안 넘음) — descriptive 멀티라인 prose(메시지·
    # decisions·tasks 에 명령 언급)는 안 걸리고, 실제 1줄 명령만 잡는다.
    ("fs", r"\bdocker(\s+compose|-compose)\b[^|;&\n]*\bdown\b[^|;&\n]*(\s-v\b|\s--volumes\b)", "docker compose down -v (볼륨 삭제)"),
    # ── db (RULES §2) ──
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDROP\s+(TABLE|DATABASE)\b", "DROP TABLE/DATABASE"),
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bTRUNCATE\b", "TRUNCATE"),
    # RULES §9 — 스키마 변경은 migration 전용. raw CLI DDL 차단 (alembic/ORM 은 CLI 경유 X → 통과).
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bALTER\s+TABLE\b", "ALTER TABLE (ad-hoc DDL — migration 사용)"),
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDROP\s+(COLUMN|INDEX)\b", "DROP COLUMN/INDEX (ad-hoc DDL — migration 사용)"),
]
DB_DELETE_RE = re.compile(
    r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDELETE\s+FROM\b(?![^|;&]*\bWHERE\b)",
    re.IGNORECASE,
)
# git restore 기본은 worktree 복원(작업본 폐기) = `checkout --` 동급 파괴 (리뷰 P1).
# '--staged'(-S) 만 있으면 unstage 라 안전; '--worktree'(-W) 포함이면 파괴.
GIT_RESTORE_RE = re.compile(r"\bgit" + _G + r"\s+restore\b(?P<tail>[^\n|;&]*)", re.IGNORECASE)
TMP_RM_RE = re.compile(r"\brm\s+(-\w+\s+)*(['\"]?/tmp/|\$TMPDIR)")


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    cmd = str((payload.get("tool_input") or {}).get("command", ""))
    if not cmd:
        return 0

    overrides = set()
    m = OVERRIDE_RE.search(cmd)
    if m:
        overrides = {tok.strip() for tok in m.group(1).split(",") if tok.strip()}

    hits = []
    for cat, pat, reason in RULES:
        if re.search(pat, cmd, re.IGNORECASE):
            # /tmp 정리용 rm 은 허용
            if reason == "rm -rf" and TMP_RM_RE.search(cmd):
                continue
            if cat in overrides:
                continue  # 사용자 허가 마커 — 통과 (감사 가능)
            hits.append((cat, reason))
    if DB_DELETE_RE.search(cmd) and "db" not in overrides:
        hits.append(("db", "DELETE FROM (WHERE 없음)"))
    for m in GIT_RESTORE_RE.finditer(cmd):
        tail = m.group("tail")
        staged = re.search(r"(?:^|\s)(?:--staged|-S)\b", tail)
        worktree = re.search(r"(?:^|\s)(?:--worktree|-W)\b", tail)
        if staged and not worktree:
            continue  # unstage-only — 안전
        if "git" not in overrides:
            hits.append(("git", "git restore (worktree 복원 — 작업본 파괴)"))
        break

    if not hits:
        return 0

    cats = sorted({c for c, _ in hits})
    reasons = ", ".join(r for _, r in hits)
    sys.stderr.write(
        f"[git_guard] 차단: {reasons} — RULES §1·§2 비가역 명령은 사용자가 "
        f"명시적으로 지시해야 실행할 수 있다.\n"
        f"사용자에게 허가를 요청하라. 사용자가 이미 명시 지시했다면 명령 앞에 "
        f"마커를 붙여 재실행: HARNESS_USER_OK={','.join(cats)} <명령>\n"
        f"(마커를 사용자 지시 없이 붙이는 것은 RULES §1 위반이다.)\n"
    )
    return 2  # PreToolUse block


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(0)  # 가드 자체 버그는 fail-open
