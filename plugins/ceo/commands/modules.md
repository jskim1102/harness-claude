---
description: 모듈 라이브러리 목록을 출력한다. modules/<name>/specs/USAGE.md 존재 = 완성(재사용 가능) 모듈. 1단계 Library Check 때, 또는 사용자가 "모듈 뭐 있어" 물을 때 사용.
---

모듈 라이브러리 스캔 (USAGE.md 존재 = 완성·재사용 가능, 없음 = 빌드 중):

!for d in "$HARNESS_ROOT"/modules/*/; do [ -d "$d" ] || continue; n=$(basename "$d"); if [ -f "$d/specs/USAGE.md" ]; then echo "✅ $n — $(sed -n '2p' "$d/specs/USAGE.md")"; else echo "🚧 $n — 빌드 중 (USAGE.md 없음, 소비 금지)"; fi; done; ls -A "$HARNESS_ROOT"/modules/ >/dev/null 2>&1 && [ -n "$(ls -A "$HARNESS_ROOT"/modules/ 2>/dev/null)" ] || echo "(모듈 없음)"

출력 후:
- ✅ 모듈 = plan.md `## 3 Library Check` 에서 `reuse:<name>` 후보. 상세는
  해당 `modules/<name>/specs/USAGE.md` 를 읽는다.
- 🚧 모듈 = 빌드 중 — 재료로 소비 금지 (RULES §7).
- 비어있으면 "모듈 없음 — `/build-module <brief>` 로 새로 빌드" 안내.
