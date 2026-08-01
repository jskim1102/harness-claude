#!/usr/bin/env python3
"""Orca 상태파일의 고아 워크스페이스 항목(UI 의 "Unknown")을 정리한다.

왜 필요한가 (2026-07-23): `orca project setup-delete` 로 프로젝트 등록을 지워도
`worktreeMeta`·`workspaceSession.tabsByWorktree` 에 그 repo 를 가리키던 항목이
남는다. Orca UI 는 그걸 이름 없는 "Unknown" 프로젝트로 그리고, repo 가 이미
없어서 CLI(`orca worktree rm`)는 `repo_not_found` 로 거부하며 UI 우클릭 메뉴도
뜨지 않는다 → 어느 경로로도 지울 수 없는 유령이 된다.

**Orca 를 완전히 종료한 뒤 실행하라.** 실행 중이면 런타임이 메모리 상태로 파일을
다시 덮어써 정리가 무효가 된다 (그래서 프로세스 검사에서 멈춘다).

    python3 scripts/orca-prune-ghosts.py            # 무엇을 지울지만 출력
    python3 scripts/orca-prune-ghosts.py --apply    # 실제 정리 (백업 후)

판정 기준은 하나뿐이다: 키의 repo id 가 `repos` 에 없으면 고아. 살아있는 repo 를
가리키는 항목은 건드리지 않는다.

2026-07-28 확장 — **부활 버그 수정.** 이전 버전은 `worktreeMeta` 와
`workspaceSession.tabsByWorktree` 두 곳만 지웠는데, Orca 는 같은 repo id 를
`unifiedTabs`·`tabGroups`·`activeTabIdByWorktree`·`activeTabTypeByWorktree`·
`activeFileIdByWorktree`·`activeBrowserTabIdByWorktree`·`lastVisitedAtByWorktreeId`
등 여러 컬렉션에 함께 기록한다. 두 곳만 지우고 재기동하면 런타임이 **남은
컬렉션을 보고 worktreeMeta 를 재생성**해 Unknown 이 되살아났다(실측: --apply
성공 22:50 → 재기동 후 22:59 파일에 부활). 그래서 이제 하드코딩한 컬렉션 목록이
아니라 **`<repo-uuid>::` 형식 키를 쓰는 모든 dict 를 재귀 탐색**해 고아를 제거하고,
값 쪽에 박힌 고아 ptyId(`terminalLayoutsByTabId`)까지 함께 거둔다.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

DATA = Path.home() / ".config/orca/profiles/local-default/orca-data.json"
# 워크스페이스 스코프 키 형식: "<repo-uuid>::<절대경로>". UUID 를 앵커로 삼아야
# `global-floating-terminal` 같은 특수 키를 고아로 오판하지 않는다.
#
# ★경로(`::/`)까지 앵커에 포함해야 한다 (2026-07-31 실측). uuid 뒤 `::` 만 보면
# Orca 의 **paneKey `<tabId>::<leafId>`** 가 같은 모양이라 걸려든다 — prefix 가
# repo id 가 아니니 live 목록에 있을 리 없고, 결과적으로 **살아있는 pane** 이
# 매번 "값 참조 고아" 로 지목됐다 (실측: 구동 중인 CEO 탭의
# mobileClientTabSelectionsByDeviceId…activeTabId). 부작용 둘 —
# (a) `--apply` 가 살아있는 참조를 지운다, (b) pane 이 하나라도 있으면 "정리할
# 고아 없음" 이 절대 안 나와 `./run.sh prune-ghosts` 의 VERDICT: CLEAN 이
# 도달 불가였다. 워크스페이스 스코프 참조는 항상 절대경로가 뒤따른다
# (worktreeId `<repo>::<path>`, ptyId `<repo>::<path>@@<hash>`).
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}::/"
)


def orca_running() -> bool:
    """orca-data.json 을 되덮을 수 있는 **serve 런타임**이 살아있는가.

    2026-07-28 재작성: 이전의 pgrep 문자열 판정은 두 방향으로 다 틀렸다 —
    (a) 오탐: harnessd 가 Orca 다운 중 CLI 폴백으로 띄우는 순간성
        `orca-linux.AppImage -e ...` 호출과, 판정 문자열을 cmdline 에 담은
        셸 자신까지 "실행 중" 으로 읽어 정리를 거부했다 (실측).
    (b) 미탐 여지: 파일을 덮는 주체는 serve 런타임뿐인데 무관 프로세스를 셌다.
    정본 판정 = 런타임 유닉스 소켓 접속 시도. 붙으면 실행 중, 아니면 아님.
    """
    meta_path = Path.home() / ".config/orca/orca-runtime.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text())
        endpoint = next(
            t["endpoint"] for t in meta.get("transports", [])
            if t.get("kind") in ("unix", "named-pipe") and t.get("endpoint")
        )
    except (ValueError, StopIteration, KeyError):
        return False
    import socket
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(2.0)
    try:
        s.connect(endpoint)
        return True
    except OSError:
        return False
    finally:
        s.close()


def scoped_dicts(node, path="root"):
    """`<uuid>::` 키를 하나라도 쓰는 dict 를 전부 찾아 (경로, dict) 로 내놓는다.

    컬렉션 이름을 하드코딩하면 Orca 가 새 컬렉션을 추가할 때마다 유령이 부활한다
    (2026-07-28 실측). 구조를 재귀로 훑어 형식만 보고 판정한다.
    """
    if isinstance(node, dict):
        if any(isinstance(k, str) and UUID_RE.match(k) for k in node):
            yield path, node
        for k, v in node.items():
            yield from scoped_dicts(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from scoped_dicts(v, f"{path}[{i}]")


def orphan_values(node, live: set, path="root", out=None):
    """값 쪽에 박힌 고아 참조(예: terminalLayoutsByTabId 의 ptyId)를 거둔다.

    키가 아니라 값이므로 위 스코프 스윕이 못 잡는다. 이 잔재가 남으면 런타임이
    그걸 근거로 worktreeMeta 를 되살린다.
    """
    if out is None:
        out = []
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if (isinstance(v, str) and UUID_RE.match(v)
                    and v.split("::", 1)[0] not in live):
                out.append((node, k, f"{path}.{k}", v))
            else:
                orphan_values(v, live, f"{path}.{k}", out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            orphan_values(v, live, f"{path}[{i}]", out)
    return out


def dead_path_repos(data: dict) -> list[dict]:
    """경로가 사라진 repo 행. delete-cto 는 빌드 dir 만 지우고 Orca 등록은 남긴다
    (구동 중 외부 삭제가 지울 수 없는 유령을 만들기 때문) — 그 잔재를 여기서 거둔다."""
    from pathlib import Path as _P

    return [r for r in data.get("repos", []) if r.get("path") and not _P(r["path"]).is_dir()]


def drop_repos(data: dict, repos: list[dict]) -> None:
    ids = {r["id"] for r in repos}
    data["repos"] = [r for r in data.get("repos", []) if r["id"] not in ids]
    data["projects"] = [
        p for p in data.get("projects", []) if not set(p.get("sourceRepoIds") or []) <= ids
    ]
    data["projectHostSetups"] = [
        s for s in data.get("projectHostSetups", []) if s.get("repoId") not in ids
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 정리 (기본은 미리보기)")
    args = ap.parse_args()

    if not DATA.exists():
        print(f"error: 상태파일 없음: {DATA}", file=sys.stderr)
        return 1
    if args.apply and orca_running():
        print("error: Orca 가 실행 중이다 — 종료 후 다시 실행하라.", file=sys.stderr)
        print("       (실행 중 편집하면 런타임이 메모리 상태로 덮어써 무효가 된다)", file=sys.stderr)
        return 2

    data = json.loads(DATA.read_text())

    # 1) 경로가 사라진 등록부터 거둔다 — 그래야 그 항목들이 아래 고아 판정에 걸린다.
    dead = dead_path_repos(data)
    if dead:
        print(f"경로 사라진 프로젝트 {len(dead)}개:")
        for r in dead:
            print(f"  - {r.get('displayName')}  {r['path']}")
        if args.apply:
            drop_repos(data, dead)
        print()

    live = {r["id"] for r in data.get("repos", [])} - {r["id"] for r in dead}
    print(f"살아있는 repo {len(live)}개: {', '.join(sorted(i[:8] for i in live)) or '(없음)'}\n")

    total = len(dead)
    for name, coll in list(scoped_dicts(data)):
        orphans = [
            k for k in coll
            if isinstance(k, str) and UUID_RE.match(k) and k.split("::", 1)[0] not in live
        ]
        if not orphans:
            continue
        print(f"{name}: {len(coll)}개 중 고아 {len(orphans)}개")
        for k in orphans:
            print(f"  - {k.split('::', 1)[1]}")
        if args.apply:
            for k in orphans:
                del coll[k]
        total += len(orphans)

    # 값 쪽 고아 참조 — 남기면 런타임이 이걸 보고 worktreeMeta 를 되살린다.
    vals = orphan_values(data, live)
    if vals:
        print(f"값 참조 고아 {len(vals)}개")
        for _holder, _k, path, v in vals:
            print(f"  - {path} → {v.split('::', 1)[1]}")
        if args.apply:
            for holder, k, _path, _v in vals:
                del holder[k]
        total += len(vals)

    if not total:
        print("\n정리할 고아 없음.")
        return 0
    if not args.apply:
        print(f"\n미리보기 — 총 {total}개. 실제 정리는 Orca 종료 후 `--apply`.")
        return 0

    backup = DATA.with_suffix(".json.prune-bak")
    shutil.copy2(DATA, backup)
    DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print(f"\n{total}개 제거. 백업: {backup}")
    print("Orca 를 다시 실행하면 Unknown 이 사라진다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
