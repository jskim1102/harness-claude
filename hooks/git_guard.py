#!/usr/bin/env python3
"""PreToolUse(Bash) guard — RULES §1·§2 의 비가역 명령을 결정론으로 차단.

배경 (docs/LATER.md "Hard rule 결정론 강제"):
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
          안 거치므로 통과; sqlite3·psql·mysql 직접 호출만 차단) +
          `harness db drop`·`dropdb` (공유 pg db-per-project 회수 — 실 DROP 은
          docker exec dropdb 경로라 위 psql/DROP 정규식엔 안 잡혀 별도 차단)
  docker — docker build / docker compose build / `--build` 포함 up /
          서비스 미지정 bare `up`·`up -d` (전 서비스 = app 컨테이너 기동).
          RULES §13: 개발·검수는 dev 서버(./dev.sh up)로, compose 는 사용자가
          "docker화 해" 할 때만. 예외 ② — 이미지 전용 의존 서비스(mediamtx 등)
          만 띄우는 `up [-d] <service…>`(--build 없음)는 통과 (app 코드는 dev 서버).
          `compose down`·`docker rm` 은 통과.
  port  — §4 할당 포트 바인딩 (2026-08-04 사고): 임시 서버(http.server)는 자기
          FRONTEND_PORT(목업 게이트 정본)만 허용 — 자기 BACKEND_PORT 포함 그 외
          할당 포트 차단. bind 서버(uvicorn/vite 등 `--port`·docker `-p N:`)가
          타 프로젝트 할당 포트를 잡는 것도 차단. 자기 포트 정상 기동·접속
          클라이언트(`psql --port` 등)·공유 인프라(5432/5435)는 통과.

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
import os
import re
import shlex
import sys

OVERRIDE_RE = re.compile(r"\bHARNESS_USER_OK=(\w[\w,-]*)")

# 예외 ② fallback — compose 파일을 못 읽을 때만 쓰는 보수적 이미지-전용 의존
# 서비스 이름 화이트리스트. 정상 경로는 compose 의 build: 유무로 판정한다.
_DEP_SERVICE_NAMES = {
    "mediamtx", "postgres", "postgresql", "pg", "db", "redis", "minio",
    "rabbitmq", "mongo", "mongodb", "nats", "kafka", "zookeeper",
    "elasticsearch", "adminer",
}
_COMPOSE_DEFAULT_NAMES = (
    "docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml",
)


def _load_compose_services(rest: list[str]) -> dict | None:
    """compose 파일을 파싱해 {service: def} 를 반환. -f <file> 우선, 없으면 cwd
    표준 이름. 읽기/파싱 실패 시 None (호출부가 보수적 fallback)."""
    try:
        import yaml  # PyYAML 없으면 fallback
    except Exception:
        return None
    path = None
    for i, t in enumerate(rest):
        if t in ("-f", "--file") and i + 1 < len(rest):
            path = rest[i + 1]
            break
        if t.startswith("--file="):
            path = t.split("=", 1)[1]
            break
    candidates = [path] if path else list(_COMPOSE_DEFAULT_NAMES)
    for cand in candidates:
        if not cand:
            continue
        p = cand if os.path.isabs(cand) else os.path.join(os.getcwd(), cand)
        try:
            with open(p, "r") as fh:
                data = yaml.safe_load(fh)
        except Exception:
            continue
        if isinstance(data, dict) and isinstance(data.get("services"), dict):
            return data["services"]
    return None


def _service_is_app(service: str, services: dict | None) -> bool:
    """True = app 서비스(마커 필요/차단), False = 이미지-전용 의존(통과).
    보수적: 판정 불가면 app 취급(fail-closed)."""
    if services is None:
        # compose 못 읽음 → 이름 화이트리스트 fallback (보수적)
        return service.lower() not in _DEP_SERVICE_NAMES
    defn = services.get(service)
    if not isinstance(defn, dict):
        return True  # 서비스 정의 못 찾음 → 보수적 차단
    if "build" in defn:
        return True  # build: 있음 = app 이미지
    if "image" in defn:
        return False  # image 전용 = 의존 서비스
    return True  # 애매 → 보수적 차단

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

# rm 의 recursive·force 플래그 어휘 — 한 토큰 -rf 뿐 아니라 -r -f 분리형,
# --recursive --force long 형, 대문자 -R 까지. 아래 두 표현이 이 어휘를 공유해
# 정의가 갈라지지 않게 한다:
#   _REC/_FRC       = raw 텍스트 lookahead (RULES 표 표기용)
#   _REC_RE/_FRC_RE = 토큰 하나가 그 플래그인지 (_rm_is_blockable 세그먼트 판정용)
_REC_TOK = r"-\w*[rR]\w*|--recursive"
_FRC_TOK = r"-\w*f\w*|--force"
# 같은 줄 ([^\n|;&] = 연산자·줄 안 넘음) 안에서만 본다.
_REC = rf"(?=[^\n|;&]*\s(?:{_REC_TOK})(?:\s|$))"
_FRC = rf"(?=[^\n|;&]*\s(?:{_FRC_TOK})(?:\s|$))"

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
    # git worktree remove/prune = 미커밋 작업본 삭제 (2026-07-27 갭). 빌드 repo 는
    # 커밋이 1~11개뿐이고 미저장 파일이 22~47개라, worktree 하나를 지우면 그게 곧
    # 데이터 손실이다. `superpowers:using-git-worktrees` 스킬이 설치돼 있어 어떤
    # 에이전트든 지금 호출할 수 있는데 게이트가 전무했다. add/list 는 비파괴 → 통과.
    ("git", r"\bgit" + _G + r"\s+worktree\s+(remove|prune)\b", "git worktree remove/prune (미커밋 작업본 삭제)"),
    # 대시보드 git 쓰기 엔드포인트 = §1 의 HTTP 우회로 (2026-07-31 신설).
    # 대시보드는 mutation 을 `DASH_TOKEN`(레포 루트 `.env`) + `X-Dash-Token` 헤더로
    # 막지만, 에이전트는 같은 유저·같은 머신이라 그 파일을 그냥 읽는다. 그러면
    # `curl -X POST .../api/cto/<n>/commit` 한 줄로 §1 이 무력화된다 — 위 규칙들은
    # `git` 명령을 보는데 이건 `curl` 이라 안 걸린다. **버튼은 사용자 것이고, 그
    # 버튼을 에이전트가 대신 누르는 경로를 막는 것**이 이 항목이다.
    # 도구 무관하게 경로 문자열로 잡는다 (curl·wget·httpie·python requests 전부).
    # stage(`/stage`)는 제외 — `git add` 는 애초에 §1 밖이다.
    # 하네스 루트용 `/api/harness/*` 도 같은 §1 이다 (2026-07-31 대시보드 확장).
    ("git", r"/api/(cto/[^\s\"']+|harness)/(commit|push|merge)\b",
     "대시보드 git 쓰기 엔드포인트 HTTP 호출 (§1 우회)"),
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
    # docker compose down -v (볼륨 삭제) 는 regex 가 아니라 _docker_downv_blocked() 토큰화로
    # 검사한다 (아래 main). 정규식 substring 은 printf/echo/보고문 속 인용 문자열의
    # "docker compose down -v" 를 실명령으로 오탐했다 (2026-07-18 keypoint 리포트 — CEO
    # 보고문에 그 문구를 인용한 harness send·grep 이 차단됨). rm/build/up 과 동일하게 명령
    # 위치 토큰으로 판정 → 인용 데이터 제외.
    # ── db (RULES §2) ──
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDROP\s+(TABLE|DATABASE)\b", "DROP TABLE/DATABASE"),
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bTRUNCATE\b", "TRUNCATE"),
    # RULES §9 — 스키마 변경은 migration 전용. raw CLI DDL 차단 (alembic/ORM 은 CLI 경유 X → 통과).
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bALTER\s+TABLE\b", "ALTER TABLE (ad-hoc DDL — migration 사용)"),
    ("db", r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDROP\s+(COLUMN|INDEX)\b", "DROP COLUMN/INDEX (ad-hoc DDL — migration 사용)"),
    # 공유 pg db-per-project 회수 (RULES §9). `harness db drop` 의 실 DROP 은
    # `docker exec … dropdb` 경로라 위 psql/DROP 정규식에 안 잡힌다(RULES §9 가
    # 명시한 가드 공백). drop 만 잡고 provision/createdb(비파괴)는 통과. 한 줄 안
    # ([^|;&\n])에서만 매칭 → 멀티라인 prose 의 명령 언급은 안 걸린다.
    ("db", r"\bharness\b[^|;&\n]*\bdb\b[^|;&\n]*\bdrop\b", "harness db drop (공유 pg DROP DATABASE)"),
    ("db", r"\bdropdb\b", "dropdb (공유 pg DROP DATABASE)"),
    # orca orchestration reset — 인자 없는 bare reset 이 `--all` 기본이라 런타임
    # 전역 orchestration 상태(tasks/messages/dispatch/gates)를 확인 없이 전부 지운다.
    # 하네스는 이 기능을 채택하지 않았지만 CLI 는 존재하므로 오타·실수 경로를 막는다
    # (2026-07-27). task-list/dispatch-show 같은 조회는 통과.
    ("fs", r"\borca(-ide|-dev)?\s+orchestration\s+reset\b", "orca orchestration reset (전역 상태 삭제)"),
    # ── docker (RULES §13) 는 regex 가 아니라 _docker_hits() 토크나이저로 검사 (아래).
    #    regex 는 `compose -f x.yml up` 처럼 flag 가 끼면 우회됐다 (감사 #1).
]
DB_DELETE_RE = re.compile(
    r"\b(sqlite3|psql|mysql)\b[^|;&]*\bDELETE\s+FROM\b(?![^|;&]*\bWHERE\b)",
    re.IGNORECASE,
)
# git restore 기본은 worktree 복원(작업본 폐기) = `checkout --` 동급 파괴 (리뷰 P1).
# '--staged'(-S) 만 있으면 unstage 라 안전; '--worktree'(-W) 포함이면 파괴.
GIT_RESTORE_RE = re.compile(r"\bgit" + _G + r"\s+restore\b(?P<tail>[^\n|;&]*)", re.IGNORECASE)

# rm -rf 세그먼트별 검사기 (protocol-review F2). 과거엔 하나의 TMP_RM_RE 를 명령
# 전체에 매칭해, /tmp rm 이 어디든 한 번 있으면 rm 게이트 전체를 껐다 — 그래서
# `rm -rf /tmp/x; rm -rf src/` 나 `rm -rf /tmp/x src/` 가 통과했다(안전한 /tmp rm 이
# 파괴적 rm 을 가림). 이제 각 shell 세그먼트의 rm -rf 를 독립 판정하고, 그 세그먼트의
# 타겟이 전부 /tmp·$TMPDIR 하위일 때만 예외로 허용한다.
_RM_RULE_RE = re.compile(r"\brm" + _REC + _FRC, re.IGNORECASE)

# 토큰 단위 플래그 판정 — 세그먼트의 rm -rf 여부는 raw 텍스트가 아니라 토큰으로
# 본다. raw 텍스트로 보면 따옴표 안의 `;` 가 lookahead 의 [^\n|;&]* 를 막아
# `rm "a;b" -rf src/` 의 -rf 를 못 본다 (F2-CLASS-RM). 토큰은 shlex 가 이미
# 따옴표를 벗겨놨으므로 구분자에 가리지 않는다.
_REC_RE = re.compile(rf"^(?:{_REC_TOK})$", re.IGNORECASE)
_FRC_RE = re.compile(rf"^(?:{_FRC_TOK})$", re.IGNORECASE)

# pre-filter — rm 토큰 자체의 존재만 raw 로 본다(따옴표에 안 가림). 플래그까지 raw
# lookahead 로 보던 예전 pre-filter(_RM_RULE_RE)는 위 F2-CLASS-RM 입력에서 매칭에
# 실패해, 정작 따옴표를 아는 _shell_segments 에 도달조차 못 했다.
_RM_TOKEN_RE = re.compile(r"\brm\b", re.IGNORECASE)

# 명령 문자열을 인자로 받아 **실행**하는 명령들. 이들만 토큰 **내용**까지 검사한다
# (`sh -c "rm -rf src/"` 처럼 rm 이 따옴표 안에 통째로 들어간 꼴).
# 이 울타리가 없으면 "rm -rf" 라는 **문자열**을 넘기는 평범한 명령까지 걸렸다 —
# `grep -rn "rm -rf" docs/`, `rg "rm -rf" plugins/`, `git log --grep="rm -rf"`
# 가 전부 차단됐다 (이 저장소를 감사하는 사람이 실제로 칠 법한 명령).
# sudo/env 는 넣지 않는다 — 명령을 감싸긴 하지만 문자열을 실행하진 않아서
# `sudo grep -rn "rm -rf" docs/` 까지 걸린다. `sudo rm -rf src/` 는 rm 이 독립
# 토큰이라 아래 일반 경로가 이미 잡는다.
_EXEC_WRAPPERS = {
    "sh", "bash", "zsh", "dash", "ksh", "ash",      # 셸 -c
    "ssh", "eval", "su",                            # 원격/치환 실행
    "python", "python3", "perl", "ruby", "node",    # -c/-e 로 코드 실행
}


def _has_exec_wrapper(toks: list[str]) -> bool:
    """세그먼트가 '문자열을 명령으로 실행하는' 명령을 포함하는지 (경로형 포함)."""
    return any(os.path.basename(t) in _EXEC_WRAPPERS for t in toks)

# 세그먼트 구분자 = shlex 가 독립 토큰으로 주는 연산자 (`;` `&&` `||` `|` `&`
# 와 `()` `<>`), 그리고 개행. 이 문자로만 이뤄진 토큰 = 연산자.
# 개행을 shlex 의 punctuation_chars 에 넣고 whitespace 에서 빼는 이유:
# 예전엔 lex 전에 cmd.splitlines() 로 미리 쪼갰는데, 그러면 **따옴표 안의**
# 개행에서도 쪼개져 각 줄의 따옴표가 안 닫힌 꼴이 되고 → ValueError → None →
# 호출부 fallback 으로 새어나갔다 (F2-DOCKER-NEWLINE-FALLBACK:
# `docker compose -f "a\nb.yml" build` 가 통과). 개행을 연산자 토큰으로
# 다루면 따옴표 밖 개행만 세그먼트를 끊고, 따옴표 안 개행은 토큰에 남는다.
_PUNCT_CHARS = ";&|()<>\n"
_OP_CHARS = set(_PUNCT_CHARS)
_TMP_ROOT = "/tmp"

# 리다이렉션 fd 번호 (`2>/dev/null` 의 `2`). shlex 는 `>` 만 연산자 토큰으로 주고
# 앞의 fd 번호는 평범한 단어로 남긴다 — 그대로 두면 `rm -rf /tmp/x 2>/dev/null`
# 의 타겟이 ['/tmp/x','2'] 가 돼 `2` 가 비-/tmp 타겟으로 오인돼 차단됐다.
_FD_RE = re.compile(r"^[0-9]+$")


def _is_tmp_target(tok: str) -> bool:
    """rm 타겟 하나가 /tmp **하위**인지 ($TMPDIR 포함). /tmp 루트 자신은 제외.
    단순 prefix 비교(`startswith("/tmp/")`)는 `/tmp/../src` 로 어디든 탈출할 수
    있었고, `startswith("$TMPDIR")` 는 변수명 경계가 없어 `$TMPDIRX` 까지
    /tmp 로 쳐줬다. normpath 로 정규화한 뒤 /tmp 안에 들어있는지 확인한다.
    realpath 가 아니라 normpath 인 이유: 이 훅은 텍스트 가드다 — fs 접근·
    symlink 추적·TOCTOU 를 끌어들이지 않는다."""
    if tok.startswith("$TMPDIR"):
        rest = tok[len("$TMPDIR"):]
        if rest and not rest.startswith("/"):
            return False  # $TMPDIRX… = 이름이 다른 변수 (경계 확인)
        tok = _TMP_ROOT + rest  # $TMPDIR → /tmp 로 놓고 같은 정규화 적용
    norm = os.path.normpath(tok)
    # /tmp 루트 자신은 예외가 아니다. 예외의 목적은 "테스트 fixture 정리"이고,
    # /tmp 통째 삭제는 smoke fixture·다른 에이전트 scratchpad·runtime 소켓까지
    # 날린다. 실제 정리 명령은 전부 하위 경로를 지목한다 (/tmp/x, $TMPDIR/x,
    # /tmp/*). normpath 가 `/tmp/`·`/tmp/.`·bare `$TMPDIR` 를 `/tmp` 로 접으므로
    # 이 한 줄이 그 변형까지 같이 막는다.
    return norm.startswith(_TMP_ROOT + os.sep)


def _shell_segments(cmd: str) -> list[list[str]] | None:
    """명령을 shell 세그먼트(토큰 리스트)들로 쪼갠다. 파싱 불가면 None.
    raw 텍스트를 `[\\n;&|]` 로 쪼개면 따옴표 안의 `;` 에서도 쪼개져
    `rm -rf "/tmp/a;b" src/` 가 `rm -rf "/tmp/a`(타겟=/tmp/a → 허용) 와
    `b" src/`(rm 없음 → 무시) 로 찢어졌다 — 실제 shell 은 src/ 까지 rm 에
    넘긴다. shlex(punctuation_chars=True) 는 따옴표를 벗기고 연산자만 독립
    토큰으로 주므로 따옴표 안의 `;` 는 세그먼트를 못 쪼갠다.

    개행도 (따옴표 밖일 때만) 세그먼트를 끊는다 — lex 전에 splitlines() 로
    미리 쪼개면 따옴표 안 개행까지 끊겨 파싱이 깨졌다 (_PUNCT_CHARS 주석)."""
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=_PUNCT_CHARS)
        lex.whitespace_split = True
        lex.whitespace = " \t\r"  # 개행은 whitespace 가 아니라 연산자로 취급
        lex.commenters = ""  # `#` 를 주석으로 먹지 않게 (shlex.split 과 동일)
        toks = list(lex)
    except ValueError:
        return None  # 따옴표 안 닫힘 등 — 호출부가 보수적 판단
    segs: list[list[str]] = []
    cur: list[str] = []
    for t in toks:
        if t and all(ch in _OP_CHARS for ch in t):
            # `2>`·`2>&1` 의 fd 번호는 리다이렉션의 일부지 명령 인자가 아니다.
            # (`&&`·`;` 앞의 숫자는 진짜 인자이므로 리다이렉션 연산자일 때만)
            if t[0] in "<>" and cur and _FD_RE.match(cur[-1]):
                cur.pop()
            segs.append(cur)
            cur = []
        else:
            cur.append(t)
    segs.append(cur)
    return segs


# 세그먼트 안에서는 `;`·`&`·`|`·개행이 **데이터**다 (따옴표 안이었으니 shlex 가
# 토큰에 남겼다). 아래 RULES 정규식들은 "한 명령 안에서만 매칭"하려고 `[^|;&\n]*`
# 를 쓰는데, 세그먼트 분리를 shlex 가 이미 해줬으므로 토큰에 남은 구분자 문자는
# 그 lookahead 를 막기만 한다 — `docker compose --env-file "a;b.env" down -v` 가
# 그렇게 통과했다 (F2-CLASS-RULES-REGEX). 매칭용 텍스트에서만 공백으로 중화한다.
_SEP_TRANS = str.maketrans({c: " " for c in ";&|\n"})


def _segment_texts(cmd: str) -> list[str]:
    """RULES 정규식을 돌릴 텍스트를 **세그먼트별로** 만든다. 파싱 불가면 명령 하나로
    보되, 성공 경로와 **같은** 구분자 중화(_SEP_TRANS)를 raw 텍스트에 적용한다.

    중화를 빼먹으면 파싱 불가가 곧 우회 통로가 된다: `lex.commenters = ""` 때문에
    `#` 는 주석이 아니라서 끝에 `#'` 를 붙이면 따옴표가 안 닫힌 꼴 → ValueError →
    여기로 온다. 그 raw 텍스트엔 따옴표 안의 `;` 가 살아있어 각 규칙의 `[^|;&\\n]*`
    lookahead 를 막고 → 매칭 실패 → **통과**했다. `docker compose --env-file
    "a;b.env" down -v #'` 로 볼륨 삭제가 통과한 게 이 경로다 (파괴적 규칙 9종이
    네 글자로 되살아났다). "파싱 불가 = shell 도 못 돌릴 명령" 이라는 예전 근거는
    거짓이다 — bash 는 `#'` 를 주석으로 떼고 멀쩡히 실행한다.

    중화 방향은 fail-safe 다: 매칭되면 차단하는 규칙들에서 구분자가 가려지면
    **통과**(위험), 공백으로 합쳐지면 **차단**(안전). 세그먼트가 과하게 합쳐지는
    부작용은 파싱 불가 명령이라는 작은 표면에만 갇힌다. 분기 자체를 fail-closed 로
    뒤집진 않는다 — `echo it's fine` 같은 정상 명령도 여기 오기 때문."""
    segs = _shell_segments(cmd)
    if segs is None:
        return [cmd.translate(_SEP_TRANS)]
    return [
        " ".join(t.translate(_SEP_TRANS) for t in toks)
        for toks in segs if toks
    ]


def _rm_is_blockable(cmd: str) -> bool:
    """cmd 안에 차단 대상 rm -rf 가 하나라도 있으면 True. 명령을 shell 세그먼트로
    쪼개 각 세그먼트의 rm -rf 히트를 독립 판정 — 그 세그먼트의 타겟(비-플래그
    인자)이 전부 /tmp·$TMPDIR 하위일 때만 통과, 하나라도 비-/tmp 타겟이거나
    타겟 파싱 실패면 차단(보수적).

    rm 여부·플래그·타겟은 전부 **토큰**으로 판정한다. 세그먼트를 다시 문자열로
    이어붙여(raw/shlex.join) 정규식을 돌리면 따옴표 안의 `;`·`|`·`&` 가 그대로
    되살아나 lookahead 의 [^\\n|;&]* 를 막는다 — `rm "a;b" -rf src/` 가 그렇게
    빠져나갔다 (F2-CLASS-RM)."""
    if not _RM_TOKEN_RE.search(cmd):
        return False  # rm 토큰 없음 — 파싱 불필요
    segs = _shell_segments(cmd)
    if segs is None:
        return True  # rm 토큰 + 파싱 불가 → 차단(보수적)
    for toks in segs:
        ri = next((i for i, t in enumerate(toks)
                   if t == "rm" or t.endswith("/rm")), -1)
        if ri < 0:
            # rm 이 독립 토큰이 아님 — `sh -c "rm -rf src/"` 처럼 감싸인 형태만
            # 보수적으로 차단 (여긴 따옴표가 이미 벗겨진 토큰 내부라 raw 검사가 맞다).
            # 문자열을 실행하는 명령일 때만 — 아니면 "rm -rf" 를 **데이터**로 넘기는
            # `grep -rn "rm -rf" docs/` 까지 걸린다 (_EXEC_WRAPPERS 주석).
            if _has_exec_wrapper(toks) and any(_RM_RULE_RE.search(t) for t in toks):
                return True
            continue
        args = toks[ri + 1:]
        flags = [t for t in args if t.startswith("-")]
        if not (any(_REC_RE.match(f) for f in flags)
                and any(_FRC_RE.match(f) for f in flags)):
            continue  # rm 이지만 -rf 아님 (`rm file.txt`, `npm rm pkg`)
        targets = [t for t in args if not t.startswith("-")]
        if targets and all(_is_tmp_target(t) for t in targets):
            continue  # 타겟 전부 /tmp 하위 → 안전
        return True   # 비-/tmp 타겟 또는 타겟 없음 → 차단
    return False


_DOCKER_TOK = ("docker", "docker-compose")


def _docker_hits(cmd: str) -> list[str]:
    """RULES §13 docker 검사 — shlex 토큰 분석 (regex 우회 방지: `-f x.yml`,
    `--env-file .env` 등 flag 가 compose 와 verb 사이에 끼어도 잡는다).
      build / compose build           → 차단 (app 이미지 빌드)
      up + `--build`                  → 차단
      up + 서비스 미지정(bare/-d)     → 차단 (전 서비스 = app 컨테이너)
      up + 서비스 명시(--build 없음)  → compose 판정: build: 있으면 app→차단,
                                        image 전용이면 의존 서비스→통과 (예외 ②)
    세그먼트 분리는 rm 과 같은 _shell_segments 를 쓴다. 예전의 raw
    `re.split(r"[\\n;&|]+", cmd)` 는 따옴표를 몰라서 `docker compose -f "a;b.yml"
    build` 가 `docker compose -f "a` / `b.yml" build` 로 찢겼고, 앞 조각엔
    서브커맨드가·뒤 조각엔 docker 토큰이 없어 둘 다 무시됐다 (F2-CLASS-DOCKER)."""
    out: list[str] = []
    base = ("개발은 dev 서버(./dev.sh up), compose 는 'docker화 해' 시만 (RULES §13)")
    segs = _shell_segments(cmd)
    if segs is None:
        # 파싱 불가(따옴표 안 닫힘 등) — docker 는 fs 와 달리 fail-closed 대상이
        # 아니라서(파괴적 명령이 아니라 정책 위반) 차단으로 뒤집지 않고 보수적으로
        # 훑는다. 단, 예전처럼 `re.split(r"[\n;&|]+", cmd)` 로 쪼개지 **않는다** —
        # 그 분할은 따옴표를 몰라서, 파싱을 일부러 깨뜨리면(따옴표 안 닫기) 지운 줄
        # 알았던 구분자-우회가 그대로 되살아났다. 통째 1세그먼트로 보면 구분자로
        # 숨길 수 없고, 과하게 잡더라도 파싱 불가 = shell 도 못 돌릴 명령이다.
        segs = [cmd.split()]
    for toks in segs:
        if not toks:
            continue
        di = next((i for i, t in enumerate(toks)
                   if t in _DOCKER_TOK or t.endswith("/docker") or t.endswith("/docker-compose")), -1)
        if di < 0:
            continue
        rest = toks[di + 1:]
        if rest and rest[0] == "compose":
            rest = rest[1:]
        if not rest:
            continue
        if "build" in rest:
            out.append(f"docker build/compose build — {base}")
        elif "up" in rest:
            after = rest[rest.index("up") + 1:]
            services = [t for t in after if not t.startswith("-")]
            if "--build" in after:
                out.append(f"docker compose up --build — {base}")
            elif not services:
                out.append(f"docker compose up (전 서비스 = app 컨테이너) — {base}")
            else:
                # 서비스 명시 → compose 파싱으로 app vs 이미지-전용 판정.
                # app(build:) 서비스가 하나라도 있으면 차단 (예외 ②는 의존 서비스만).
                svc_defs = _load_compose_services(rest)
                app_svcs = [s for s in services if _service_is_app(s, svc_defs)]
                if app_svcs:
                    out.append(
                        f"docker compose up {' '.join(app_svcs)} "
                        f"(app 서비스 = 개발은 dev 서버) — {base}"
                    )
                # 전부 이미지-전용 의존 서비스면 예외 ② 통과
    return out


def _docker_downv_blocked(cmd: str, _depth: int = 0) -> bool:
    """docker compose down -v/--volumes (볼륨 삭제, §2) 를 명령 위치 토큰으로 판정.
    정규식 substring 대신 shlex 세그먼트로 docker 가 명령 위치인지 본다 —
    printf/echo/harness send/grep 의 인용 데이터 속 "docker compose down -v" 는 docker 가
    명령 위치가 아니라(di<0) 통과, 실제 down -v 만 차단 (2026-07-18 keypoint 오탐 리포트).
    rm 과 동일하게 exec wrapper(sh -c "…") 도 재귀 재검사."""
    segs = _shell_segments(cmd)
    if segs is None:
        segs = [cmd.split()]
    for toks in segs:
        if not toks:
            continue
        di = next((i for i, t in enumerate(toks)
                   if t in _DOCKER_TOK or t.endswith("/docker") or t.endswith("/docker-compose")), -1)
        if di < 0:
            # exec wrapper (sh -c "docker compose down -v") 재검사 — rm 과 대칭.
            if _depth < 3 and _has_exec_wrapper(toks):
                for t in toks:
                    if "docker" in t and (" " in t or ";" in t or "\n" in t):
                        if _docker_downv_blocked(t, _depth + 1):
                            return True
            continue
        rest = toks[di + 1:]
        if rest and rest[0] == "compose":
            rest = rest[1:]
        if "down" in rest and ("-v" in rest or "--volumes" in rest):
            return True
    return False


# ── §4 포트 가드 (2026-08-04 사고: 8013 목업 점유 + 5185→5186 vite 드리프트) ──
# 에이전트 Bash 명령이 §4 할당 포트(각 프로젝트 .env 진실원천)에 서버를 바인딩
# 하려는 걸 결정론 차단한다:
#   ① 임시 서버(`python -m http.server`)는 **자기 FRONTEND_PORT 만 허용**
#      (시안/목업 게이트 정본 — 사용자 접속 경로가 최종 제품과 동일, RULES §4.1
#      2026-08-04 사용자 결정). 자기 BACKEND_PORT 포함 그 외 할당 포트는 차단.
#   ② bind 서버(uvicorn/vite/npm dev …)의 `--port N`·docker `-p N:` 이
#      **타 프로젝트** 할당 포트 → 차단 (자기 포트는 통과 — 정상 dev 기동)
# `--port` 는 psql 등 "접속" 클라이언트에도 쓰이므로 bind-서버 토큰이 같은
# 세그먼트에 있을 때만 본다 (접속은 §4 위반이 아님 — 오탐 방지).
# 공유 인프라 포트(5432/5435 등)는 전 프로젝트 공용이라 제외.
_PORT_SHARED = {5432, 5435}
_PORT_BIND_CMD_RE = re.compile(
    r"\b(uvicorn|vite|gunicorn|flask|streamlit|http\.server|npm|pnpm|yarn|serve|next)\b")
_PORT_TEMP_SERVER_RE = re.compile(r"\bhttp\.server\b")
# 주의: `--port` 앞에 \b 를 쓰면 안 된다 — 공백→`-` 는 둘 다 non-word 라
# \b 가 성립하지 않아 패턴이 영원히 안 맞는다 (2026-08-04 구현 중 실측).
_PORT_ARG_RES = [
    re.compile(r"\bhttp\.server\s+(?:--?[\w-]+(?:[=\s]\S+)?\s+)*(\d{2,5})\b"),
    re.compile(r"(?:^|\s)--port[=\s]+(\d{2,5})\b"),
    re.compile(r"(?:^|\s)-p\s+(\d{2,5}):"),
    re.compile(r"(?:^|\s)--publish[=\s]+(\d{2,5}):"),
]


def _port_harness_root() -> str:
    return os.environ.get("HARNESS_ROOT") or os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))


def _port_allocated() -> dict[int, str]:
    """port → project slug, 각 프로젝트 .env 의 *_PORT=<n> 스캔 (진실원천)."""
    out: dict[int, str] = {}
    root = _port_harness_root()
    for parent in ("modules", "claude-project"):
        base = os.path.join(root, parent)
        try:
            names = os.listdir(base)
        except OSError:
            continue
        for name in names:
            env = os.path.join(base, name, ".env")
            try:
                with open(env, encoding="utf-8", errors="replace") as f:
                    for line in f:
                        m = re.match(r"([A-Z_]*PORT[A-Z_]*)=(\d{2,5})\s*$", line.strip())
                        if m and m.group(1) != "PORT_OFFSET":
                            p = int(m.group(2))
                            if p not in _PORT_SHARED:
                                out.setdefault(p, name)
            except OSError:
                continue
    return out


def _port_own_project() -> str | None:
    d = os.environ.get("HARNESS_CTO_DIR")
    if d:
        return os.path.basename(d.rstrip("/"))
    role = os.environ.get("HARNESS_ROLE", "")
    if ":" in role:
        return role.split(":", 1)[1]
    return None


def _port_own_frontend() -> int | None:
    """자기 프로젝트 .env 의 FRONTEND_PORT — 목업 프리뷰가 허용되는 유일한 포트."""
    d = os.environ.get("HARNESS_CTO_DIR")
    if not d:
        own = _port_own_project()
        if not own:
            return None
        root = _port_harness_root()
        for parent in ("modules", "claude-project"):
            cand = os.path.join(root, parent, own)
            if os.path.isdir(cand):
                d = cand
                break
        else:
            return None
    try:
        with open(os.path.join(d, ".env"), encoding="utf-8", errors="replace") as f:
            for line in f:
                m = re.match(r"FRONTEND_PORT=(\d{2,5})\s*$", line.strip())
                if m:
                    return int(m.group(1))
    except OSError:
        pass
    return None


def _port_hits(seg_texts: list[str]) -> list[str]:
    try:
        alloc = _port_allocated()
    except Exception:
        return []  # 스캔 실패 = fail-open (판정 불가 시 작업을 막지 않는다)
    if not alloc:
        return []
    own = _port_own_project()
    own_frontend = _port_own_frontend()
    out: list[str] = []
    for t in seg_texts:
        is_temp = bool(_PORT_TEMP_SERVER_RE.search(t))
        is_bind = bool(_PORT_BIND_CMD_RE.search(t)) or "-p " in t or "--publish" in t
        if not (is_temp or is_bind):
            continue
        for pat in _PORT_ARG_RES:
            for m in pat.finditer(t):
                p = int(m.group(1))
                owner = alloc.get(p)
                if owner is None:
                    continue
                if is_temp and p != own_frontend:
                    out.append(
                        f"임시 서버가 §4 할당 포트 {p}({owner}) 바인딩 — 목업/프리뷰는 "
                        f"자기 FRONTEND_PORT 로만 (RULES §4.1)")
                elif not is_temp and owner != own:
                    out.append(
                        f"타 프로젝트({owner}) 할당 포트 {p} 바인딩 — 자기 .env 포트만 "
                        f"사용 (RULES §4)")
    return out


def _note(msg: str) -> None:
    """가드가 판정을 못 하고 통과시킨 사실만 stderr 에 남긴다 (exit code 불변).

    fail-open 은 설계다 (가드 버그가 작업을 막으면 안 된다). 문제는 그게
    **조용해서** 가드가 죽어도 아무도 모른다는 것 — 권한우회 모드에선 이게
    유일한 브레이크다. 로그 자체가 터져도 훅을 깨면 안 되니 이중 try.
    """
    try:
        sys.stderr.write(f"[git_guard] fail-open: {msg} — 가드가 이 명령을 검사하지 못했다.\n")
    except Exception:
        pass


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        _note("stdin JSON 파싱 실패")
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

    # RULES/DELETE/restore 는 raw 명령이 아니라 **세그먼트 텍스트**에 돌린다.
    # raw 로 돌리면 따옴표 안의 `;` 가 각 규칙의 `[^|;&\n]*` 를 막아 우회됐다
    # (F2-CLASS-RULES-REGEX — `docker compose --env-file "a;b.env" down -v`).
    seg_texts = _segment_texts(cmd)

    hits = []
    for cat, pat, reason in RULES:
        if reason == "rm -rf":
            continue  # rm -rf 는 아래 _rm_is_blockable 로 세그먼트/타겟별 판정
        if any(re.search(pat, t, re.IGNORECASE) for t in seg_texts):
            if cat in overrides:
                continue  # 사용자 허가 마커 — 통과 (감사 가능)
            hits.append((cat, reason))
    # rm -rf — /tmp 정리 예외를 명령 전체가 아니라 세그먼트/타겟별로 판정 (F2)
    if "fs" not in overrides and _rm_is_blockable(cmd):
        hits.append(("fs", "rm -rf"))
    # docker compose down -v (볼륨 삭제) — 토큰화로 인용 데이터 제외 (regex 오탐 대체).
    if "fs" not in overrides and _docker_downv_blocked(cmd):
        hits.append(("fs", "docker compose down -v (볼륨 삭제)"))
    if any(DB_DELETE_RE.search(t) for t in seg_texts) and "db" not in overrides:
        hits.append(("db", "DELETE FROM (WHERE 없음)"))
    for m in (m for t in seg_texts for m in GIT_RESTORE_RE.finditer(t)):
        tail = m.group("tail")
        staged = re.search(r"(?:^|\s)(?:--staged|-S)\b", tail)
        worktree = re.search(r"(?:^|\s)(?:--worktree|-W)\b", tail)
        if staged and not worktree:
            continue  # unstage-only — 안전
        if "git" not in overrides:
            hits.append(("git", "git restore (worktree 복원 — 작업본 파괴)"))
        break
    if "docker" not in overrides:
        for reason in _docker_hits(cmd):
            hits.append(("docker", reason))
    if "port" not in overrides:
        for reason in _port_hits(seg_texts):
            hits.append(("port", reason))
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
    except Exception as exc:  # 가드 자체 버그는 fail-open — 단 조용히는 아니다
        _note(f"내부 오류 {type(exc).__name__}: {exc}")
        sys.exit(0)
