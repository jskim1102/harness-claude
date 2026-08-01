# Hermes / OpenClaw 자동 스킬 연동 결론

작성일: 2026-07-15

## 결론

`harness-claude`를 Hermes로 이식하거나 Hermes가 현재 하네스를 대체하게 만들 필요는
없다. 현재 CEO, Claude CTO와 Agent Team, 별도 Codex developer, SQLite 메시지큐,
대시보드는 실행 계층으로 그대로 유지한다.

Hermes를 도입한다면 새로운 CTO나 LLM이 아니라 **자동 스킬 후보를 만드는 학습
사이드카**로 둔다. Hermes는 Claude나 Codex 같은 모델이 아니라 이 모델들을 사용해
도구, 메모리, 스킬을 운용하는 에이전트 런타임이다.

권장 판단은 다음과 같다.

- 하네스를 Hermes로 이식: 비추천
- Hermes가 CEO/CTO/Codex 실행을 대체: 비추천
- 기존 하네스 옆에 학습 사이드카로 연동: 조건부 추천
- 현재의 `harness-memory.md`와 완료 요약만 Hermes에 전달: 실익이 작음
- 학습 에피소드 수집, 스킬 후보 staging, 대시보드 승인까지 구성: 실익이 큼
- 운영 안전성을 우선한 자동 스킬 제안 엔진: OpenClaw가 우세
- 스킬을 적극적으로 작성, patch, 정리하는 학습 에이전트: Hermes가 우세

가장 합리적인 순서는 제품 종속성이 없는
`LearningEpisode -> SkillCandidateBackend` 경계를 먼저 만들고, Hermes를 첫 PoC
backend로 연결한 뒤 같은 에피소드를 OpenClaw와 비교하는 것이다.

## 권장 아키텍처

```text
현재 실행 계층 — 변경 없음

사용자
  <-> CEO
  <-> SQLite 메시지큐
  <-> Claude CTO + planner/designer/reviewer
  <-> same-name inbox
  <-> Codex developer
          |
          | segment/build 완료
          v
학습 에피소드 수집·비식별화
          |
          | 재발성 또는 명시적 사용자 교정 gate
          v
Hermes 학습 전용 profile
          |
          | /learn + skill_manage
          v
Pending skill candidate
          |
          v
기존 Dashboard의 Skill Lab
          |
          | diff / 근거 / 수정 요청 / 승인 / 거절
          v
plugins/cto/skills/<skill>/
          |
          | validator + forward test + doctor + smoke
          v
기존 symlink 방식으로 CTO에 배포
```

Hermes를 harness role allowlist나 CEO/CTO inbox peer로 추가하지 않는다. 조직 역할이
아니라 완료된 실행 증거를 소비하는 별도 학습 서비스로 취급한다.

## 연동에 필요한 핵심 구성요소

### 1. Learning Episode

현재 `hooks/project_memory.py`가 수집하는 것은 다음과 같은 기계적 사실이다.

- 실제로 실행한 build/test/lint 명령
- 런타임 버전
- 누락된 모듈이나 환경변수 이름
- 반복해서 접근한 파일

반면 임의의 stdout/stderr, diff, 실패 경로는 의도적으로 수집하지 않는다. Codex도
현재 완료 시 변경 파일, 테스트, 기존 패턴, 위험, rollback 정도만 보고한다. 이
정보만 Hermes에 전달하면 실제 절차를 학습하지 못하고 회고 문서를 생성하는 수준에
머물 가능성이 크다.

학습 에피소드는 최소한 다음 필드를 가져야 한다.

- 작업 목표와 이 절차를 다시 사용해야 하는 trigger
- 중요한 precondition
- 실패한 접근과 관찰 가능한 결과 요약
- 최종 성공 절차
- 테스트 및 검증 증거
- 사용자 또는 reviewer의 교정
- 적용되었거나 누락된 기존 스킬
- 관련 파일과 spec 경로
- 비밀정보 제거 결과

원시 chain-of-thought나 전체 터미널 로그는 저장하지 않는다. 도구 입력의 안전한
요약, exit status, 결과 digest, 변경 파일, 테스트 결과처럼 관찰 가능한 증거만
보존한다.

초기 구현에서는 Claude 쪽은 별도의 hook으로 사건을 수집하고, Codex 쪽은 기존
Completion Evidence에 `Failed attempts`, `Winning procedure`, `User correction`을
추가해 segment 종료 시 구조화된 episode를 내보내는 방법이 가장 안전하다. Codex
내부 session 파일을 직접 파싱하는 방식은 포맷 의존성이 크므로 1차 PoC에서는 피한다.

### 2. 재발성 gate

기존 `harness-self-improve`의 원칙을 유지한다. 아래 조건 중 하나를 만족할 때만
스킬 후보 생성을 요청한다.

