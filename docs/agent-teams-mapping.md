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
CEO (현재 셸, claude 직결)
  ↕  (harness 메시지 채널 — sqlite + harnessd)
CTO (tmux 세션, claude --dangerously-skip-permissions, Agent Teams team-lead)
  ↕  (Agent Teams: SendMessage, TaskCreate, mailbox)
  ├── planner    (.claude/agents/planner.md)
  ├── designer   (.claude/agents/designer.md)
  ├── developer  (.claude/agents/developer.md)
  └── reviewer   (.claude/agents/reviewer.md)
```

- **CEO ↔ CTO** = 우리 자체 harness (SQLite + 데몬 + tmux send-keys).
- **CTO ↔ sub-agents** = Claude Code 의 native Agent Teams 기능.
- CEO 는 Agent Teams 를 쓰지 않는다. CEO 는 사용자 ↔ CTO 의 메타관리만.
- 사용자는 **CTO 와만 직접 대화**. sub-agent 들은 invisible
  (`teammateMode: in-process`).

## 잠금된 의사결정

| 항목 | 결정 | 출처 |
|---|---|---|
| Q1. sub-agent 자동스폰 트리거 | 사용자가 자연어로 "create a team of X" 직접 입력. CTO 가 의도추론으로 자동 spawn 하지 않음 | 영상 1/2/3 + AWS sample 패턴 |
| Q2. plan approval mode | 활성화 — destructive 작업전 lead 승인 | 공식문서 + 영상 1 |
| Q3. spec 디렉토리 | 프로젝트 root `specs/` 에 spec.md / tasks.md (구 `.claude/specs/<slug>/` 는 폐기 — `planner.md`) | AWS sample → 재설계로 경로 변경 |
| Q4. devil's advocate | 별도 sub-agent 분리 X. reviewer 의 한 단계 ("Devil's Advocate Pass") 로 통합 | AWS sample review-agent + 우리 토큰절약 |
| 메모리 (각 sub-agent) | 비활성화 (memory field 생략). LATER.md 에 기록 | 디버깅 단순화 우선 |
| 도구 권한 | 엄격 allowlist (P1 시작). 필요시 확장 | AWS sample + 우리 결정 |
| 모델 + effort | opus 4.8. **CTO=high**(오케스트레이션) / teammate 4종=xhigh(실작업) | 2026-06-24 — CTO 조율은 xhigh 불필요(지연만), teammate 깊이 유지 |
| teammateMode | in-process (사용자가 CTO 만 봄) | Q1 = "사용자 CTO 와만 대화" |
| 사용자 시각검증 게이트 | **게이트3 = 사용자 브라우저 실동작 PASS 필수** (RULE A). agent live-app/browse 는 기계적 자체검증일 뿐 게이트3 대체 X, CTO 자가 선언 불가 | 2026-06-24 RULE A 박음 (이전 "게이트 X 자율판단"은 폐기) |
| 슬라이스 크기 | 시간상한 X. 원칙만 ("사용자가 화면에서 새 동작 1개 수행 최소단위") | 사용자 결정 |

## 활동 단위 표 (one team handles all activities)

| 활동 | active teammate | trigger (entry) | trigger (exit) |
|---|---|---|---|
| **Plan** | planner | 사용자 새 요청 또는 plan 수정 요청 | spec.md / tasks.md 완성 + 사용자 컨펌 |
| **Design** | designer (lead); planner 휴면(필요 시 CTO 가 깨워 revise) | Plan 완료 또는 UI 수정 요청 | design.md + DESIGN.md + HTML/CSS 완성 + 사용자 컨펌 |
| **Build** | developer (lead) + reviewer (on-demand); planner 휴면(필요 시 CTO 가 깨워 revise) | Design 완료 또는 다음 ckpt 시작 | ckpt 완료 + reviewer PASS + 사용자 시각검증 |

핵심: **하나의 Agent Team 이 전체 workflow 를 처리**. 활동마다 team 재
생성 X. 활동전환 = phase, 같은 team 안에서 일부 teammate 가 메인 / 일부
관찰. AWS sample 의 Plan → Build → Review 루프 패턴.

## 갭 해결 출처

| 갭 | 해결 | 출처 |
|---|---|---|
| A. CTO 자동 spawn 트리거 | 사용자 자연어 입력 — 자동스폰 X | 영상 1/2/3 + 사용자 결정 |
| B. one team + 활동전환 | 한 team 이 모든 활동 처리. role tag 로 분배 | AWS sample fullstack-agent.md |
| C. CTO role.md + agent body 충돌 | 별개 컨텍스트. role.md = lead system prompt. agent body = teammate system prompt | 공식문서 sub-agents |
| D. in-process UX | Shift+Down cycle. 사용자가 CTO 만 봐도 OK | 공식문서 |
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
  - 클론 위치: `references/aws-sample/`
- 영상 1: Nate Herk, "How to Build Claude Agent Teams Better Than 99% of People"
- 영상 2: Eric Tech, "TMUX + Claude Agent Teams = Game Changer"
- 영상 3: Hodu's AI Analysis Lab, "Claude Code Agent Teams 완벽 가이드"
- 영상 4 (짐코딩): "클로드 코드 Agent Teams 완벽 정리 | Subagent와 차이점"
- 영상 5 (Matt Pocock): "코드는 비싸지 않다" (펀더멘털 + grill-me 소개)
- 영상 6 (메이커 에반): "구글이 사양 공개한 design.md 정체"
