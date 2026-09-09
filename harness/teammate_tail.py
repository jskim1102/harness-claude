"""CTO 콕핏 rail 의 읽기전용 teammate 전사 뷰어.

Usage: python3 teammate_tail.py <cto-name> <role>

빌드 dir(claude-project/<name> | modules/<name>)의 Claude 프로젝트 전사
디렉토리에서 1행 agent-setting 이 <role> 인 최신 jsonl 을 폴링으로 추적해
pretty-tail 한다. teammate 재spawn(새 jsonl)은 자동 전환. 읽기전용 —
어떤 파일도 쓰지 않는다. 레코드 단위 오류는 조용히 스킵하고 pane 프로세스는
죽지 않는다 (스펙 2026-07-29-cto-cockpit-rail-design.md §1).
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
from datetime import datetime

POLL_SEC = 2.0
TAIL_BYTES = 20_000  # 새 파일에 붙을 때 마지막 이 정도만 되감아 보여준다.
STATUS_TICK_SEC = 0.5  # 하단 상태줄 갱신 주기 (시계가 돌면 뷰어 생존 증거)

COLORS = {"planner": "34", "designer": "35", "reviewer": "33"}
RESET = "\x1b[0m"
DIM = "\x1b[2m"


def repo_root() -> str:
    return os.environ.get(
        "HARNESS_ROOT",
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )


def build_dir(name: str) -> str | None:
    for base in ("claude-project", "modules"):
        cand = os.path.join(repo_root(), base, name)
        if os.path.isdir(cand):
            return cand
    return None


def project_dir(build: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]", "-", os.path.abspath(build))
    return os.path.expanduser(os.path.join("~", ".claude", "projects", slug))


def transcript_role(path: str) -> str | None:
    """1행이 agent-setting 레코드면 그 role, 아니면 None."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            first = fh.readline()
        rec = json.loads(first)
    except (OSError, ValueError):
        return None
    if rec.get("type") != "agent-setting":
        return None
    setting = rec.get("agentSetting")
    return setting if isinstance(setting, str) else None


def _subagent_role(meta_path: str) -> str | None:
    """subagents/agent-*.meta.json 의 teammate role (아니면 None)."""
    try:
        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        return None
    # one-shot Task subagent 배제 — in-process teammate 만 rail 대상.
    if meta.get("taskKind") not in (None, "in_process_teammate"):
        return None
    name = meta.get("name") or meta.get("agentType")
    return name if isinstance(name, str) else None


def _fresh_boundary(name: str) -> float:
    """add-cto --fresh 가 남긴 경계 시각 — 그 이전 전사는 폐기된 대화의 잔재라
    rail 에 보여주지 않는다 (없으면 0 = 전부 허용)."""
    path = os.path.expanduser(f"~/.harness-claude/cto-fresh-{name}.ts")
    try:
        with open(path, encoding="utf-8") as fh:
            return float(fh.read().strip())
    except (OSError, ValueError):
        return 0.0


def newest_transcript(proj: str, role: str, min_mtime: float = 0.0) -> str | None:
    best, best_mtime = None, -1.0
    try:
        names = os.listdir(proj)
    except OSError:
        names = []
    # 구형(claude-teams 래퍼 시절): top-level <session>.jsonl, 1행 agent-setting.
    for fname in names:
        if not fname.endswith(".jsonl"):
            continue
        path = os.path.join(proj, fname)
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime <= best_mtime or mtime < min_mtime:
            continue
        if transcript_role(path) == role:
            best, best_mtime = path, mtime
    # 현행(순수 claude in-process, 2026-07-29 실측):
    # <proj>/<lead세션>/subagents/agent-*.jsonl + 같은 이름 .meta.json.
    for meta in glob.glob(os.path.join(proj, "*", "subagents", "agent-*.meta.json")):
        path = meta[: -len(".meta.json")] + ".jsonl"
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        if mtime <= best_mtime or mtime < min_mtime:
            continue
        if _subagent_role(meta) == role:
            best, best_mtime = path, mtime
    return best


def _session_label(path: str) -> str:
    stem = os.path.basename(path)
    stem = stem[: -len(".jsonl")] if stem.endswith(".jsonl") else stem
    if stem.startswith("agent-"):
        return stem.rsplit("-", 1)[-1][:8]
    return stem[:8]


def _ts_epoch(rec: dict) -> float | None:
    raw = rec.get("timestamp")
    if isinstance(raw, str) and "T" in raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return None
    return None


def _ts(rec: dict) -> str:
    raw = rec.get("timestamp")
    if isinstance(raw, str) and "T" in raw:
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.astimezone().strftime("%H:%M:%S")
        except ValueError:
            return raw.split("T", 1)[1][:8]
    return ""


def _tool_summary(block: dict) -> str:
    name = block.get("name", "?")
    inp = block.get("input") or {}
    for key in ("file_path", "command", "pattern", "skill", "subject", "prompt"):
        val = inp.get(key)
        if isinstance(val, str) and val:
            return f"{name} {' '.join(val.split())[:70]}"
    if name == "SendMessage":
        to = inp.get("to") or inp.get("recipient") or ""
        content = " ".join(str(inp.get("content") or inp.get("message") or "").split())[:70]
        return f"SendMessage →{to} {content}"
    return name


