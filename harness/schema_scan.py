#!/usr/bin/env python3
"""harness schema scan — 정적 DB 스키마 현황 (읽기전용, DB·venv 불필요).

각 빌드(claude-project/*, modules/*)의 스키마 정의를 텍스트 파싱해 출력한다.
스키마 소스 우선순위:
  1. SQLAlchemy `models.py` 의 `__tablename__` + 컬럼
  2. alembic migration 의 `op.create_table(...)` (RULES §9 — 스키마는 migration 에 산다)
코드를 실행하지 않으므로(import X) 환경변수·의존성 없이 항상 동작.

테이블이 없어도 DB 인프라(db.py / DATABASE_URL / engine) 가 있으면
"테이블 미정의" 로, 아무것도 없으면 "DB 미사용" 으로 구분한다.

usage: schema_scan.py [<build-name>]   # 인자 없으면 전체
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP = {".venv", "venv", "node_modules", "__pycache__", ".git", "dist",
        "build", ".pytest_cache", ".mypy_cache", ".sources"}

CLASS_RE = re.compile(r"^class\s+(\w+)\s*\([^)]*\)\s*:")
TABLE_RE = re.compile(r"""__tablename__\s*=\s*["']([^"']+)["']""")
COL_MAPPED_RE = re.compile(r"^\s*(\w+)\s*:\s*Mapped\[[^\]]*\]\s*=\s*mapped_column\((.*)\)\s*$")
COL_CLASSIC_RE = re.compile(r"^\s*(\w+)\s*=\s*Column\((.*)\)\s*$")
OP_TABLE_RE = re.compile(r"""op\.create_table\(\s*["'](\w+)["']""")
SA_COL_RE = re.compile(r"""sa\.Column\(\s*["'](\w+)["']\s*,\s*(?:sa\.)?(\w+(?:\([^)]*\))?)""")
INFRA_RE = re.compile(r"create_async_engine|create_engine|DeclarativeBase|declarative_base|DATABASE_URL")


def _walk(root: Path):
    """os.walk with SKIP-dir pruning (don't descend into .venv etc)."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP]
        yield Path(dirpath), filenames


def find_files(build: Path, name: str) -> list[Path]:
    return [d / f for d, fs in _walk(build) for f in fs if f == name]


def find_migrations(build: Path) -> list[Path]:
    out = []
    for d, fs in _walk(build):
        if d.name == "versions" and d.parent.name in ("alembic", "migrations"):
            out += [d / f for f in fs if f.endswith(".py") and f != "__init__.py"]
    return out


def _flags(blob: str) -> list[str]:
    out = []
    if "primary_key=True" in blob:
        out.append("PK")
    if "unique=True" in blob:
        out.append("UNIQUE")
    if "nullable=False" in blob:
        out.append("NOT NULL")
    fk = re.search(r"""ForeignKey\(["']([^"']+)""", blob)
    if fk:
        out.append(f"FK->{fk.group(1)}")
    if "index=True" in blob:
        out.append("idx")
    return out


def parse_models(path: Path):
    """SQLAlchemy models.py → [(table, [(col, type, [flags])])]."""
    tables, cur = [], None
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return tables
    for ln in lines:
        if CLASS_RE.match(ln):
            cur = {"table": None, "cols": []}
            tables.append(cur)
            continue
        if cur is None:
            continue
        tm = TABLE_RE.search(ln)
        if tm:
            cur["table"] = tm.group(1)
            continue
        m = COL_MAPPED_RE.match(ln) or COL_CLASSIC_RE.match(ln)
        if m:
            typ = ""
            tmatch = re.match(r"\s*([A-Z]\w*(?:\([^)]*\))?)", m.group(2))
            if tmatch:
                typ = tmatch.group(1)
            cur["cols"].append((m.group(1), typ, _flags(m.group(2))))
    return [t for t in tables if t["table"]]


def parse_migrations(migs: list[Path]):
    """alembic op.create_table → [(table, [(col, type, [flags])])] (최신 정의 누적)."""
    tables, order, cur = {}, [], None
    for mp in sorted(migs):
        try:
            lines = mp.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in lines:
            tm = OP_TABLE_RE.search(ln)
            if tm:
                cur = tm.group(1)
                if cur not in tables:
                    tables[cur] = []
                    order.append(cur)
                continue
            if cur is None:
                continue
            cm = SA_COL_RE.search(ln)
            if cm:
                tables[cur].append((cm.group(1), cm.group(2), _flags(ln)))
            elif re.match(r"\s*\)", ln):
                cur = None
    return [{"table": t, "cols": tables[t]} for t in order]


def db_infra(build: Path) -> bool:
    """테이블이 없어도 DB 연결/엔진 코드가 있나 (tests 제외)."""
    for d, fs in _walk(build):
        if d.name == "tests":
            continue
        for f in fs:
            if not f.endswith(".py") or f.startswith("test_"):
                continue
            try:
                if INFRA_RE.search((d / f).read_text(errors="replace")):
                    return True
            except OSError:
                pass
    return False


def db_hint(build: Path):
    dbs, blob = [], ""
    for d, fs in _walk(build):
        for f in fs:
            if f.endswith(".db"):
                dbs.append(d / f)
            if f == ".env" or f.startswith("docker-compose"):
                try:
                    blob += (d / f).read_text(errors="replace")
                except OSError:
                    pass
    engine = "postgres" if re.search(r"postgres", blob, re.I) else ("sqlite" if dbs else None)
    return engine, dbs


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
    print("== DB 스키마 현황 (정적 스캔 · 읽기전용 · RULES §9) ==\n")
    for parent, b in bs:
        engine, dbs = db_hint(b)
        migs = find_migrations(b)
        tag = f"  [{engine}]" if engine else ""
        print(f"■ {parent}/{b.name}{tag}")

        m_tables = [t for mp in find_files(b, "models.py") for t in parse_models(mp)]
        mig_tables = parse_migrations(migs)
        tables = m_tables or mig_tables
        source = "models.py" if m_tables else ("migration" if mig_tables else None)

        if tables:
            print(f"   tables (source: {source})")
            for t in tables:
                print(f"   · {t['table']}")
                for c, typ, flags in t["cols"]:
                    fl = ("  " + " ".join(flags)) if flags else ""
                    print(f"       {c:<18}{typ}{fl}")
        elif engine or migs or db_infra(b):
            print("   (DB 연결·인프라 있음 — 테이블 스키마 아직 미정의:"
                  " models.py / migration create_table 없음)")
        else:
            print("   (DB 미사용 — plan only 또는 비DB 빌드)")

        if migs:
            print(f"   migrations: {len(migs)} files (latest: {sorted(p.name for p in migs)[-1]})")
        elif tables or engine or db_infra(b):
            print("   migrations: 없음 (create_all 또는 미설정 — RULES §9 는 migration 권장)")
        if dbs:
            print(f"   live db: {', '.join(str(p.relative_to(REPO)) for p in dbs)}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
