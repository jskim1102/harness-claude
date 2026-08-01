#!/usr/bin/env python3
"""CTO statusline — 현재 작업 중인 phase:ckpt 를 상시 표시한다.
(PROCESS.md §6: CTO Orca terminal은 현재 phase:ckpt 출력)

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
import time


def _find_tasks_md(cwd):
    # 빌드 dir 루트의 specs/tasks.md. cwd 가 아무리 깊어도 상향 탐색하되
    # (6단계 제한 제거 — codex finding #11), **REPO 루트에서 멈춘다**
    # (2026-07-27): 무제한이면 빌드 밖 임의의 상위 디렉토리에 있는 남의
    # specs/tasks.md 를 집어 다른 빌드의 진행률을 표시할 수 있다. REPO 를
    # 못 찾는 환경에서는 기존대로 파일시스템 루트까지 간다(폴백).
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = cwd
    while True:
        cand = os.path.join(d, "specs", "tasks.md")
        if os.path.isfile(cand):
            return cand
        if os.path.abspath(d) == repo:
            return None
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def _current_ckpt(tasks_path):
    """첫 미완료 ckpt 헤딩과 전체 진행률을 돌려준다."""
    ckpt_re = re.compile(r"^###\s+(phase\d+\.ckpt\d+)\s*(.*)$")
    # 완료 = [✅] (정본; 레거시 [x]/[X] 도 인식). 블로커 = [❓] (정본; 레거시 [!] 도). 미완 = [ ].
    box_re = re.compile(r"^\s*[-*]\s*\[(✅| |x|X|❓|!)\]")

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


# ── CEO 세션 staleness (하이진 finding #1) ───────────────────────────────
# 오래 안 죽인 CEO Orca 세션 = 맥락 부패. 세션 나이 or RULES 갱신 감지 → 재시작 권고.
CEO_MAX_AGE_HOURS = 12  # 이 시간 넘으면 (밤샘/장기세션) 경고


def _staleness_verdict(created_epoch, rules_mtime_epoch, now_epoch, max_age_hours):
    """CEO 세션 재시작 권고 여부. True = stale.
    - 세션 나이 > max_age_hours (컨텍스트 누적 부패)
    - RULES.md 가 세션 시작 후 수정됨 (새 하드룰이 세션에 미반영)
    순수 함수 — 결정론 테스트 (tests/smoke.sh CEO 라이프사이클 case E).
    """
    if now_epoch - created_epoch > max_age_hours * 3600:
        return True
    if rules_mtime_epoch > created_epoch:
        return True
    return False


def _rules_mtime():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.getmtime(os.path.join(repo, "plugins", "_shared", "RULES.md"))


def _ceo_session_created_epoch():
    """run.sh가 새 CEO Orca tab 생성 때 기록한 epoch. 없으면 fail-open."""
    marker = os.path.expanduser("~/.harness-claude/ceo-session.started")
    try:
        raw = open(marker, encoding="utf-8").read().strip()
        return int(raw)
    except (OSError, TypeError, ValueError):
        return None


def _ceo_statusline():
    """CEO 상태줄: 세션 나이 + staleness 경고. 어떤 예외든 fail-open."""
    created = _ceo_session_created_epoch()
    if created is None:
        print("[ceo] 🟢 harness meta-manager")
        return
    now = time.time()
    age_h = (now - created) / 3600.0
    try:
        rules_mtime = _rules_mtime()
    except Exception:
        rules_mtime = 0
    if _staleness_verdict(created, rules_mtime, now, CEO_MAX_AGE_HOURS):
        reasons = []
        if now - created > CEO_MAX_AGE_HOURS * 3600:
            reasons.append(f"세션 {age_h:.0f}h")
        if rules_mtime > created:
            reasons.append("RULES 갱신됨")
        print(f"[ceo] ⚠ 재시작 권고 ({', '.join(reasons)}) — ./run.sh ceo --fresh")
    else:
        print(f"[ceo] 🟢 session {age_h:.1f}h")


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
    if role.startswith("ceo"):
        _ceo_statusline()
        return
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
