"""Harness Dashboard backend — 현황 API + control mutations.

harness/cli.py 의 현황 수집 함수를 재사용해 modules/ + claude-project/ 의
모듈·프로젝트 상태를 JSON 으로 노출한다 (GET /api/state).
+ control mutations (POST): cto start/stop, dev/docker toggle — run.sh·dev.sh·
docker compose 를 호출한다.

보안 (interim — 풀 로그인은 docs/LATER.md "dashboard 인증"):
- **mutation 은 토큰 게이트.** `DASH_TOKEN` env 가 설정돼야 하고, 요청은
  `X-Dash-Token` 헤더로 그 값을 보내야 통과 (`secrets.compare_digest`).
  DASH_TOKEN 미설정 시 mutation 은 503 (기본 거부 — fail-closed).
- **CORS 제한**: 기본 cross-origin 차단 (frontend 는 /api 동일출처 프록시라 불필요).
  `DASH_ORIGINS`(쉼표구분) 로만 추가 허용. (이전 `*` 는 cross-origin mutation 위험.)
- GET 현황은 열림 (읽기전용). backend 는 127.0.0.1 바인딩 (frontend 가 프록시).
"""
from __future__ import annotations

import os
import re
import secrets
import subprocess
import sys
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# harness repo root 를 path 에 올려 cli.py 현황 함수 재사용
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from harness import cli  # noqa: E402


