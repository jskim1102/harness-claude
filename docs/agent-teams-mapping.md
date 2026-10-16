# Agent Teams — 우리 설계 매핑

> **이 문서 = "왜 이렇게 설계했나"의 기록 (architecture 모델 + 잠금된 결정의 출처).**
> 운영 정본이 아니다. 현행 정본:
> - 운영 프로세스 = `plugins/_shared/PROCESS.md`
> - 규칙 정본 색인 = `docs/instruction-authority.md`
> - 에이전트별 스킬·도구·파일구조 = 각 `plugins/cto/agents/*.md` + `AGENTS.md`
>
> 옛 스킬맵·파일트리·CEO 메타도구·사용예시·v3 후보 절은 정본에서 drift 가 누적돼
> **2026-06-24 제거**(SHRINK). 그 정보는 위 정본 파일들이 가진다.

이 문서는 Claude Code Agent Teams 공식 기능과 `harness-claude` 의 CEO/CTO
아키텍처가 어떻게 결합되는지, 그리고 결합 관련 의사결정의 출처를 정리한다.

## 두 층 아키텍처

```
사용자
  ↕  (자연어 대화)
CEO (harness Project의 `harness:ceo` Orca tab, focus `./run.sh ceo`)
  ↕  (harness 메시지 채널 — sqlite + harnessd)
CTO lead (build directory Orca Project의 `harness:cto:<name>:lead` tab)
  ↕  (Agent Teams: SendMessage, TaskCreate, mailbox)
  ├── planner    (.claude/agents/planner.md)
  └── reviewer   (.claude/agents/reviewer.md)
  ↕  (same-name harness inbox — SQLite + harnessd)
Codex developer (같은 Orca Project의 `harness:cto:<name>:codex` tab, production code 전담)
```

`claude-project/<name>`과 `modules/<name>` 각각이 Orca Project다. Orca Project
신원은 git repo 경계라 자체 `.git`이 없으면 부모 harness-claude 신원에 묶여
워크트리가 없고 terminal create가 selector_not_found로 죽는다. 그래서 `add-cto`가
빌드 dir에 `.git`이 없을 때 한해 빈 저장소를 자동 init한다(커밋 0으로도 kind=git
등록 성립). `.git` 유무 가드라 최초 add-cto 1회만 돌고 재스폰은 건너뛴다. 자동 생성은
빈 저장소까지이며 commit·push는 여전히 사용자 명시가 있을 때만 한다(RULES §1).

- **CEO ↔ CTO** = 우리 자체 harness (SQLite + 데몬 + Orca terminal input).
- **CTO ↔ Claude sub-agents** = Claude Code 의 native Agent Teams 기능.
- **CTO ↔ Codex developer** = same-name pair 전용 harness inbox + 공유 specs/tasks.md.
  inbox를 읽은 턴은 요약만 하고 사용자 다음 턴 승인 뒤 실행한다.
- CEO 는 Agent Teams 를 쓰지 않는다. CEO 는 사용자 ↔ CTO 의 메타관리만.
- 사용자는 Claude CTO와 Codex TUI tab을 각각 focus한다. lead 는 순수 `claude`
  세션이고(`orca claude-teams` 래퍼는 native split 을 강제 생성해 2026-07-29
  제거), lead tab 은 콕핏 rail(lead 좌 + skill activity/planner/reviewer
  읽기전용 뷰어 3단)로 고정된다. designer 는 독립 `harness:cto:<name>:designer`
  tab (2026-07-29 분리 — specs/2026-07-29-designer-cto-split-design.md). Codex는 별도 tab이다.

## 잠금된 의사결정