- 같은 문제나 절차가 둘 이상의 surface에서 재발
- 사용자가 명시적으로 잘못된 접근을 교정
- 다음 작업에서 여러 tool round-trip을 줄일 안정적인 절차 발견
- 기존 스킬의 누락이나 잘못된 단계가 반복해서 드러남

일회성 환경 장애, 단순 선호, 검증되지 않은 부정적 주장, 프로젝트 하나에만 해당하는
우연한 해결책은 후보에서 제외한다. authority 파일은 계속 사람이 승인한다.

### 3. Hermes 학습 profile

Hermes에는 하네스 전용 profile을 만든다.

- 예시 이름: `harness-learning`
- bundled skills 없이 시작
- 허용 도구: `skill_manage`와 읽기 전용 episode/catalog 도구
- `skills.write_approval: true`
- `skills.guard_agent_created: true`
- 초기에는 terminal, web, memory, delegation, curator 비활성
- 학습 모델은 Claude 또는 Codex 중 선택

하네스 close-out이 gate를 통과한 episode에 대해 Hermes `/learn` turn을 시작한다.
Hermes의 네이티브 background review가 외부 하네스 실행을 자동으로 볼 수 있는 것은
아니다. 따라서 여기서 말하는 자동화는 다음 파이프라인이다.

```text
harness close-out
  -> episode gate
  -> Hermes /learn 자동 호출
  -> skill_manage pending write
  -> 사람의 승인
```

`plugins/cto/skills`를 Hermes의 writable external skill directory로 직접 연결하면 안
된다. Hermes의 external directory는 쓰기 보호 경계가 아니기 때문이다. 현재 스킬은
읽기 전용 catalog/MCP로 보여주고, 생성물은 별도 staging profile에만 기록한다.

### 4. Dashboard Skill Lab

기존 대시보드에 다음 정보를 보여주는 `Skill Lab`을 추가한다.

- 후보 스킬과 상태
- 근거 episode와 재발 횟수
- 기존 스킬 대비 diff
- 생성된 script/reference/template
- 보안 검사와 validation 결과
- 승인, 수정 요청, 거절, quarantine

Mutation은 현재 `DASH_TOKEN` gate를 그대로 사용한다. 승인 후에만 후보를 하네스
형식으로 정규화하여 `plugins/cto/skills/<name>/`에 반영한다.

### 5. 승격과 검증

Hermes가 만든 Agentskills 호환 문서를 그대로 배포하지 않는다. 하네스 고유의 role,
authority, trigger, `${CLAUDE_SKILL_DIR}`, 금지 명령과 검증 계약에 맞게 정규화한다.

승격 조건은 다음과 같다.

1. 근거 episode와 재발성 확인
2. 기존 스킬을 patch할지 새 스킬을 만들지 확인
3. frontmatter와 참조 무결성 검사
4. support script의 결정론적 테스트
5. 과거 episode를 이용한 forward test
6. 사용자 또는 CTO 승인
7. `./run.sh doctor`
8. `./run.sh smoke`

승인된 스킬은 현재 `run.sh`의 symlink 배포 경로를 그대로 사용하므로 CTO 실행 구조를
바꿀 필요가 없다.

## Hermes를 붙였을 때의 실익

충분한 episode가 제공된다는 전제에서는 다음 이점이 있다.

- 현재 회고가 찾아낸 승격 후보를 완성된 `SKILL.md`와 지원 파일로 작성
- 무조건 새 스킬을 만들지 않고 기존 스킬을 patch
- 실패, 회복, 검증의 순서를 procedural memory로 보존
- Claude/Codex 중 별도의 학습 모델을 선택
- 반복 업무에서 탐색과 tool round-trip 감소
- 현재 CEO, CTO, Codex TUI, 대시보드, 승인 경계를 유지

비용과 위험도 존재한다.

- 실질적인 개발 작업의 대부분은 Hermes 설치가 아니라 episode collector와 redaction
- 추가 모델 호출 비용과 transcript data-handling 검토
- 잘못된 일반화와 skill bloat
- Hermes profile과 pending store를 운영해야 하는 부담
- Hermes 스킬 형식과 하네스 authority 계약 사이의 정규화 필요

따라서 Hermes 연동 자체가 가치인 것이 아니라, **좋은 실행 증거를 안전하게 반복
가능한 절차로 변환하는 파이프라인**이 가치다.

## Hermes를 실행 계층으로 넣지 않는 이유

Hermes는 Codex App Server를 감싸 terminal, file edit, sandbox, MCP 실행을 Codex에
맡기면서 세션, 메모리, 스킬 검토를 유지할 수 있다. 이 방식이면 Hermes가 Codex tool
event를 자기 transcript 형식으로 보고 네이티브 background review를 수행할 수 있다.

하지만 현재 하네스에서는 다음 문제가 생긴다.

