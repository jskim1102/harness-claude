"""Shared helpers for the agent-team enforcement hooks.

Imported by task_created_format_check.py, task_completed_verify_gate.py and
teammate_idle_workcheck.py. Responsibilities:
  - parse the stdin JSON payload the harness delivers to a hook,
  - append an audit record to ~/.claude/logs/team-hooks.jsonl for every decision,
  - implement the documented exit-code contract: 0 = proceed, 2 = block + the
    stderr text is fed back as the reason.

Design rule for ALL hooks: FAIL OPEN. Any unexpected condition must resolve to
allow() — a hook bug must never be able to roll back a task, prevent a valid
completion, or trap a teammate. Enforcement is a guardrail, not a tripwire.

Adapted from aws-samples/sample-claude-code-agent-team for harness-claude.
Role tags adapted to our team: plan, design, dev, review.
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

HOME = os.path.expanduser("~")
LOG_DIR = os.path.join(HOME, ".claude", "logs")
LOG_PATH = os.path.join(LOG_DIR, "team-hooks.jsonl")
TASKS_DIR = os.path.join(HOME, ".claude", "tasks")     # ~/.claude/tasks/<team>/<id>.json
VERIFIED_DIR = os.path.join(LOG_DIR, "verified")        # completion sentinels
NUDGE_DIR = os.path.join(LOG_DIR, "idle-nudges")        # idle loop-guard state

# Workflow role tags: Claude teammates 2명([plan]/[review]) + 독립 designer-cto
# 세션([design]) + external Codex-owned [dev]. 태그 4종은 tasks.md 표기 규약이라
# 팀 구성 변화(2026-07-29 designer 분리)와 무관하게 유지된다.
# A task subject/description must contain [role] where role is one of these.
ROLES = ("plan", "design", "dev", "review")


def read_payload():
    """Read and parse the hook stdin payload. Returns {} on empty/invalid."""
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def audit(event, payload, decision, reason=None, extra=None):
    rec = {"captured_at": _now(), "event": event, "decision": decision}
    if reason:
        rec["reason"] = reason
    if extra:
        rec.update(extra)
    rec["payload"] = payload
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception as exc:
        # logging must never break a hook — but it must not vanish either.
        # The gates' fail-open handlers log ONLY through here, so an unwritable
        # LOG_DIR used to erase every gate decision with zero trace. stderr is a
        # separate stream from the hooks' stdout protocol and does not affect
        # exit codes. Wrapped again so a closed stderr still cannot break us.
        try:
            print(f"[team-hook] audit write failed ({type(exc).__name__}: {exc}) "
                  f"— {event}/{decision} not recorded in {LOG_PATH}", file=sys.stderr)
        except Exception:
            pass


def allow(event=None, payload=None, reason=None, extra=None):
    """Permit the action (exit 0). Audits if an event is given."""
    if event is not None:
        audit(event, payload, "allow", reason, extra)
    sys.exit(0)


def block(event, payload, reason, extra=None):
    """Block the action (exit 2). stderr is fed back as the reason."""
    audit(event, payload, "block", reason, extra)
    print(reason, file=sys.stderr)
    sys.exit(2)


def repo_root():
    """이 훅 파일($REPO/hooks/team/*.py) 위치로 REPO 를 결정론 산출 (3단계 상위)."""
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def safe_key(s):
    """파일명으로 안전한 키. 경로 구분자·NUL·제어문자를 '_' 로 접는다."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(s))


def project_of(payload):
    """빌드 프로젝트 이름을 결정론 산출한다 — 증거 파일의 **정본 키**.

    왜 팀 이름이 아니라 프로젝트인가 (2026-07-27):
      증거 파일(완료 sentinel, code-review 마커)이 `team_name` 으로 키잉돼 있었는데
      그 값은 세션 파생(`session-<8hex>`)이라 **세션을 재시작할 때마다 바뀐다**.
      결과: `~/.claude/logs/verified/` 에 소비되지 않은 고아 sentinel 330개
      (전체의 52%), 그중 205개가 이름 없는 `_noteam` 통. 프로젝트 dir 이름은
      세션 수명과 무관하게 안정적이므로 이걸 키로 쓴다.

    해석 순서 (앞이 이길수록 신뢰도 높음):
      1. payload cwd 가 <repo>/{claude-project,modules}/<name> 아래
      2. transcript_path 의 인코딩된 프로젝트 경로를 실 빌드 dir 목록과 매칭
         (lead·teammate 모두 같은 프로젝트 dir 아래 transcript 를 두므로
          env/cwd 전파에 의존하지 않고 식별된다)
      3. HARNESS_ROLE=cto:<name>
      4. payload team_name (레거시 호환)
      5. "_noteam"
    """
    repo = repo_root()
    bases = ("claude-project", "modules")
    payload = payload if isinstance(payload, dict) else {}

    # 1) cwd
    cwd = str(payload.get("cwd", "") or "")
    if cwd:
        for base in bases:
            root = os.path.join(repo, base) + os.sep
            if cwd == os.path.join(repo, base):
                break
            if cwd.startswith(root):
                name = cwd[len(root):].split(os.sep)[0]
                if name:
                    return safe_key(name)

    # 2) transcript_path 역산 (인코딩 = 절대경로의 '/'·'_' → '-')
    m = re.search(r"/projects/([^/]+)/", str(payload.get("transcript_path", "") or ""))
    if m:
        encoded = m.group(1)
        for base in bases:
            d = os.path.join(repo, base)
            try:
                names = os.listdir(d)
            except OSError:
                continue
            for name in names:
                full = os.path.join(d, name)
                if os.path.isdir(full) and full.replace("/", "-").replace("_", "-") == encoded:
                    return safe_key(name)

    # 3) HARNESS_ROLE
    role = os.environ.get("HARNESS_ROLE", "")
    if ":" in role:
        return safe_key(role.split(":", 1)[1])

    # 4) legacy team_name → 5) fallback
    team = payload.get("team_name")
    return safe_key(team) if team else "_noteam"


REGRESSION_DIR = os.path.join(HOME, ".harness-claude", "regression")


def regression_missing(proj):
    """`[review]` 를 닫기 전 회귀 검사가 실제로 통과했는지 (PROCESS §3 5.4).

    `./run.sh regress <proj> --baseline` (리뷰 착수) → `--check` (수정 반영 후).
    훅은 **결과 파일만 읽는다** — 모델이 쓴 `Run:` 텍스트를 훅이 셸에 넘기지
    않는다(RULES §6 취지 유지).

    반환: 차단 사유 리스트 (빈 리스트 = 통과).
    FAIL OPEN 예외 하나: `regressions > 0` 은 오류가 아니라 **결과**이므로 차단한다.

    두 소비처가 공유한다 — TaskCompleted 게이트(작업목록을 쓰는 빌드)와
    tasks.md 편집 게이트(작업목록을 안 쓰는 빌드). 구현이 갈리면 한쪽만 조여진다.
    """
    proj = safe_key(proj)
    base_p = os.path.join(REGRESSION_DIR, proj, "baseline.json")
    chk_p = os.path.join(REGRESSION_DIR, proj, "last-check.json")
    how = ("회귀 검사를 돌려라: `./run.sh regress {0} --baseline` (리뷰 착수) → "
           "수정 반영 후 `./run.sh regress {0} --check`".format(proj))

    if not os.path.exists(base_p):
        return ["회귀 기준선 없음 ({}) — {}".format(base_p, how)]
    if not os.path.exists(chk_p):
        return ["회귀 재검사 결과 없음 ({}) — {}".format(chk_p, how)]
    if os.path.getmtime(chk_p) <= os.path.getmtime(base_p):
        return ["회귀 재검사가 기준선보다 오래됨 — 수정 반영 후 `--check` 를 다시 돌려라"]
    try:
        with open(chk_p) as fh:
            n = int(json.load(fh).get("regressions", -1))
    except Exception:
        return ["회귀 결과 파일을 읽을 수 없음 ({}) — {}".format(chk_p, how)]
    if n < 0:
        return ["회귀 결과에 regressions 필드 없음 — {}".format(how)]
    if n > 0:
        return ["회귀 {}건 — 이전에 통과하던 `Run:` 이 지금 실패한다. "
                "다른 어떤 finding 보다 우선하는 BLOCKER (PROCESS §3 5.4). "
                "`./run.sh regress {} --check` 출력 참조".format(n, proj)]
    return []


CODEREVIEW_DIR = os.path.join(LOG_DIR, "codereview")


def codereview_paths(proj):
    """code-review 호출 마커(.invoked)와 직전 [review] 완료 마커(.lastreview).

    키는 **프로젝트 + reviewer** 다. 예전엔 프로젝트만이라 CTO·planner·designer 가
    code-review 를 돌려도 reviewer 의 완료게이트가 열렸다.

    안전 근거 (2026-07-27, `~/.harness-claude/skill-activity.log` 전수):
    실 프로젝트의 code-review/qa 호출 47건 중 **42건이 `agent=reviewer` 로 정확히
    식별**됐고(6개 프로젝트 전부), `agent=cto` 는 5건뿐이었다 — 그 5건이 바로 이
    게이트가 막아야 할 구멍이다. 즉 `_extract_agent` 는 실제 팀원을 안정적으로
    잡으며, 조여도 정상 리뷰가 막히지 않는다.

    reviewer 가 가동 불가라 CTO 가 직접 검증하는 경우는 **차단이 맞다** — 그때의
    합법 출구는 사용자 명시 waive 파일뿐이다 (PROCESS §3 step5).
    """
    return (os.path.join(CODEREVIEW_DIR, "{}.reviewer.invoked".format(safe_key(proj))),
            os.path.join(CODEREVIEW_DIR, safe_key(proj) + ".lastreview"))


def codereview_missing(proj):
    """`[review]` 를 닫기 전 reviewer 가 code-review/qa 를 실제로 호출했는지.

    반환: 차단 사유 리스트 (빈 리스트 = 통과) — `regression_missing` 과 같은 계약.

    ★ 두 소비처가 공유한다 — TaskCompleted 게이트(작업목록을 쓰는 빌드)와 tasks.md
    편집 게이트(작업목록을 안 쓰는 빌드). 회귀 판정은 처음부터 공유했지만 이
    호출-증거 판정은 TaskCompleted 쪽에만 있었고, 그래서 tasks.md 경로로만 흐르는
    빌드는 reviewer 를 한 번도 dispatch 하지 않고 `[review]` 를 닫을 수 있었다
    (실측: rtsp-keypoint phase4 — 체크박스가 코드 착지 후 사후에 찍혔고 ckpt2
    뮤테이션 검증·ckpt4 실카메라 검증이 미수행으로 남았다). 구현이 갈리면 한쪽만
    조여진다는 원칙을 여기서도 적용한다.
    """
    inv_p, last_p = codereview_paths(proj)
    inv_m = os.path.getmtime(inv_p) if os.path.exists(inv_p) else -1.0
    last_m = os.path.getmtime(last_p) if os.path.exists(last_p) else 0.0
    if inv_m <= last_m:
        return [
            "**reviewer 의** code-review/qa 스킬 호출 증거 없음 (직전 리뷰 이후). "
            "합법 출구는 둘뿐: (a) reviewer teammate 가 직접 `code-review`(또는 "
            "qa-only)를 실행한다 — CTO·planner·designer 가 대신 돌린 것은 이제 "
            "인정되지 않는다; (b) 사용자가 이 segment 를 명시 waive 해 CTO 가 "
            "waiver 파일을 만든다 (PROCESS §3 step5). 파일 읽기·diff 등 수동 "
            "static 검증만으론 불가"
        ]
    return []


def role_of_teammate(name):
    """Map an actor name to its task role tag.

    Claude uses planner/designer/reviewer. The developer mapping remains for
    external Codex task ownership and compatibility with existing task data.
    """
    if not name:
        return None
    n = name.lower()
    mapping = {
        "planner": "plan",
        "designer": "design",
        "developer": "dev",
        "reviewer": "review",
    }
    if n in mapping:
        return mapping[n]
    # Also accept role tags directly (e.g. teammate named "plan-agent")
    for role in ROLES:
        if n == role or n.startswith(role + "-") or n.startswith(role + "_"):
            return role
    return None


def load_team_tasks(team_name):
    """Load every <id>.json in ~/.claude/tasks/<team_name>/ as {id: task_dict}."""
    tasks = {}
    if not team_name:
        return tasks
    d = os.path.join(TASKS_DIR, team_name)
    try:
        names = os.listdir(d)
    except Exception:
        return tasks
    for fn in names:
        if not fn.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, fn)) as fh:
                t = json.load(fh)
            tasks[str(t.get("id", fn[:-5]))] = t
        except Exception:
            continue
    return tasks


# ---- 사용자 승인 판정 (start_project_gate · plan_readonly_gate 공유) ----
# 두 게이트가 같은 장치를 쓴다: 사용자 프롬프트(모델이 못 꾸밈)가 **직전 CTO
# 메시지의 질문**에 대한 짧은 긍정일 때만 승인. 구현이 갈리면 한쪽만 조여진다.
NO_RE = re.compile(r"아니|ㄴㄴ|싫|말고|하지\s*마|취소|\b(no|nope|stop)\b", re.I)
# 첫 단어 정확 일치만 본다 — 접두 매칭은 "어디까지 했어?"·"해당 부분…" 을 승인으로 오인한다.
YES_WORDS = {"응", "응응", "ㅇ", "ㅇㅇ", "ㅇㅇㅇ", "웅", "어", "네", "네네", "넵", "넵넵", "넹",
             "예", "yes", "y", "yep", "yeah", "sure", "ok", "okay", "오케이", "ㅇㅋ",
             "좋아", "좋아요", "그래", "그래요", "해", "해줘", "해줘요", "해주세요", "해라",
             "ㄱ", "ㄱㄱ", "고", "go", "진행", "진행해", "진행해줘", "진행해주세요", "진행하자",
             "스폰", "스폰해", "스폰해줘", "스폰해주세요", "알았어", "알겠어", "부탁해", "부탁해요"}
# 질문 전용 동사(확정*/수정*)는 여기 넣지 않는다 — plan_readonly_gate._answer_ok 가 질문별로
# 판정한다. 공유 집합에 넣으면 "reviewer 스폰할까요?" 에 "수정해" 가 스폰 승인으로 샌다.


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