| 항목 | 결정 | 출처 |
|---|---|---|
| Q1. sub-agent 자동스폰 트리거 | 사용자가 자연어로 "create a team of X" 직접 입력. CTO 가 의도추론으로 자동 spawn 하지 않음 | 영상 1/2/3 + AWS sample 패턴 |
| Q2. plan approval mode | 활성화 — destructive 작업전 lead 승인 | 공식문서 + 영상 1 |
| Q3. spec 디렉토리 | 프로젝트 root `specs/` 에 spec.md / tasks.md (구 `.claude/specs/<slug>/` 는 폐기 — `planner.md`) | AWS sample → 재설계로 경로 변경 |
| Q4. devil's advocate | 별도 sub-agent 분리 X. reviewer 의 한 단계 ("Devil's Advocate Pass") 로 통합 | AWS sample review-agent + 우리 토큰절약 |
| 메모리 (각 sub-agent) | 비활성화 (memory field 생략). LATER.md 에 기록 | 디버깅 단순화 우선 |
| 도구 권한 | 엄격 allowlist (P1 시작). 필요시 확장 | AWS sample + 우리 결정 |
| 모델 + effort | Claude CEO·CTO lead·designer-cto = Opus 5.5(`claude-opus-5-5`) + effort `max` (run.sh settings 템플릿 기본값), Claude teammate(planner/reviewer) = 동일 (프론트매터). 사용자는 attach 후 `/model`·`/effort` 로 세션별 변경 가능. Codex 모델은 사용자 Codex config 사용 | 2026-10-16 사용자 지시 (이전: CTO high / teammate xhigh) |
| teammateMode | `in-process` (순수 `claude` lead + 콕핏 rail 3단: skill/planner/reviewer 읽기전용 뷰어. designer 는 독립 세션. `orca claude-teams` 래퍼는 native split 강제라 제거) | 2026-07-23 spawn-only 전환 → 2026-07-29 콕핏 rail (specs/2026-07-29-cto-cockpit-rail-design.md) |
| 사용자 시각검증 게이트 | **게이트3 = 사용자 브라우저 실동작 PASS 필수** (RULE A). agent live-app/browse 는 기계적 자체검증일 뿐 게이트3 대체 X, CTO 자가 선언 불가 | 2026-06-24 RULE A 박음 (이전 "게이트 X 자율판단"은 폐기) |
| 슬라이스 크기 | 시간상한 X. 원칙만 ("사용자가 화면에서 새 동작 1개 수행 최소단위") | 사용자 결정 |

## 활동 단위 표 (one team handles all activities)

| 활동 | active teammate | trigger (entry) | trigger (exit) |
|---|---|---|---|
| **Plan** | planner | 사용자 새 요청 또는 plan 수정 요청 | spec.md / tasks.md 완성 + 사용자 컨펌 |
| **Design** | 독립 designer-cto 세션 (inbox 발주; planner 휴면 — design-max 는 사용자 직접 대화) | Plan 완료 또는 UI 수정 요청 | DESIGN.md + 시안 + 사용자 브라우저 검수 (design-max 시 Claude Design) + 구현 계약 |
| **Build** | 외부 Codex developer + Claude reviewer(on-demand) | 승인 디자인/다음 ckpt 시작 | ckpt 완료 + reviewer PASS + 사용자 시각검증 |

핵심: Claude Agent Team은 plan/design/review를 유지하고, 별도 Codex가 모든
production code를 쓴다. 둘은 같은 `specs/tasks.md`를 공유하며 활동마다 재생성하지 않는다.

## 갭 해결 출처

| 갭 | 해결 | 출처 |
|---|---|---|
| A. CTO 자동 spawn 트리거 | 사용자 자연어 입력 — 자동스폰 X | 영상 1/2/3 + 사용자 결정 |
| B. one team + 활동전환 | 한 team 이 모든 활동 처리. role tag 로 분배 | AWS sample fullstack-agent.md |
| C. CTO role.md + agent body 충돌 | 별개 컨텍스트. role.md = lead system prompt. agent body = teammate system prompt | 공식문서 sub-agents |
| D. teammate UX | `in-process` + 콕핏 rail 3단 = lead 좌측, 우측에 skill activity + planner/reviewer 읽기전용 전사 뷰어 (개입은 lead 에서; designer 는 독립 탭) | 2026-07-23 사용자 결정 → 2026-07-29 목업 확정·designer 분리 |
| E. shared task list 형식 | `[role] verb what \| files \| acceptance. Run: cmd`. 3 hook 으로 강제 | AWS sample + 우리 적응 |
| F. Claude 버전 | 사용자 v2.1.160 (>= 2.1.32) ✓ | 직접확인 |
| G. minimal test | AWS sample 패턴 적용. 사용자가 CTO 에 자연어 요청 | 우리 결정 |

## 참조 출처

- 공식 문서: <https://code.claude.com/docs/en/agent-teams>
- 공식 문서 (KO): <https://code.claude.com/docs/ko/agent-teams>
- 공식 sub-agents: <https://code.claude.com/docs/en/sub-agents>
- 공식 hooks: <https://code.claude.com/docs/en/hooks>
- 공식 skills: <https://code.claude.com/docs/en/skills>
- 공식 settings: <https://code.claude.com/docs/en/settings>
- AWS Sample (reference): <https://github.com/aws-samples/sample-claude-code-agent-team>
  - 클론 위치: `.references/aws-sample/`
- 영상 1: Nate Herk, "How to Build Claude Agent Teams Better Than 99% of People"
- 영상 2: Eric Tech, "TMUX + Claude Agent Teams = Game Changer"
- 영상 3: Hodu's AI Analysis Lab, "Claude Code Agent Teams 완벽 가이드"
- 영상 4 (짐코딩): "클로드 코드 Agent Teams 완벽 정리 | Subagent와 차이점"
- 영상 5 (Matt Pocock): "코드는 비싸지 않다" (펀더멘털 + grill-me 소개)
- 영상 6 (메이커 에반): "구글이 사양 공개한 design.md 정체"
