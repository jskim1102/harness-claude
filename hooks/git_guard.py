#!/usr/bin/env python3
"""PreToolUse(Bash) guard — RULES §1·§2 의 비가역 명령을 결정론으로 차단.

배경 (plans/harness.md "시스템 점검" / docs/LATER.md "Hard rule 결정론 강제"):
CEO/CTO 는 --dangerously-skip-permissions 로 돌아 권한 확인창이 없다.
RULES.md 는 advisory(모델 신뢰) — 모델이 "지금 커밋하는 게 좋겠다"고
합리화하면 막을 게 없었다. 이 훅이 Bash 명령을 실행 직전에 가로채
패턴 매칭으로 거부한다.

차단 카테고리:
  git   — commit / commit --amend / push / tag / reset --hard / rebase /
          checkout -- / init, gh pr create|merge / gh release
  fs    — rm -rf(-fr, -r -f 변형 포함) / find -delete / dd of= / mkfs / wipefs
  db    — DROP TABLE|DATABASE / TRUNCATE / WHERE 없는 DELETE FROM
          (sqlite3·psql·mysql 호출 안에서)

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

# (category, pattern, human reason)
RULES = [
    # ── git (RULES §1) ──
    ("git", r"\bgit\s+(-\S+\s+)*commit\b", "git commit"),
    ("git", r"\bgit\s+(-\S+\s+)*push\b", "git push"),
    ("git", r"\bgit\s+(-\S+\s+)*tag\b", "git tag"),
    ("git", r"\bgit\s+(-\S+\s+)*init\b", "git init"),
    ("git", r"\bgit\s+(-\S+\s+)*reset\s+--hard\b", "git reset --hard"),
    ("git", r"\bgit\s+(-\S+\s+)*rebase\b", "git rebase"),
    ("git", r"\bgit\s+(-\S+\s+)*checkout\s+--\s", "git checkout --"),
    ("git", r"\bgh\s+pr\s+(create|merge)\b", "gh pr create/merge"),
    ("git", r"\bgh\s+release\b", "gh release"),
    # ── fs (RULES §2) ──
    ("fs", r"\brm\s+(-\w*\s+)*-\w*[rf]\w*[rf]\w*\b", "rm -rf"),
    ("fs", r"\bfind\b[^|;&]*-delete\b", "find -delete"),
    ("fs", r"\bdd\s+[^|;&]*\bof=/dev/", "dd of=/dev/*"),
    ("fs", r"\bmkfs\b", "mkfs"),
    ("fs", r"\bwipefs\b", "wipefs"),
    # ── db (RULES §2) ──
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDROP\s+(TABLE|DATABASE)\b", "DROP TABLE/DATABASE"),
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bTRUNCATE\b", "TRUNCATE"),
]
DB_DELETE_RE = re.compile(
    r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDELETE\s+FROM\b(?![^|;&]*\bWHERE\b)",
    re.IGNORECASE,
)
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
