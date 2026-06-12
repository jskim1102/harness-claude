#!/usr/bin/env python3
"""CTO statusline — 현재 작업 중인 phase:ckpt 를 상시 표시한다.
(plans/harness.md "전체 시스템 특징": CTO tmux 는 현재 phase:ckpt 출력)

Claude Code 의 statusLine command 로 settings.json 에 배선된다 (run.sh
write_role_settings). stdin 으로 세션 JSON 을 받고, stdout 한 줄이
상태줄에 표시된다.

현재 ckpt 판정 = `<빌드dir>/specs/tasks.md` 의 phase→ckpt 트리에서
미완료(`[ ]`) 체크박스를 가진 첫 `### phaseN.ckptM` 헤딩.
- tasks.md 없음           → "분해 전 (specs/tasks.md 없음)"
- 미완료 ckpt 없음         → "전 ckpt 완료"
- 체크박스 집계            → "(done/total)" 진행률 병기

fail-open: 어떤 예외든 빈 줄 대신 안전한 기본 문자열을 낸다.
"""
import json
import os
import re
import sys


def _find_tasks_md(cwd):
    # 빌드 dir 루트의 specs/tasks.md. cwd 가 아무리 깊어도 파일시스템
    # 루트까지 상향 탐색 (6단계 제한 제거 — codex finding #11).
    d = cwd
    while True:
        cand = os.path.join(d, "specs", "tasks.md")
        if os.path.isfile(cand):
            return cand
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _current_ckpt(tasks_path):
    """첫 미완료 ckpt 헤딩과 전체 진행률을 돌려준다."""
    ckpt_re = re.compile(r"^###\s+(phase\d+\.ckpt\d+)\s*(.*)$")
    box_re = re.compile(r"^\s*[-*]\s*\[(✅| |x|X|!)\]")

    sections = []  # (ckpt_id, title, boxes:[bool done])
    cur = None
    with open(tasks_path, encoding="utf-8") as fp:
        for line in fp:
            m = ckpt_re.match(line)
            if m:
                cur = {"id": m.group(1), "title": m.group(2).strip(), "boxes": []}
                sections.append(cur)
                continue
            if cur is not None:
                b = box_re.match(line)
                if b:
                    cur["boxes"].append(b.group(1) in ("x", "X", "✅"))

    total = sum(len(s["boxes"]) for s in sections)
    done = sum(sum(1 for x in s["boxes"] if x) for s in sections)

    for s in sections:
        # 체크박스 없는 ckpt 는 미착수로 간주, 하나라도 [ ] 면 진행 중.
        if not s["boxes"] or not all(s["boxes"]):
            return s["id"], s["title"], done, total
    return None, None, done, total


def main():
    cwd = os.getcwd()
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        cwd = (
            payload.get("workspace", {}).get("current_dir")
            or payload.get("cwd")
            or cwd
        )
    except Exception:
        pass

    role = os.environ.get("HARNESS_ROLE", "cto")
    tasks = _find_tasks_md(cwd)
    if not tasks:
        print(f"[{role}] 분해 전 (specs/tasks.md 없음)")
        return

    try:
        ckpt, title, done, total = _current_ckpt(tasks)
    except Exception:
        print(f"[{role}] tasks.md 파싱 실패")
        return

    prog = f" ({done}/{total})" if total else ""
    if ckpt:
        t = f" — {title}" if title else ""
        print(f"[{role}] 📍 {ckpt}{t}{prog}")
    else:
        print(f"[{role}] ✅ 전 ckpt 완료{prog}")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("[cto] statusline error")
        sys.exit(0)
