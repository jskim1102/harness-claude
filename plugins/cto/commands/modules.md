---
description: 모듈 라이브러리 목록을 출력한다. modules/<name>/specs/USAGE.md 존재 = 완성(재사용 가능) 모듈. 분해 때 plan.md ## 3 Library Check 의 reuse 대상을 확인할 때 사용.
---

모듈 라이브러리 스캔 (USAGE.md 존재 = 완성·재사용 가능, 없음 = 빌드 중):

!for d in "$HARNESS_ROOT"/modules/*/; do [ -d "$d" ] || continue; n=$(basename "$d"); if [ -f "$d/specs/USAGE.md" ]; then echo "✅ $n — $(sed -n '2p' "$d/specs/USAGE.md")"; else echo "🚧 $n — 빌드 중 (USAGE.md 없음, 소비 금지)"; fi; done; ls -A "$HARNESS_ROOT"/modules/ >/dev/null 2>&1 && [ -n "$(ls -A "$HARNESS_ROOT"/modules/ 2>/dev/null)" ] || echo "(모듈 없음)"

- plan.md `## 3 Library Check` 가 `reuse:<name>` 로 지정한 모듈만 소비한다.
  해당 `modules/<name>/specs/USAGE.md` 의 사용법/환경/API 를 따라 통합 ckpt 를
  구성하고, spec.md 에서 그 기능들을 `[supplied:modules/<name>]` 로 태그한다.
- 🚧 (USAGE.md 없는) 모듈은 소비 금지 (RULES §7).
