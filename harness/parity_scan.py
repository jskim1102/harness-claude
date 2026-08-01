#!/usr/bin/env python3
"""harness parity scan — dev/docker 포트 패리티 린트 (RULES §5.5, 읽기전용, advisory).

각 빌드의 `docker compose` 가 publish 하는 호스트 포트 집합과 `dev.sh`(호스트
venv+vite)가 띄우는 포트 집합을 정적 파싱해 diff 한다. 한쪽 모드에서만 뜨는
포트를 경고로 표면화한다 — 특히 image-only 의존 서비스(예 mediamtx)는 dev 에서
구조적으로 안 뜨므로 docker-only 로 드러난다.

advisory: 항상 exit 0 (게이트 아님 — 패리티 기대 정렬용 경고). 코드 실행 X.
usage: parity_scan.py [<build-name>]
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist",
        "build", ".pytest_cache", ".mypy_cache", ".sources"}

ENV_LINE_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]*)\s*=\s*(.+?)\s*$")
# ${VAR} / ${VAR:?msg} / ${VAR:-default} / $VAR — 전체(내부 콜론 포함)를 한 번에 소비.
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[-?+][^}]*)?\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def _walk(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        yield Path(dirpath), filenames


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def env_map(build: Path) -> dict[str, str]:
    """.env (우선) + .env.example 의 KEY=VALUE 를 합쳐 변수 해석용 맵."""
    m: dict[str, str] = {}
    for fn in (".env.example", ".env"):  # .env 가 example 을 덮어쓰도록 뒤에
        for d, fs in _walk(build):
            if fn in fs:
                for ln in _read(d / fn).splitlines():
                    mm = ENV_LINE_RE.match(ln)
                    if mm:
                        m[mm.group(1)] = mm.group(2).strip().strip("'\"")
    return m


def resolve(tok: str, env: dict[str, str]) -> str:
    """${VAR}/${VAR:?msg}/${VAR:-def}/$VAR → 값. 내부 콜론까지 통째로 치환해
    이후 split(':') 가 호스트:컨테이너만 보게 한다. 미해석 시 :-default 또는 변수명."""
    def sub(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        if name in env and env[name]:
            return env[name]
        dm = re.search(r":-([^}]*)\}$", m.group(0))  # ${VAR:-default}
        return dm.group(1) if dm else name
    return VAR_RE.sub(sub, tok)


def _host_port(item: str, env: dict[str, str]) -> str | None:
    """ports 항목 → 호스트 포트. `[IP:]HOST:CONTAINER[/proto]`. ${...} 먼저 해석."""
    item = item.lstrip("-").strip()
    if item[:1] in ("'", '"'):                       # 따옴표면 안쪽만
        q = item[0]
        end = item.find(q, 1)
        item = item[1:end] if end > 0 else item[1:]
    else:
        item = item.split("#")[0].split()[0]         # 비따옴표: 첫 토큰
    val = resolve(item, env).split("/")[0]           # /proto 제거
    parts = val.split(":")
    host = parts[-2] if len(parts) >= 2 else parts[0]
    host = host.strip()
    return host or None


def compose_ports(build: Path, env: dict[str, str]) -> set[str]:
    """docker-compose*.yml 의 호스트 publish 포트 집합."""
    out: set[str] = set()
    for d, fs in _walk(build):
        for f in fs:
            if not f.startswith("docker-compose") or not f.endswith((".yml", ".yaml")):
                continue
            in_ports = False
            for ln in _read(d / f).splitlines():
                stripped = ln.strip()
                if re.match(r"^ports\s*:", stripped):
                    in_ports = True
                    continue
                if in_ports:
                    if stripped.startswith("-"):
                        h = _host_port(stripped, env)
                        if h:
                            out.add(h)
                    elif stripped and not stripped.startswith("#"):
                        in_ports = False
    return out


def dev_ports(build: Path, env: dict[str, str]) -> set[str]:
    """dev.sh 가 띄우는 포트 — 템플릿상 backend+frontend (RULES §5.5)."""
    if not any("dev.sh" in fs for _d, fs in _walk(build)):
        return set()
    out = set()
    for var in ("BACKEND_PORT", "FRONTEND_PORT"):
        if var in env:
            out.add(env[var])
    return out


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
    print("== dev/docker 포트 패리티 (정적 스캔 · advisory · RULES §5.5) ==\n")
    warns = 0
    for parent, b in bs:
        env = env_map(b)
        cp = compose_ports(b, env)
        dp = dev_ports(b, env)
        if not cp and not dp:
            continue
        docker_only = sorted(cp - dp)
        dev_only = sorted(dp - cp)
        print(f"■ {parent}/{b.name}")
        print(f"   compose 포트: {', '.join(sorted(cp)) or '—'}")
        print(f"   dev.sh 포트 : {', '.join(sorted(dp)) or '—'}")
        if docker_only:
            warns += 1
            print(f"   ⚠ docker-only (dev 에서 안 뜸): {', '.join(docker_only)}"
                  " — image-only 의존 서비스면 PORT.md 에 docker-only 명시로 기대 정렬")
        if dev_only:
            warns += 1
            print(f"   ⚠ dev-only (compose 에 없음): {', '.join(dev_only)}")
        if not docker_only and not dev_only:
            print("   ✓ 패리티 일치")
        print()
    print(f"== parity: {warns} 경고 (advisory — 게이트 아님) ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
