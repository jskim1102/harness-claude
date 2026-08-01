#!/usr/bin/env python3
"""Lineage parity scan — feature-uniformity lint across a derivation group.

When projects derive from a parent module (plan.md `## 1 Build Type` source
axis: `modules:[parent]` / `extract:[parent]` / `reuse:[parent]`), the
inherited code is meant to stay in sync. This diffs each derivative's
common-path backend files against its parent, normalized for the obvious
project-specifics (logger name, project slug, mediamtx path prefix), and
surfaces files that have HIGH similarity but are NOT identical — i.e. files
that look meant-to-be-shared yet drifted. The CEO then judges real drift vs
intentional divergence (extra endpoints etc.) and dispatches a re-sync.

Design (CEO decision "A"): auto-diff common files + CEO judgment. The
similarity heuristic keeps noise low — a file that is only ~50% similar is
almost certainly project-specific (ignored), while ~90%+ similar-but-different
is a drift candidate. Identical files never surface.

read-only, advisory — ALWAYS exit 0 (never a gate). No code execution.
usage: lineage_parity_scan.py [<project-name>]
  (no arg) scan every lineage group.
  <name>  scan only the group that <name> belongs to (parent + derivatives).
"""
from __future__ import annotations

import difflib
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASES = (REPO / "modules", REPO / "claude-project")
SKIP = {"ceo"}
# Backend code surface compared for parity. Frontends/configs/.env diverge by
# design (per-project UI, ports, secrets) so they are out of scope.
SCAN_SUBDIR = "backend/app"
# After normalization: >= this ratio + not identical = drift candidate.
# Below it = treated as legitimately project-specific (not surfaced).
DRIFT_RATIO = 0.85


def _all_projects() -> dict[str, Path]:
    out: dict[str, Path] = {}
    for base in BASES:
        if not base.is_dir():
            continue
        for d in sorted(base.iterdir()):
            if d.is_dir() and d.name not in SKIP and not d.name.startswith("."):
                out[d.name] = d
    return out


def _parents_of(proj_dir: Path, known: set[str]) -> list[str]:
    """Parent slugs from plan.md `## 1` source axis (mirror of the dashboard's
    _derived_from). Only tokens matching an existing project are returned."""
    plan = proj_dir / "plan.md"
    if not plan.is_file():
        return []
    try:
        txt = plan.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = re.search(r"##\s*1\b.*?(?=\n##\s|\Z)", txt, re.S)
    sec = m.group(0) if m else ""
    refs: list[str] = []
    for inner in re.findall(r"(?:modules|extract|reuse)\s*:\s*\[([^\]]*)\]", sec):
        # 슬러그에 `(설명)` 이 붙어도 슬러그만 떼내도록 괄호도 분리문자에 포함
        # (dashboard _derived_from 와 동일 규칙).
        for tok in re.split(r"[,\s·+()]+", inner):
            tok = tok.strip().strip(":")
            if tok in known and tok != proj_dir.name:
                refs.append(tok)
    return list(dict.fromkeys(refs))


def _norm(text: str, a: str, b: str) -> str:
    """Neutralize the legitimate per-project differences so only real drift
    shows: logger names, and each project's slug in both hyphen and underscore
    form (covers MEDIAMTX_PATH_PREFIX values, log channels, comments)."""
    text = re.sub(r'getLogger\(["\'][^"\']*["\']\)', "getLogger(N)", text)
    for slug in (a, b):
        for variant in {slug, slug.replace("-", "_"), slug.replace("_", "-")}:
            text = text.replace(variant, "PROJ")
    return text


def _common_files(member: Path, parent: Path) -> list[str]:
    md, pd = member / SCAN_SUBDIR, parent / SCAN_SUBDIR
    if not (md.is_dir() and pd.is_dir()):
        return []
    # Recursive: shared code lives in subdirs too (inference/, streaming/) — the
    # very place lineage bugs land. Key by relative path so same-named files in
    # different subdirs (e.g. inference/__init__.py vs streaming/__init__.py)
    # stay distinct instead of colliding on basename.
    def rel(root: Path) -> set[str]:
        return {
            p.relative_to(root).as_posix()
            for p in root.rglob("*.py")
            if not p.name.startswith("test")
        }
    return sorted(rel(md) & rel(pd))


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _compare(member: str, parent: str, mdir: Path, pdir: Path) -> list[dict]:
    """Return drift candidates: high-similarity-but-not-identical common files."""
    out: list[dict] = []
    for fn in _common_files(mdir, pdir):
        mt = _norm(_read(mdir / SCAN_SUBDIR / fn), member, parent)
        pt = _norm(_read(pdir / SCAN_SUBDIR / fn), member, parent)
        if mt == pt:
            continue  # identical after normalization — in sync
        ratio = difflib.SequenceMatcher(None, mt, pt).ratio()
        if ratio >= DRIFT_RATIO:
            out.append({"file": f"{SCAN_SUBDIR}/{fn}", "member": member,
                        "parent": parent, "ratio": round(ratio, 3)})
    return out


def scan(target: str | None) -> list[dict]:
    projs = _all_projects()
    known = set(projs)
    pairs: list[tuple[str, str]] = []  # (member, parent)
    names = [target] if target else list(projs)
    for name in names:
        if name not in projs:
            continue
        # name as derivative → compare against its parents
        for par in _parents_of(projs[name], known):
            pairs.append((name, par))
        # name as parent → compare each derivative against it
        for other in projs:
            if other != name and name in _parents_of(projs[other], known):
                pairs.append((other, name))
    seen = set()
    drift: list[dict] = []
    for member, parent in pairs:
        key = (member, parent)
        if key in seen:
            continue
        seen.add(key)
        drift.extend(_compare(member, parent, projs[member], projs[parent]))
    return drift


def main() -> int:
    target = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        drift = scan(target)
    except Exception as e:  # advisory — never fail the caller
        print(f"lineage-parity: scan error (skipped): {e}", file=sys.stderr)
        return 0
    if not drift:
        print("lineage-parity: 계보 그룹 동기화 OK (drift 후보 없음)")
        return 0
    print(f"lineage-parity: ⚠ drift 후보 {len(drift)}건 — CEO 판단 필요 "
          "(진짜 drift vs 의도된 분기):")
    for d in sorted(drift, key=lambda x: -x["ratio"]):
        print(f"  {d['member']} ↔ {d['parent']}  {d['file']}  "
              f"(유사도 {d['ratio']} — 거의 같은데 다름)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