def record_kind(rec: dict) -> str | None:
    """상태 판정용 레코드 분류. 뷰어가 이미 파싱하는 전사를 그대로 쓴다.

    mtime 으로 판정하면 안 된다 — 15분짜리 code-review Agent 처럼 **오래 걸리는
    도구 하나**를 도는 동안 전사에 아무것도 안 붙어 '작업중'이 '죽음'으로 보인다
    (2026-08-18 사용자 지적). 마지막 레코드의 종류가 진짜 상태다:
      tool_use  = 도구 실행 중        (assistant 가 도구를 부르고 결과 대기)
      user      = 응답 생성 중        (도구 결과가 들어와 모델이 생각 중)
      text      = 완료/대기           (텍스트만 있는 assistant = 턴을 마쳤다)
    """
    rtype = rec.get("type")
    if rtype == "assistant":
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            return None
        if any(isinstance(b, dict) and b.get("type") == "tool_use" for b in content):
            return "tool_use"
        if any(isinstance(b, dict) and b.get("type") == "text" and b.get("text", "").strip()
               for b in content):
            return "text"
        return None
    if rtype == "user":
        return "user"
    return None


def _age(sec: float) -> str:
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}s"
    if sec < 3600:
        return f"{sec // 60}m{sec % 60}s"
    return f"{sec // 3600}h{(sec % 3600) // 60}m"


def status_text(role: str, kind: str | None, age_sec: float, session: str | None) -> str:
    """상태줄 본문 (색 코드 없는 순수 문자열 — 테스트가 이 함수를 고정한다)."""
    if session is None:
        return f"·  {role} 전사 없음 (미배치)"
    tail = f" · sess {session}"
    if kind == "tool_use":
        return f"▶ {role} WORKING · 도구 실행 중 {_age(age_sec)}{tail}"
    if kind == "user":
        return f"▶ {role} WORKING · 응답 생성 중 {_age(age_sec)}{tail}"
    if kind == "text":
        return f"⏸ {role} 대기 · 마지막 응답 {_age(age_sec)} 전{tail}"
    return f"·  {role} 상태 미상{tail}"


def _draw_status(text: str, color: str) -> None:
    clock = datetime.now().strftime("%H:%M:%S")
    line = f"{text} · {clock}"[:200]
    sys.stdout.write(f"\r\x1b[K{DIM}\x1b[{color}m{line}{RESET}")
    sys.stdout.flush()


def _clear_status() -> None:
    sys.stdout.write("\r\x1b[K")
    sys.stdout.flush()


def render(rec: dict, color: str) -> None:
    rtype = rec.get("type")
    ts = _ts(rec)
    if rtype == "assistant":
        content = (rec.get("message") or {}).get("content")
        if not isinstance(content, list):
            return
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    print(f"\x1b[{color}m● {ts}{RESET} {text[:700]}", flush=True)
            elif block.get("type") == "tool_use":
                print(f"{DIM}  ⚙ {_tool_summary(block)}{RESET}", flush=True)
    elif rtype == "user":
        content = (rec.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            print(f"{DIM}▷ {ts} {content.strip()[:300]}{RESET}", flush=True)


def follow(name: str, role: str) -> None:
    color = COLORS.get(role, "36")
    build = None
    while build is None:
        build = build_dir(name)
        if build is None:
            time.sleep(POLL_SEC)
    proj = project_dir(build)
    print(f"\x1b[1;{color}m── {role} viewer · cto:{name} ──{RESET}", flush=True)

    current, offset, buf = None, 0, ""
    last_scan = 0.0
    kind: str | None = None          # 마지막 레코드 종류 = 현재 상태
    kind_at = time.time()            # 그 레코드 시각 (경과 표시용)
    while True:
        now = time.time()
        if now - last_scan >= POLL_SEC:
            last_scan = now
            newest = newest_transcript(proj, role, _fresh_boundary(name))
            if newest and newest != current:
                current = newest
                size = os.path.getsize(current) if os.path.exists(current) else 0
                offset = max(0, size - TAIL_BYTES)
                buf = ""
                kind, kind_at = None, now
                _clear_status()
                print(
                    f"\x1b[1;{color}m── session {_session_label(current)} ──{RESET}",
                    flush=True,
                )
        if current is None:
            _draw_status(status_text(role, None, 0, None), color)
            time.sleep(STATUS_TICK_SEC)
            continue
        try:
            size = os.path.getsize(current)
            if size < offset:  # 파일 교체/축소 — 처음부터
                offset, buf = 0, ""
            if size > offset:
                with open(current, encoding="utf-8", errors="ignore") as fh:
                    fh.seek(offset)
                    chunk = fh.read()
                    offset = fh.tell()
                buf += chunk
                *lines, buf = buf.split("\n")
                if lines:
                    _clear_status()   # 상태줄 지우고 본문을 그 자리부터 흘린다
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    k = record_kind(rec)
                    if k:
                        kind, kind_at = k, (_ts_epoch(rec) or time.time())
                    try:
                        render(rec, color)
                    except Exception:
                        continue
        except OSError:
            pass
        _draw_status(
            status_text(role, kind, time.time() - kind_at, _session_label(current)),
            color,
        )
        time.sleep(STATUS_TICK_SEC)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: teammate_tail.py <cto-name> <role>", file=sys.stderr)
        return 2
    try:
        follow(sys.argv[1], sys.argv[2])
    except KeyboardInterrupt:
        print()   # 상태줄 뒤에 개행 — 종료 후 프롬프트가 겹치지 않게
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
