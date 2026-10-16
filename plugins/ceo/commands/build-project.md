---
description: 새 프로젝트 빌드 폴더 생성 — 빈 폴더만 만든다 (계획·brainstorm·plan.md 는 CTO 탭의 몫, 2026-10-15). Usage: /build-project <name>
argument-hint: <name>
---

# /build-project <name>

빈 폴더 `claude-project/<name>/` 하나를 만든다. **그게 전부다.** 만들고 싶은 것을
듣고 정리하는 일(축2·축3, Library Check, plan.md 작성·점검)은 CTO 가
계획 단계에 한다 (`plugins/cto/skills/harness-plan`, RULES §19).

!name='$0'; root="${HARNESS_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null)}"; [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || { echo "error: name must be kebab-case (lowercase, digits, hyphens). Usage: /build-project <name>"; exit 1; }; [[ "$name" != "ceo" ]] || { echo "error: 'ceo' 는 CEO 작업공간"; exit 1; }; [[ -n "$root" && -d "$root/claude-project" ]] || { echo "error: HARNESS_ROOT 미확인 — ./run.sh ceo 로 재기동"; exit 1; }; for b in claude-project modules; do [[ -e "$root/$b/$name" ]] && { echo "error: $b/$name 이미 존재 — 기존 빌드면 ./run.sh add-cto $name, 새 빌드면 다른 이름"; exit 1; }; done; mkdir -p "$root/claude-project/$name" && echo "created: claude-project/$name/ (빈 폴더 — 계획은 CTO 탭에서)" && printf '다음 — 새 터미널에서:\n  ./run.sh add-cto %s        # 계획 단계로 기동 (plan.md 없음 = CTO 가 brief 부터)\n  ./run.sh attach-cto %s     # /model · /effort 설정 → 첫 메시지 = 만들고 싶은 것\n' "$name" "$name"

## CEO 가 하는 것 / 하지 않는 것

- 위 출력을 사용자에게 그대로 보여준다. 끝.
- **하지 않는다**: 만들고 싶은 것 묻기, 축2·축3 추론, Library Check, plan.md 작성,
  이름 제안 대화. 사용자가 이름 없이 "프로젝트 만들어" 라고 하면 kebab-case 이름
  하나만 확인해 이 커맨드를 다시 치고, 만들고 싶은 것은 CTO 탭에서 말하라고 안내한다.
- "기존 프로젝트 늘리기" 는 이 커맨드가 아니다 — 그 프로젝트의 CTO 탭에서 직접.
- `add-cto`·`attach-cto` 를 CEO 가 실행하지 않는다 (사용자가 새 터미널에서).

ARGUMENTS: $ARGUMENTS
