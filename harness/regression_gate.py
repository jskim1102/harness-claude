#!/usr/bin/env python3
"""harness regression gate — 이전에 통과하던 `Run:` 이 지금도 통과하는지 확인.

왜 필요한가 (2026-07-27):
  reviewer 는 segment 끝에 호출되지만, 실제로 재실행하는 건 그 `[review]` task 의
  `Run:` **한 개**뿐이다. 같은 ckpt 의 형제 task 들, 그리고 앞선 segment 들에서
  통과했던 `Run:` 들(rescue-pose 기준 40개 중 39개)은 **아무도 다시 안 돌린다.**
  그래서 "리뷰 지적대로 고쳤더니 원래 되던 게 깨졌다" 가 구조적으로 감지되지
  않았다 (2026-07 cam-distance `enabled` · rtsp-detection fix9 사고).

무엇을 하나:
  `specs/tasks.md` 에서 **완료(`[✅]`)된 task 의 `Run:`** 를 모아 재실행하고,
  기준선 대비 **통과 → 실패** 로 바뀐 것만 회귀로 보고한다. 기준선에서 이미
  실패였던 건 회귀가 아니다(원래 깨져 있음).

두 모드:
  --baseline  전부 실행 → 기준선 저장. 리뷰 착수 시 1회.
  --check     다시 실행 → 기준선과 비교. 수정 반영 후 1회. 회귀>0 이면 exit 1.

제외 규칙 (순서대로, 제외 사유는 리포트에 전부 나열 — 조용한 누락 금지):
  1. 미완(`[ ]`/`[❓]`) task            → 통과한 적 없으니 기준선이 아니다
  2. `--segment` 범위 안의 ckpt          → 방금 만든 것이라 기준선이 아니다
  3. phase1(환경설정) ckpt               → 1회성 셋업. 재실행 위험이 여기 몰려 있다
  4. 재실행 위험 명령                    → venv 재생성·npm install·docker up·
                                            alembic·dev.sh up·상태변경 curl·
                                            스크래치(/tmp) --outDir 가 아닌 프런트 빌드(dist 덮어씀)
  5. 중복 명령                           → 실측 30~50% 가 중복

안전 경계 (정직하게):
  이 도구는 tasks.md 의 모델 작성 텍스트를 셸로 실행한다. `hooks/git_guard.py` 는
  PreToolUse(Bash) 훅이라 여기서 파생된 자식 프로세스는 보지 못한다. 그래서
  DESTRUCTIVE_RE 로 명백한 파괴 명령을 **실행 전에 거부**한다. 이는 git_guard 와
  같은 성격의 **anti-합리화 장치이지 샌드박스가 아니다** — 리뷰어가 이미 자기
  Bash 로 같은 명령을 돌릴 수 있는 것과 같은 신뢰 도메인이다.
  또 하나: 선정된 Run: 에 pytest 가 있으면 시작 전에 **같은 빌드 dir 안에서 도는 다른
  pytest** 를 찾아 exit 2 로 거부한다 — 게이트는 내부에서 pytest 를 돌리므로 공유
  테스트 DB 를 쓰는 스위트와 겹치면 무관한 테스트가 허위 실패한다 (annodock
  2026-10-06: 허위 회귀 8건 중 7건이 이 원인). 판정은 /proc 의 argv 로 한다(argv[0]
  이 pytest 이거나 `-m pytest`) — 명령 문자열에 pytest 가 들어간 셸 래퍼와 게이트의
  조상 프로세스는 세지 않는다 (Codex 리뷰 2026-10-08 P1: 게이트를 기다리는 부모 셸이
  걸리면 영원히 exit 2). 우회 플래그는 없다 — 기다렸다 돌려라. 한계: 시작 시점 1회
  검사라 실행 도중 뒤늦게 시작되는 pytest 는 못 막는다(공유 락은 별건).

usage:
  regression_gate.py <build-name> --baseline [--segment A~B] [--timeout N] [--json]
  regression_gate.py <build-name> --check    [--segment A~B] [--timeout N] [--json]

exit: 0 정상 / 1 회귀 검출 / 2 사용법·기준선 부재 등 진행 불가
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASES = ("claude-project", "modules")
STATE_ROOT = Path.home() / ".harness-claude" / "regression"

# --- tasks.md 파싱 정본 (hooks/cto_statusline.py 와 동일 규약) --------------
# 완료 = [✅] (정본; 레거시 [x]/[X] 도 인식). 블로커 [❓]/[!], 미완 [ ].
BOX_RE = re.compile(r"^\s*[-*]\s*\[(✅| |x|X|❓|!)\]")
DONE_MARKS = ("x", "X", "✅")
# statusline 은 `phase\d+\.ckpt\d+` 만 보지만 실 빌드엔 `fix.ckpt1` 도 있다
# (rescue-pose). 재실행 대상 수집은 그것도 포함해야 하므로 더 넓게 잡는다.
CKPT_RE = re.compile(r"^###\s+([A-Za-z][A-Za-z0-9_-]*\.ckpt\d+)\s*(.*)$")
RUN_RE = re.compile(r"\bRun:\s*(.+?)\s*$")
ROLE_RE = re.compile(r"\[(dev|design|plan|review)\]")

# --- 프런트 빌드 판정 (RISKY 의 callable 항목) ------------------------------
# 설계 원칙 (Codex 리뷰 2026-10-08 1~3차 반영): 셸 문법을 흉내내 "정확히" 판정하려던 시도는 따옴표
# 이스케이프·$'…'·here-string·치환 같은 변형마다 구멍이 났다. 그래서 두 방향 모두 "더 제외하는
# 쪽"으로만 틀리게 만든다 — 이 파일의 정책(잘못 제외 = 커버리지 손실, 잘못 실행 = 환경 파괴)이다.
#   감지: 원문 그대로(따옴표·주석 해석 없음) 세그먼트(|;&)에 JS 빌드 도구 토큰과 독립 단어 `build` 가
#         같이 있으면 위험. bash -c '…npm run build…'·TAG="a;b" npm run build 같은 변형도 문자열이
#         남아있는 한 걸린다. printf '…npm run build…' 류의 과잉 제외는 감수한다.
#   면제: 세그먼트 전체가 정확히 `npm run build -- --outDir[= ]/tmp/<리터럴 경로>` 또는
#         `[npx] vite build --outDir[= ]/tmp/<리터럴 경로>` 일 때만. 환경변수 대입·리다이렉트·치환·
#         따옴표·`..`·다른 인자가 하나라도 붙으면 면제가 아니다 (화이트리스트 문법). 구분자 `--` 의
#         의미가 도구마다 달라서 이 둘만 허용한다 (Codex 리뷰 4·5차 P1): npm 은 `--` 가 없으면 옵션을
#         자기가 먹고 스크립트엔 안 넘겨 기본 dist 로 빌드되므로 `--` 필수. vite 는 `--` 뒤를 무시하므로
#         `--` 금지. pnpm 과 modern Yarn 은 `--` 자체를 스크립트에 넘겨 vite 가 옵션을 무시한다 —
#         버전별로 전달 규칙이 갈려 안전한 형태를 특정할 수 없으니 **면제 없음**(항상 위험).
#   한계: 빌드 뒤 `cp -r /tmp/x dist` 처럼 빌드가 아닌 명령으로 서빙 dir 를 덮어쓰는 건 못 잡는다 —
#         이 게이트는 휴리스틱 가드지 샌드박스가 아니다. 근본 해법은 prod 가 작업 트리를 직접 서빙하지
#         않는 것(annodock: Caddy 가 frontend/dist 를 직접 서빙, 2026-10-06 실측).
_JS_TOOL_RE = re.compile(r"\b(?:npm|pnpm|yarn|npx|vite|webpack|esbuild|rollup|parcel|next|astro)\b")
_BUILD_WORD_RE = re.compile(r"(?<![\w./])build(?![\w./])")
_SCRATCH_DIR = r"--outDir(?:=|\s+)(?:/tmp|/var/tmp)(?:/[A-Za-z0-9_-][A-Za-z0-9._-]*)+/?"
_SCRATCH_BUILD_RE = re.compile(
    r"^\s*(?:"
    + r"npm\s+run\s+build\s+--\s+" + _SCRATCH_DIR          # npm: `--` 필수 (pnpm/yarn 은 면제 없음)
    + r"|(?:npx\s+)?vite\s+build\s+" + _SCRATCH_DIR         # vite: `--` 금지
    + r")\s*$"
)


def _risky_frontend_build(cmd: str) -> bool:
    for seg in re.split(r"[|;&]+", cmd):
        if _JS_TOOL_RE.search(seg) and _BUILD_WORD_RE.search(seg) and not _SCRATCH_BUILD_RE.match(seg):
            return True
    return False


# --- 재실행하면 부작용이 남는 명령 (제외; 실행하지 않음) --------------------
# 보수적으로 잡는다 — 잘못 제외하면 커버리지만 줄지만, 잘못 실행하면 환경이 깨진다.
RISKY = (
    ("venv 재생성", re.compile(r"\bpython3?\s+-m\s+venv\b")),
    ("패키지 재설치", re.compile(r"\b(pip3?|uv\s+pip)\s+install\b|\bpoetry\s+install\b|\buv\s+sync\b")),
    ("npm 설치", re.compile(r"\bnpm\s+(install|ci|i)\b")),
    # --outDir 없는 빌드는 작업 트리의 dist/ 를 덮어쓴다. annodock 은 Caddy 가 frontend/dist 를
    # 직접 서빙하므로 게이트 실행 = 판정 전 prod 배포였다 (2026-10-06 17:26 실측). 판정 규칙은
    # _risky_frontend_build 참조 — /tmp 류 스크래치 --outDir 만 통과.
    ("프런트 빌드(dist 덮어씀)", _risky_frontend_build),
    ("docker build/up", re.compile(r"\bdocker(\s+compose|-compose)?\s+(up|build)\b")),
    ("docker pull", re.compile(r"\bdocker(\s+compose|-compose)?\s+pull\b")),
    ("DB 마이그레이션", re.compile(r"\balembic\s+(upgrade|downgrade|stamp)\b")),
    ("서버 기동/정지", re.compile(r"\bdev\.sh\s+(up|down)\b")),
    ("상태변경 HTTP", re.compile(r"\bcurl\b[^|;&]*?(-X\s*(POST|PUT|PATCH|DELETE)\b|--data\b|\s-d\s)")),
)

# --- 실행 자체를 거부하는 파괴 명령 (안전 경계) -----------------------------
DESTRUCTIVE = (
    ("rm -rf", re.compile(r"\brm\s+(-\w*\s+)*-\w*[rR]\w*f|\brm\s+(-\w*\s+)*-\w*f\w*[rR]")),
    ("git 되돌리기/발행", re.compile(r"\bgit\s+(reset|checkout|clean|rebase|push|commit|tag)\b")),
    ("docker 볼륨 삭제", re.compile(r"\bdocker\s+volume\s+(rm|prune)\b|\bdown\b[^|;&]*--volumes|\bdown\b[^|;&]*\s-v\b")),
    ("DB 파괴 DDL", re.compile(r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", re.I)),
    ("디스크 파괴", re.compile(r"\b(dd|mkfs\S*|wipefs)\b")),
    ("find -delete", re.compile(r"\bfind\b[^|;&]*-delete\b")),
)


class Task:
    __slots__ = ("ckpt", "role", "done", "cmd", "lineno")

    def __init__(self, ckpt, role, done, cmd, lineno):
        self.ckpt, self.role, self.done, self.cmd, self.lineno = ckpt, role, done, cmd, lineno


def parse_tasks(text: str) -> tuple[list[Task], list[str]]:
    """tasks.md 본문 → (Run: 를 가진 task 목록, 문서 순서의 ckpt id 목록). 순수 함수."""
    tasks: list[Task] = []
    order: list[str] = []
    ckpt = None
    for i, line in enumerate(text.splitlines(), 1):
        m = CKPT_RE.match(line)
        if m:
            ckpt = m.group(1)
            if ckpt not in order:
                order.append(ckpt)
            continue
        b = BOX_RE.match(line)
        if not b:
            continue
        r = RUN_RE.search(line)
        if not r:
            continue
        role_m = ROLE_RE.search(line)
        tasks.append(Task(
            ckpt=ckpt or "(ckpt 없음)",
            role=role_m.group(1) if role_m else "?",
            done=b.group(1) in DONE_MARKS,
            cmd=r.group(1).strip(),
            lineno=i,
        ))
    return tasks, order


def risky_reason(cmd: str) -> str | None:
    for name, rx in RISKY:
        if rx(cmd) if callable(rx) else rx.search(cmd):
            return name
    return None


def destructive_reason(cmd: str) -> str | None:
    for name, rx in DESTRUCTIVE:
        if rx.search(cmd):
            return name
    return None


def _proc_argv(pid: str) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]


_PYTEST_NAMES = ("pytest", "py.test")
_PY_INTERP_RE = re.compile(r"^(?:python|pypy)(?:\d+(?:\.\d+)?)?$")
_PY_OPTS_WITH_VALUE = ("-X", "-W", "--check-hash-based-pycs")


def _is_pytest_argv(argv: list[str]) -> bool:
    """실제 pytest 기동인가 — argv[0] 자체가 pytest 거나, 파이썬 인터프리터가 `-m pytest` 또는
    console script(`/…/bin/pytest`, 커널이 shebang 을 푼 모양)를 첫 피연산자로 받는 경우만.
    vim/cat 의 피연산자, `bash -c "…pytest…"` 문자열, uv/poetry/time 같은 래퍼는 세지 않는다
    (래퍼의 자식이 위 모양으로 잡힌다). Codex 리뷰 2026-10-08 2·3차."""
    if not argv:
        return False
    if Path(argv[0]).name in _PYTEST_NAMES:
        return True
    if not _PY_INTERP_RE.match(Path(argv[0]).name):
        return False
    skip = False
    for i, a in enumerate(argv[1:], 1):
        if skip:
            skip = False
            continue
        if a == "-m":
            return i + 1 < len(argv) and argv[i + 1] == "pytest"
        if a in _PY_OPTS_WITH_VALUE:
            skip = True
            continue
        if a.startswith("-"):
            continue
        return Path(a).name in _PYTEST_NAMES
    return False


def _ancestor_pids() -> set[int]:
    """자기 자신 + 조상 체인 (게이트를 기다리는 부모 셸을 충돌로 세지 않기 위해)."""
    pids: set[int] = set()
    pid = os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            pid = int(stat.rsplit(")", 1)[1].split()[1])   # `pid (comm) state ppid …`
        except (OSError, ValueError, IndexError):
            break
    return pids


def concurrent_pytest(bdir: Path) -> list[str]:
    """이 빌드 dir 안(cwd 기준)에서 도는 다른 pytest 프로세스. Linux /proc 전용 —
    /proc 이 없으면 검사 불가 → 빈 목록(현상 유지). 프로세스는 찾았는데 cwd 를 못 읽으면
    보수적으로 충돌로 본다."""
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    root = bdir.resolve()
    skip = _ancestor_pids()
    hits: list[str] = []
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) in skip:
            continue
        argv = _proc_argv(entry.name)
        if not _is_pytest_argv(argv):
            continue
        try:
            target = os.readlink(entry / "cwd")
            if target.endswith(" (deleted)"):      # 지워진 뒤 재생성된 빌드 dir — 같은 DB 일 수 있다
                inside = True
            else:
                cwd = Path(target).resolve()
                inside = cwd == root or root in cwd.parents
        except OSError:
            inside = True
        if inside:
            hits.append(f"pid {entry.name} · {' '.join(argv)[:88]}")
    return hits


def segment_ckpts(order: list[str], spec: str | None) -> set[str]:
    """`phase4.ckpt1~phase4.ckpt2` → 문서 순서상 그 사이의 ckpt 집합. 순수 함수."""
    if not spec:
        return set()
    parts = [p.strip() for p in re.split(r"[~-]{1,2}", spec) if p.strip()]
    if not parts:
        return set()
    lo = parts[0]
    hi = parts[-1] if len(parts) > 1 else parts[0]
    if lo not in order or hi not in order:
        return {p for p in parts if p in order}
    i, j = order.index(lo), order.index(hi)
    if i > j:
        i, j = j, i
    return set(order[i:j + 1])


def select(tasks: list[Task], order: list[str], segment: str | None):
    """실행 대상과 제외 목록을 가른다. 순수 함수 — smoke 로 단위 검증 가능."""
    seg = segment_ckpts(order, segment)
    selected: list[Task] = []
    excluded: list[tuple[Task, str]] = []
    seen: dict[str, Task] = {}
    for t in tasks:
        if not t.done:
            excluded.append((t, "미완 task"))
            continue
        if t.ckpt in seg:
            excluded.append((t, "이번 segment"))
            continue
        if t.ckpt.startswith("phase1."):
            excluded.append((t, "phase1 환경설정"))
            continue
        d = destructive_reason(t.cmd)
        if d:
            excluded.append((t, f"파괴 명령 거부: {d}"))
            continue
        r = risky_reason(t.cmd)
        if r:
            excluded.append((t, f"재실행 위험: {r}"))
            continue
        if t.cmd in seen:
            excluded.append((t, f"중복 ({seen[t.cmd].ckpt})"))
            continue
        seen[t.cmd] = t
        selected.append(t)
    return selected, excluded


def run_one(cmd: str, cwd: Path, timeout: int) -> dict:
    started = time.monotonic()
    try:
        p = subprocess.run(
            ["bash", "-c", cmd], cwd=str(cwd), timeout=timeout,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        out, code = p.stdout.decode("utf-8", "replace"), p.returncode
    except subprocess.TimeoutExpired:
        out, code = f"(timeout {timeout}s)", 124
    except Exception as exc:                       # noqa: BLE001 — 실행 실패도 결과다
        out, code = f"(실행 실패: {exc})", 125
    return {
        "cmd": cmd,
        "exit": code,
        "secs": round(time.monotonic() - started, 2),
        "tail": out[-4000:],
    }


def build_dir(name: str) -> Path | None:
    for base in BASES:
        d = REPO / base / name
        if (d / "specs" / "tasks.md").is_file():
            return d
    return None


def state_path(name: str, kind: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return STATE_ROOT / safe / f"{kind}.json"


def _write_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def _exclusion_summary(excluded) -> list[str]:
    agg: dict[str, int] = {}
    for _, why in excluded:
        agg[why] = agg.get(why, 0) + 1
    return [f"{why} ×{n}" for why, n in sorted(agg.items(), key=lambda kv: -kv[1])]


def main() -> int:
    ap = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n")[0])
    ap.add_argument("build", help="빌드 이름 (claude-project/<name> 또는 modules/<name>)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--baseline", action="store_true", help="전부 실행해 기준선 저장")
    mode.add_argument("--check", action="store_true", help="다시 실행해 기준선과 비교")
    ap.add_argument("--segment", help="이번 segment 범위 (예: phase4.ckpt1~phase4.ckpt2) — 제외 대상")
    ap.add_argument("--timeout", type=int, default=120, help="명령당 타임아웃 초 (기본 120)")
    ap.add_argument("--json", action="store_true", help="기계 판독 출력")
    args = ap.parse_args()

    bdir = build_dir(args.build)
    if bdir is None:
        print(f"error: 빌드를 찾을 수 없음 — {args.build} "
              f"(claude-project/ 또는 modules/ 아래 specs/tasks.md 필요)", file=sys.stderr)
        return 2

    tasks, order = parse_tasks((bdir / "specs" / "tasks.md").read_text(encoding="utf-8", errors="replace"))
    selected, excluded = select(tasks, order, args.segment)

    if not selected:
        print(f"== regression {'baseline' if args.baseline else 'check'}: {args.build} ==")
        print(f"  실행 대상 0개 (수집 {len(tasks)} · 제외 {len(excluded)})")
        for s in _exclusion_summary(excluded):
            print(f"    - {s}")
        if args.check:
            print("== REGRESSIONS: 0 ==")
        return 0

    if any("pytest" in t.cmd for t in selected):
        busy = concurrent_pytest(bdir)
        if busy:
            print("error: 같은 빌드 dir 에서 다른 pytest 가 실행 중 — 게이트는 내부에서 pytest 를 "
                  "돌리므로\n       공유 테스트 DB 가 겹쳐 무관한 테스트가 허위 실패한다. "
                  "끝나길 기다렸다가 다시 돌려라.", file=sys.stderr)
            for h in busy:
                print(f"       - {h}", file=sys.stderr)
            return 2

    base = None
    if args.check:
        bp = state_path(args.build, "baseline")
        if not bp.is_file():
            print(f"error: 기준선 없음 — 먼저 --baseline 을 돌려라 ({bp})", file=sys.stderr)
            return 2
        base = {r["cmd"]: r for r in json.loads(bp.read_text(encoding="utf-8"))["results"]}

    label = "baseline" if args.baseline else "check"
    print(f"== regression {label}: {args.build} ==")
    print(f"  수집 {len(tasks)} → 실행 {len(selected)} · 제외 {len(excluded)}")
    for s in _exclusion_summary(excluded):
        print(f"    - {s}")
    print()

    results = []
    for n, t in enumerate(selected, 1):
        print(f"  [{n}/{len(selected)}] {t.ckpt} · {t.cmd[:88]}", flush=True)
        r = run_one(t.cmd, bdir, args.timeout)
        r["ckpt"] = t.ckpt
        r["role"] = t.role
        results.append(r)
        print(f"        exit {r['exit']}  {r['secs']}s", flush=True)

    payload = {
        "build": args.build,
        "mode": label,
        "segment": args.segment,
        "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "collected": len(tasks),
        "ran": len(selected),
        "excluded": [{"ckpt": t.ckpt, "cmd": t.cmd, "why": w} for t, w in excluded],
        "results": results,
    }

    if args.baseline:
        _write_state(state_path(args.build, "baseline"), payload)
        passed = sum(1 for r in results if r["exit"] == 0)
        print(f"\n  기준선 기록: 통과 {passed} · 실패 {len(results) - passed}")
        print(f"  저장 위치: {state_path(args.build, 'baseline')}")
        if args.json:
            print(json.dumps(payload, ensure_ascii=False))
        return 0

    # --check : 기준선 대비 통과 → 실패 만 회귀
    regressions, held, base_fail, newly = [], [], [], []
    for r in results:
        b = base.get(r["cmd"])
        if b is None:
            newly.append(r)
        elif b["exit"] == 0 and r["exit"] != 0:
            r["baseline_exit"] = b["exit"]
            r["baseline_secs"] = b["secs"]
            regressions.append(r)
        elif b["exit"] == 0:
            held.append(r)
        else:
            base_fail.append(r)

    payload["regressions"] = len(regressions)
    payload["held"] = len(held)
    payload["baseline_fail"] = len(base_fail)
    payload["not_in_baseline"] = len(newly)
    _write_state(state_path(args.build, "last-check"), payload)

    print(f"\n  회귀 {len(regressions)} · 유지 {len(held)} · 기준선FAIL {len(base_fail)}"
          f" · 기준선없음 {len(newly)}")
    for r in regressions:
        print(f"\n!! 회귀 [{r['ckpt']}] {r['cmd']}")
        print(f"   기준선 exit 0 ({r['baseline_secs']}s) → 지금 exit {r['exit']} ({r['secs']}s)")
        print("   --- 출력 ---")
        for line in r["tail"].splitlines()[-40:]:
            print(f"   {line}")
    print(f"\n== REGRESSIONS: {len(regressions)} ==")
    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
