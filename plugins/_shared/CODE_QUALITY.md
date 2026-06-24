# Code Quality Contract

위치: `plugins/_shared/` (RULES.md/PROCESS.md 옆). 이 문서는 "좋은 코드"의
짧은 정본이다. 상세 절차는 각 agent.md 의 완료/리뷰 게이트가 강제한다.

A change is acceptable only when it improves or preserves code health.

1. Correctness
- 요청된 동작을 해결하고, 명시된 edge case 와 명백한 실패 경로를 다룬다.
- 관련 없는 동작을 조용히 바꾸지 않는다.

2. Simplicity
- 현재 요구사항을 해결하는 최소 변경을 선호한다.
- speculative abstraction, unused generality, future-only API 를 만들지 않는다.

3. Maintainability
- 이름은 의도를 드러내고, 제어흐름은 빠르게 이해 가능해야 한다.
- 주석은 obvious what 이 아니라 why 를 설명한다.

4. Tests
- 변경에 맞는 수준의 테스트를 추가/수정한다.
- 구현이 깨지면 실패하는 의미 있는 검증이어야 한다.

5. Integration
- 기존 module boundary, data flow, local pattern 을 따른다.
- behavior 변경 시 docs/config/schema/migration 도 함께 맞춘다.

6. Risk
- security, auth, data loss, concurrency, performance, deploy risk 를 만졌으면
  mitigation 또는 CTO/user escalation 이 필요하다.

7. Rollback
- 변경은 review/revert 가능한 크기여야 한다.
- migration/config/deploy 변경은 compatibility 또는 rollback story 를 가진다.
