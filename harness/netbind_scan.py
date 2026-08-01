#!/usr/bin/env python3
"""harness netbind scan — 웹서버 외부접속 바인딩 정적 검사 (RULES §5.3, 읽기전용).

각 빌드(claude-project/*, modules/*)가 전 인터페이스(`0.0.0.0`)로 바인딩하는지
텍스트 파싱으로 확인한다. localhost 전용(`127.0.0.1`/`localhost`) = 외부 접속 불가
= §5.3 위반. 코드를 실행하지 않으므로(import X) 환경·의존성 없이 항상 동작.

검사:
  · 프론트(Vite dev): frontend/vite.config.* 에 `server.host: true|'0.0.0.0'`
    (또는 dev 런처가 `--host 0.0.0.0`). 없거나 loopback 명시면 위반.
  · 백엔드(uvicorn): 런처(dev.sh/Dockerfile/compose/*.py)가 `0.0.0.0` 바인딩.
    bare `uvicorn`(host 미지정 = 기본 127.0.0.1)·loopback 명시면 위반.

fail-closed: 위반 1건이라도 있으면 exit 1 (게이트로 사용 가능).
usage: netbind_scan.py [<build-name>]   # 인자 없으면 전체
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist",
        "build", ".pytest_cache", ".mypy_cache", ".sources"}

VITE_CFG_RE = re.compile(r"vite\.config\.(js|ts|mjs|cjs)$")
# server.host: true | '0.0.0.0'  (server 블록 안이 아니어도 관대하게 잡음)
VITE_HOST_OK_RE = re.compile(r"""host\s*:\s*(true|["']0\.0\.0\.0["'])""")
VITE_HOST_LOOPBACK_RE = re.compile(r"""host\s*:\s*["'](127\.0\.0\.1|localhost)["']""")
HOST_FLAG_OK_RE = re.compile(r"--host[=\s]+0\.0\.0\.0|host\s*=\s*['\"]0\.0\.0\.0['\"]")
HOST_FLAG_LOOPBACK_RE = re.compile(
    r"--host[=\s]+(127\.0\.0\.1|localhost)|host\s*=\s*['\"](127\.0\.0\.1|localhost)['\"]")
UVICORN_RE = re.compile(r"\buvicorn\b")
VITE_LAUNCH_RE = re.compile(r"\bvite\b")


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        yield Path(dirpath), filenames


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _launchers(build: Path) -> list[Path]:
    """백엔드/프론트 기동을 정의하는 파일들 (host 바인딩이 박히는 곳)."""
    out = []
    for d, fs in _walk(build):
        for f in fs:
            if (f in ("dev.sh", "run.sh") or f == "Dockerfile" or f.endswith(".Dockerfile")
                    or f.startswith("docker-compose") or f == "main.py" or f == "__main__.py"
                    or f == "package.json"):
                out.append(d / f)
    return out


def check_frontend(build: Path):
    """→ (status, evidence). status: 'ok'|'violation'|'na'."""
    cfgs = [d / f for d, fs in _walk(build) for f in fs if VITE_CFG_RE.search(f)]
    if not cfgs:
        return "na", "vite.config 없음 (Vite 프론트 아님)"
    for cfg in cfgs:
        blob = _read(cfg)
        if VITE_HOST_LOOPBACK_RE.search(blob):
            return "violation", f"{cfg.relative_to(build)} 에 server.host loopback 명시"
        if VITE_HOST_OK_RE.search(blob):
            return "ok", f"{cfg.relative_to(build)} server.host 설정됨"
    # vite.config 에 server.host 없음 → dev 런처가 --host 0.0.0.0 주면 통과
    for lp in _launchers(build):
        blob = _read(lp)
        if VITE_LAUNCH_RE.search(blob) and HOST_FLAG_OK_RE.search(blob):
            return "ok", f"{lp.relative_to(build)} 가 vite --host 0.0.0.0"
    return ("violation",
            "vite.config 에 server.host 없음 (기본 127.0.0.1) — `server: {{ host: true }}` 추가 필요")


def check_backend(build: Path):
    launchers = _launchers(build)
    found_uvicorn = False
    ok_hit = loop_hit = None
    bare = []
    for lp in launchers:
        blob = _read(lp)
        for ln in blob.splitlines():
            if not UVICORN_RE.search(ln):
                continue
            found_uvicorn = True
            if HOST_FLAG_LOOPBACK_RE.search(ln):
                loop_hit = lp
            elif HOST_FLAG_OK_RE.search(ln):
                ok_hit = lp
            elif "uvicorn.run(" in ln or "exec uvicorn" in ln or ln.strip().startswith(("uvicorn", "CMD", "RUN", "command")):
                bare.append(lp)
    if not found_uvicorn:
        return "na", "uvicorn 기동 없음 (백엔드 아님 또는 다른 서버)"
    if loop_hit:
        return "violation", f"{loop_hit.relative_to(build)} uvicorn loopback 바인딩"
    if ok_hit:
        return "ok", f"{ok_hit.relative_to(build)} uvicorn --host 0.0.0.0"
    if bare:
        return ("violation",
                f"{bare[0].relative_to(build)} uvicorn host 미지정 (기본 127.0.0.1) — --host 0.0.0.0 필요")
    return "ok", "uvicorn 기동에 loopback 없음"


def builds(filt: str | None):
    out = []
    for parent in ("claude-project", "modules"):
        d = REPO / parent
        if not d.is_dir():
            continue
        for b in sorted(d.iterdir()):
            if not b.is_dir() or b.name == "ceo" or b.name.startswith("."):
                continue
            if filt and b.name != filt:
                continue
            out.append((parent, b))
    return out


def main() -> int:
    filt = sys.argv[1] if len(sys.argv) > 1 else None
    bs = builds(filt)
    if not bs:
        print(f"빌드 없음{': ' + filt if filt else ''}")
        return 0
    print("== 웹서버 외부접속 바인딩 (정적 스캔 · 읽기전용 · RULES §5.3) ==\n")
    violations = 0
    unchecked = []          # frontend·backend 둘 다 na = 이 스캔이 아무것도 못 본 빌드
    mark = {"ok": "✓", "violation": "✗ 위반", "na": "—"}
    for parent, b in bs:
        fs_status, fs_ev = check_frontend(b)
        be_status, be_ev = check_backend(b)
        violations += (fs_status == "violation") + (be_status == "violation")
        none_checked = fs_status == "na" and be_status == "na"
        if none_checked:
            unchecked.append(f"{parent}/{b.name}")
        print(f"■ {parent}/{b.name}{'   ⊘ 미검사' if none_checked else ''}")
        print(f"   frontend {mark[fs_status]:<6} {fs_ev}")
        print(f"   backend  {mark[be_status]:<6} {be_ev}")
        print()
    if violations:
        print(f"== netbind: FAIL ✗ ({violations} 위반 — §5.3: 항상 0.0.0.0 바인딩) ==")
        return 1
    if unchecked:
        # na 를 초록으로 세지 않는다 (2026-07-21). 이 스캐너는 uvicorn/vite 리터럴을
        # `_launchers()` 목록 파일에서만 찾으므로, 그 규약 밖 서버(stdlib
        # ThreadingHTTPServer 등)나 목록 밖 파일에서 bind 하는 구조는 **파일을 아예 열지
        # 않는다**. 그래도 위반 0 이라 예전엔 "ALL CLEAN ✓ / exit 0" 이 나왔다 — 위반이
        # 없는 게 아니라 안 본 것이라 §5.3 증거로 쓰면 거짓 안심이다.
        # exit 2 = 위반(1)과도, 통과(0)와도 구분되는 "증명 안 됨".
        print(f"== netbind: 미검사 {len(unchecked)}건 — 게이트 통과 아님 (exit 2) ==")
        for u in unchecked:
            print(f"   ⊘ {u}")
        print("   이 스캔은 uvicorn/vite 를 dev.sh·run.sh·Dockerfile·docker-compose*·")
        print("   main.py·__main__.py·package.json 에서만 찾는다. 그 밖에서 bind 하면 못 본다.")
        print("   §5.3 증명이 필요하면 런타임으로: `ss -ltnp | grep <port>` 가 0.0.0.0 인지")
        print("   + 비-loopback IP 로 실제 curl.")
        return 2
    print("== netbind: ALL CLEAN ✓ ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
