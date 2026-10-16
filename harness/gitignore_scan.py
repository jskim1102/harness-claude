#!/usr/bin/env python3
"""harness gitignore scan — 빌드 저장소 경계 정적 검사 (RULES §16, 읽기전용).

각 빌드(claude-project/*, modules/*)에서 **커밋하면 올라갈 목록**을 뽑아 §16 A
목록(하네스 산출물)이 섞여 있는지 본다. 판단 여지가 없는 기계 검사다 — A 목록은
고정이고, 올라감 여부는 git 이 계산한다.

올라감 정의는 `./run.sh git-listup` 과 **같다**: `ls-files` ∪
`ls-files --others --exclude-standard`, 디스크에 실존하는 것만. 정의가 갈리면
CLI·대시보드·이 스캐너가 서로 다른 답을 주므로 한 곳으로 맞춘다.

왜 문서만으로 부족한가 (2026-07-31 실측): `.gitignore` 를 강제한 규칙은 §4.1 의
`.env` 한 줄뿐이었고, 나머지는 CTO 재량이라 8개 빌드가 11~33줄로 제각각이었다.
대부분은 관례로 수렴했지만 **2건이 샜다** — dataset-viewer 는 `.source/` 427MB
(단일 zip 192MB)가 올라감에 있었고(GitHub 파일당 100MB 하드리밋 → 첫 push 가
거부되고, 커밋 뒤엔 히스토리 rewrite 없이는 못 지운다), bulk-receipe 는
`.sources/`·`specs/` 가 남아 있었다. 재량에 맡기면 대부분 맞지만 **가장 비싼 쪽이
새는 걸 못 막는다** — 그래서 기계 검사를 둔다.

`.gitignore` 는 **이미 추적 중인 파일에 무효**라, 위반이 tracked 면 추적 해제가
따로 필요하다(사용자 명시 지시 사안 — §1). 그래서 둘을 구분해 보고한다.

usage: gitignore_scan.py [<build-name>]   # 인자 없으면 전체
exit: 0 = 위반 없음, 1 = 위반 있음
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASES = ("claude-project", "modules")
SKIP = {"ceo"}

# RULES §16 A — 하네스 산출물. 전 빌드 공통, 올라가면 안 된다.
# 값 = 사람이 읽을 사유 (보고서에 그대로 나간다).
FORBIDDEN = {
    ".claude": "하네스 세션 설정 (스킬이 하네스 repo 절대경로 심링크 → clone 시 dangling)",
    "plan.md": "계획서 — CTO lead 가 사용자와 작성·확정 (만드는 쪽 문서)",
    "specs": "빌드 관리 문서 (spec·tasks·decisions·learnings·design-contract)",
    "DESIGN.md": "디자인 시스템 산출물",
    ".source": "extract 원본·데이터셋 (대용량 — GitHub 파일당 100MB 하드리밋)",
    ".sources": "extract 원본·데이터셋 (대용량 — GitHub 파일당 100MB 하드리밋)",
    ".env": "실값·시크릿 (§4.1 — .env.example 만 올린다)",
}


def _git(d: Path, *args: str) -> tuple[int, str]:
    try:
        r = subprocess.run(["git", "-C", str(d), *args],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return -1, ""
    return r.returncode, r.stdout


def _z(raw: str) -> list[str]:
    return [t for t in raw.split("\0") if t != ""]


def builds(filt: str | None) -> list[tuple[str, Path]]:
    out = []
    for base in BASES:
        root = REPO / base
        if not root.is_dir():
            continue
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith(".") or d.name in SKIP:
                continue
            if filt and d.name != filt:
                continue
            out.append((base, d))
    return out


def scan(build: Path) -> tuple[str, list[dict]]:
    """(status, hits). status: 'ok' | 'violation' | 'na'(git repo 아님)."""
    if not (build / ".git").exists():
        return "na", []
    rc, traw = _git(build, "ls-files", "-z")
    tracked = set(_z(traw)) if rc == 0 else set()
    rc, oraw = _git(build, "ls-files", "--others", "--exclude-standard", "-z")
    others = set(_z(oraw)) if rc == 0 else set()

    # 최상위 세그먼트별로 묶는다 — §16 A 는 최상위 항목 단위 규칙이다.
    tops: dict[str, dict] = {}
    for p in tracked | others:
        if not (build / p).exists():
            continue          # 삭제된 tracked 는 올라갈 것이 아니다 (git-listup 과 동일)
        top = p.split("/", 1)[0]
        if top not in FORBIDDEN:
            continue
        e = tops.setdefault(top, {"path": top, "files": 0, "tracked": 0})
        e["files"] += 1
        if p in tracked:
            e["tracked"] += 1
    hits = [tops[k] for k in sorted(tops)]
    return ("violation" if hits else "ok"), hits


def main() -> int:
    filt = sys.argv[1] if len(sys.argv) > 1 else None
    bs = builds(filt)
    if not bs:
        print(f"빌드 없음{': ' + filt if filt else ''}")
        return 0
    print("== 빌드 저장소 경계 (정적 스캔 · 읽기전용 · RULES §16) ==\n")
    violations = 0
    for base, b in bs:
        status, hits = scan(b)
        if status == "na":
            print(f"■ {base}/{b.name}   ⊘ git repo 아님 (add-cto 전 — 올릴 것이 없다)")
            continue
        if status == "ok":
            print(f"■ {base}/{b.name}   ✓ clean")
            continue
        violations += 1
        print(f"■ {base}/{b.name}   ✗ 위반 {len(hits)}건")
        for h in hits:
            mark = f"   [추적중 {h['tracked']}]" if h["tracked"] else ""
            print(f"   ✗ {h['path']:<12} {h['files']:>5} 파일{mark}  — {FORBIDDEN[h['path']]}")
    print()
    if violations:
        print(f"== gitignore: FAIL ✗ ({violations} 빌드 — §16 A 목록이 올라감에 있다) ==")
        print("   고치기: `./run.sh git-listup <name>` 로 확인 후 그 빌드 .gitignore 에 추가")
        print("           (대시보드 노드 모달 Git 상태 탭에서 행 호버 → `→` 클릭도 같은 동작)")
        print("   ★ [추적중] 표시는 .gitignore 로 안 빠진다 — 추적 해제가 따로 필요하고")
        print("     그건 사용자 명시 지시 사안이다 (§1).")
        return 1
    print("== gitignore: ALL CLEAN ✓ ==")
    return 0


if __name__ == "__main__":
    sys.exit(main())
