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
                print(
                    f"\x1b[1;{color}m── session {_session_label(current)} ──{RESET}",
                    flush=True,
                )
        if current is None:
            time.sleep(POLL_SEC)
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
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        render(json.loads(line), color)
                    except Exception:
                        continue
        except OSError:
            pass
        time.sleep(0.5)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: teammate_tail.py <cto-name> <role>", file=sys.stderr)
        return 2
    try:
        follow(sys.argv[1], sys.argv[2])
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