- 별도 Codex TUI와 다음-turn 사용자 승인 계약 변경
- Claude Agent Teams와 Codex의 역할 경계 변경
- 권한과 sandbox 계층 중복
- Hermes가 Codex 절반만 감싸면 CTO의 계획·리뷰 문맥은 여전히 누락
- 양쪽을 모두 감싸면 사실상 현재 실행 하네스를 교체하는 대규모 이식

자동 스킬 하나를 얻기 위해 이 비용을 지불하는 것은 합리적이지 않다.

## OpenClaw 비교

| 기준 | Hermes | OpenClaw |
|---|---|---|
| 외부 하네스 관찰 | 별도 episode adapter 필요 | 별도 episode adapter 필요 |
| 자료에서 스킬 생성 | `/learn` + `skill_manage` | `/learn` + Skill Workshop |
| 자동 학습 범위 | 자기 런타임의 tool-heavy turn | 자기 Gateway의 정상 foreground turn |
| 활성 스킬 보호 | `write_approval` 설정 필요 | background reviewer는 활성 스킬 적용 불가 |
| 후보 lifecycle | pending diff/approve/reject | proposal, revise, stale, quarantine, apply |
| update 안전성 | 별도 승격 계층 필요 | hash binding, scanner, rollback 내장 |
| 스킬 개선 성향 | 적극적 patch와 LLM 기반 정리에 강함 | 보수적 후보 제안과 통제에 강함 |
| Codex 연동 | Codex App Server runtime | 공식 Codex plugin, thread 감독 가능 |
| 현재 하네스와의 적합성 | 학습 저작 backend | 운영 거버넌스 backend |

두 제품 모두 현재 Claude/Codex 실행을 밖에서 자동으로 관찰하지 않는다. 각자의
네이티브 self-learning은 각자 런타임 안에서 일어난 turn을 대상으로 한다. 따라서
Learning Episode 계층은 어느 제품을 선택해도 필요하다.

OpenClaw의 강점은 Skill Workshop의 proposal-first 구조다. 생성과 수정은 활성
`SKILL.md`를 건드리지 않고, 적용 시 hash stale 검사, 보안 재검사, rollback,
quarantine을 제공한다. 기존 대시보드에 자동 스킬 승인 기능을 넣는 목적만 보면
OpenClaw가 더 안전한 모델이다.

Hermes의 강점은 skill authoring과 자기개선이다. 기존 스킬 patch, support file 생성,
별도 학습 모델 선택, 장기적인 skill curation을 적극적으로 수행하는 학습 에이전트를
원한다면 Hermes가 더 맞다.

OpenClaw의 Skill Workshop은 현재 공식 문서에서 `Status: proposal`로 표시되어 있으므로
실제 도입 전 버전 안정성과 API 변경 가능성을 확인해야 한다.

## 권장 PoC

1. 제품 중립적인 `LearningEpisode` schema와 redaction부터 구현한다.
2. 기존 authority promotion gate를 유지한다.
3. Hermes를 첫 `SkillCandidateBackend`로 연결한다.
4. 10~20개 완료 segment 동안 canonical skill에는 쓰지 않고 후보만 생성한다.
5. 다음 지표를 기록한다.
   - 큰 수정 없이 승인 가능한 후보 비율
   - 기존 스킬 patch 대 새 스킬 생성 비율
   - 승인된 스킬의 실제 재사용 횟수
   - 재사용 시 줄어든 tool call 또는 실패 횟수
   - 잘못된 일반화, 보안, authority 위반 건수
6. 같은 episode corpus를 OpenClaw에 넣어 후보 품질과 운영 편의성을 비교한다.
7. 결과가 유의미할 때만 Dashboard Skill Lab과 자동 close-out 호출을 정식화한다.

## 참고 자료

### 현재 하네스

- `docs/agent-teams-mapping.md`
- `hooks/project_memory.py`
- `plugins/cto/skills/harness-self-improve/SKILL.md`
- `plugins/cto/skills/harness-remember/SKILL.md`
- `plugins/codex-cto/role.md`
- `dashboard/backend/main.py`
- `run.sh`

### 공식 문서

- Hermes Skills: <https://hermes-agent.nousresearch.com/docs/user-guide/features/skills/>
- Hermes Codex App-Server Runtime: <https://hermes-agent.nousresearch.com/docs/user-guide/features/codex-app-server-runtime>
- Hermes Providers: <https://hermes-agent.nousresearch.com/docs/integrations/providers>
- OpenClaw Self-learning: <https://docs.openclaw.ai/tools/self-learning>
- OpenClaw Skill Workshop: <https://docs.openclaw.ai/tools/skill-workshop>
- OpenClaw Codex Harness: <https://docs.openclaw.ai/plugins/codex-harness>
- OpenClaw Trajectory Bundles: <https://docs.openclaw.ai/tools/trajectory>