def require_token(x_dash_token: str = Header(default="")) -> None:
    """mutation 게이트 — DASH_TOKEN env 설정 + X-Dash-Token 헤더 일치 필요.
    미설정 = fail-closed (mutation 비활성). 풀 로그인 전 interim 보호."""
    expected = os.environ.get("DASH_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="mutations disabled — set DASH_TOKEN env to enable")
    if not secrets.compare_digest(x_dash_token, expected):
        raise HTTPException(status_code=401, detail="invalid or missing X-Dash-Token")

app = FastAPI(title="Harness Dashboard")
# CORS: 기본 cross-origin 차단 (frontend 는 /api 동일출처 프록시라 불필요).
# DASH_ORIGINS(쉼표구분) 로만 명시 허용. cross-origin mutation(CSRF 류) 방어.
_origins = [o.strip() for o in os.environ.get("DASH_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware, allow_origins=_origins, allow_methods=["*"], allow_headers=["*"]
)

BASES = {"module": REPO / "modules", "project": REPO / "claude-project"}
SKIP = {"ceo"}  # CEO workspace 는 빌드 산출물 아님


def _derived_from(d: Path, others: set[str]) -> list[str]:
    """진짜 파생관계만 반환. plan.md ## 1 Build Type 의 source 축
    `modules:[...]` / `extract:[...]` / `reuse:[...]` 괄호 안에서 기존 노드
    이름과 일치하는 슬러그만 lineage 부모로 본다. (예: cam-distance 의
    `modules:[rtsp-streaming]` → rtsp-streaming). Library Check 의 no-overlap
    언급 등 단순 언급은 무시 — 그래서 ## 1 섹션 + 괄호 안만 스캔한다."""
    plan = d / "plan.md"
    if not plan.is_file():
        return []
    try:
        txt = plan.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = re.search(r"##\s*1\b.*?(?=\n##\s|\Z)", txt, re.S)  # ## 1 Build Type 섹션만
    sec = m.group(0) if m else ""
    refs = []
    for inner in re.findall(r"(?:modules|extract|reuse)\s*:\s*\[([^\]]*)\]", sec):
        for tok in re.split(r"[,\s·+]+", inner):
            tok = tok.strip().strip(":")
            if tok in others:
                refs.append(tok)
    return list(dict.fromkeys(refs))


def _git_url(d: Path) -> str | None:
    """own .git 이 있으면 origin remote URL 을 브라우저용 https 로 정규화해 반환."""
    if not (d / ".git").exists():
        return None
    try:
        r = subprocess.run(
            ["git", "-C", str(d), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=4,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    u = r.stdout.strip()
    if not u:
        return None
    if u.startswith("git@"):  # git@github.com:user/repo(.git) → https://github.com/user/repo
        u = "https://" + u[len("git@"):].replace(":", "/", 1)
    if u.endswith(".git"):
        u = u[:-4]
    return u if u.startswith("http") else None


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/state")
def state() -> dict:
    pub = cli._docker_published_ports()
    host = cli._host_listening_ports()
    live = cli._live_cto_sessions()
    # 표 컬럼 = PORT.md 와 동일 순서(cli.PORT_COLS) + PostgreSQL 뒤 DB 컬럼
    columns = []
    for label, var in cli.PORT_COLS:
        columns.append({"label": label, "var": var, "kind": "port"})
        if var == cli.DB_ENGINE_AFTER:
            columns.append({"label": "DB", "var": "_db", "kind": "db"})
    items = []
    for kind, base in BASES.items():
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if not d.is_dir() or d.name in SKIP or d.name.startswith("."):
                continue
            env = cli._read_env_ports(d / ".env")
            be = env.get("BACKEND_PORT", "")
            cells = {}
            running = declared = 0
            for _label, var in cli.PORT_COLS:
                p = env.get(var, "")
                if p:
                    declared += 1
                    if p in pub:
                        mode = "docker"
                    elif var in ("BACKEND_PORT", "FRONTEND_PORT") and p in host:
                        mode = "dev"  # app 컬럼만 dev.sh(호스트) 개념 존재
                    else:
                        mode = "down"
                    up = mode in ("docker", "dev")
                    cells[var] = {"port": p, "up": up, "mode": mode}
                    running += 1 if up else 0
                else:
                    cells[var] = None
            if declared == 0:
                status = "none"
            elif running == declared:
                status = "up"
            elif running == 0:
                status = "down"
            else:
                status = "partial"
            docker_up = any((c or {}).get("mode") == "docker" for c in cells.values())
            dev_up = any((c or {}).get("mode") == "dev" for c in cells.values())
            items.append(
                {
                    "name": d.name,
                    "type": kind,
                    "path": str(d),  # 서버 실제 경로(절대)
                    "git_repo": (d / ".git").exists(),  # own .git = 완료, 없으면 진행중
                    "git_url": _git_url(d),  # 완료 repo origin (브라우저 링크용 https)
                    "cto_active": d.name in live,
                    "docker_up": docker_up,  # docker-published 포트 1개+ = 컨테이너 실행중
                    "dev_up": dev_up,        # 호스트 dev 서버(./dev.sh) 실행중
                    "offset": (int(be) - 8000) if be.isdigit() else None,
                    "db": cli._detect_db_engine(d, env),
                    "cells": cells,
                    "running": running,
                    "declared": declared,
                    "status": status,
                }
            )
    # lineage 그래프 엣지: 파생 노드(plan.md source)는 부모에만 연결, root 만 CEO 연결.
    # 예: cam-distance 는 rtsp-streaming 에서 파생 → rtsp→cam 만, CEO→cam 은 없음.
    names = {it["name"] for it in items}
    links = []
    for it in items:
        derived = _derived_from(Path(it["path"]), names - {it["name"]})
        if derived:
            for src in derived:
                links.append({"source": src, "target": it["name"], "kind": "lineage"})
        else:
            links.append({"source": "CEO", "target": it["name"], "kind": "ceo"})
    return {"columns": columns, "items": items, "links": links}


# ── mutations (control console; 인증 없음 — 추후 로그인 추가 예정) ──
# 주의: frontend(8166)가 공인 노출 → /api 프록시 경유 외부 호출 가능.
def _resolve_project(name: str) -> Path | None:
    """name 을 스캔된 빌드 dir 로 안전 resolve (kebab 검증 + .env 존재). 임의 명령 방지."""
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", name or "") or name in SKIP:
        return None
    for base in BASES.values():
        d = base / name
        if d.is_dir() and (d / ".env").is_file():
            return d
    return None


@app.post("/api/cto/{name}/start", dependencies=[Depends(require_token)])
def cto_start(name: str) -> dict:
    """CTO 세션 활성화/재개 (run.sh add-cto — plan.md 또는 specs/tasks.md 있으면 스폰)."""
    if not _resolve_project(name):
        return {"ok": False, "error": "unknown project"}
    r = subprocess.run(
        [str(REPO / "run.sh"), "add-cto", name],
        cwd=str(REPO), capture_output=True, text=True, timeout=120,
    )
    return {"ok": r.returncode == 0, "out": (r.stdout + r.stderr)[-2000:]}


@app.post("/api/cto/{name}/stop", dependencies=[Depends(require_token)])
def cto_stop(name: str) -> dict:
    """CTO 세션 정지 (run.sh stop-cto — 작업 보존, 세션+프로세스만)."""
    if not _resolve_project(name):
        return {"ok": False, "error": "unknown project"}
    r = subprocess.run(
        [str(REPO / "run.sh"), "stop-cto", name],
        cwd=str(REPO), capture_output=True, text=True, timeout=60,
    )
    return {"ok": r.returncode == 0, "out": (r.stdout + r.stderr)[-2000:]}


@app.post("/api/dev/{name}/toggle", dependencies=[Depends(require_token)])
def dev_toggle(name: str) -> dict:
    """호스트 dev 서버 토글 — 실행중이면 ./dev.sh down, 아니면 ./dev.sh up (venv uvicorn + vite)."""
    d = _resolve_project(name)
    if not d:
        return {"ok": False, "error": "unknown project"}
    sh = d / "dev.sh"
    if not sh.is_file():
        return {"ok": False, "error": "dev.sh 없음 (phase1 산출물)"}
    pub = cli._docker_published_ports()
    host = cli._host_listening_ports()
    env = cli._read_env_ports(d / ".env")
    appports = [env.get("BACKEND_PORT", ""), env.get("FRONTEND_PORT", "")]
    dev_up = any(p and p in host and p not in pub for p in appports)
    action = "down" if dev_up else "up"
    r = subprocess.run([str(sh), action], cwd=str(d), capture_output=True, text=True, timeout=90)
    return {"ok": r.returncode == 0, "action": action, "out": (r.stdout + r.stderr)[-2000:]}


@app.post("/api/docker/{name}/toggle", dependencies=[Depends(require_token)])
def docker_toggle(name: str) -> dict:
    """docker compose 토글 — 실행중이면 down, 아니면 up -d --build."""
    d = _resolve_project(name)
    if not d:
        return {"ok": False, "error": "unknown project"}
    pub = cli._docker_published_ports()
    env = cli._read_env_ports(d / ".env")
    up = any(env.get(var, "") in pub for _l, var in cli.PORT_COLS)
    cmd = ["docker", "compose", "down"] if up else ["docker", "compose", "up", "-d", "--build"]
    r = subprocess.run(cmd, cwd=str(d), capture_output=True, text=True, timeout=300)
    return {
        "ok": r.returncode == 0,
        "action": "down" if up else "up",
        "out": (r.stdout + r.stderr)[-2000:],
    }
