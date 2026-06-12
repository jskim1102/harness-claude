# Agent Teams — 우리 설계 매핑

> ⚠️ **부분 이력 문서 (2026-06-12 재설계 반영 주석).** Agent Teams 결합
> 메커니즘(2층 아키텍처·teammate 구조·메시지 채널)은 **현행 유효**.
> 단 빌드 흐름 관련 절(stock·feature-extract·observe·use-modules·
> add-cto 구 시그니처)은 재설계로 **폐기** — 현행 정본 = `plans/harness.md`,
> 운영 스펙 = `plugins/_shared/PROCESS.md`. 폐기 절은 아래에 ⚠️ 마커.

이 문서는 Claude Code Agent Teams 공식 기능과 `harness-claude` 의 CEO/CTO
아키텍처가 어떻게 결합되는지, 그리고 모든 의사결정의 출처를 정리한다.

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
  변경 없음. v1 MVP 그대로.
- **CTO ↔ sub-agents** = Claude Code 의 native Agent Teams 기능. v2 추가.
- CEO 는 Agent Teams 를 쓰지 않는다. CEO 는 사용자 ↔ CTO 의 메타관리만.
- 사용자는 **CTO 와만 직접 대화**. sub-agent 들은 invisible
  (`teammateMode: in-process`).

## 잠금된 의사결정

| 항목 | 결정 | 출처 |
|---|---|---|
| Q1. sub-agent 자동스폰 트리거 | 사용자가 자연어로 "create a team of X" 직접 입력. CTO 가 의도추론으로 자동 spawn 하지 않음 | 영상 1/2/3 + AWS sample 패턴 |
| Q2. plan approval mode | 활성화 — destructive 작업전 lead 승인 | 공식문서 + 영상 1 |
| Q3. spec 디렉토리 | `.claude/specs/<slug>/` 에 spec.md / design.md / tasks.md / review.md / decisions.md | AWS sample |
| Q4. devil's advocate | 별도 sub-agent 분리 X. reviewer 의 한 단계 ("Devil's Advocate Pass") 로 통합 | AWS sample review-agent + 우리 토큰절약 |
| 메모리 (각 sub-agent) | 비활성화 (memory field 생략). LATER.md 에 기록 | 디버깅 단순화 우선 |
| 도구 권한 | 엄격 allowlist (P1 시작). 필요시 확장 | AWS sample + 우리 결정 |
| 모델 + effort | opus 4.8 + xhigh 모두 | 사용자 결정 |
| teammateMode | in-process (사용자가 CTO 만 봄) | Q1 = "사용자 CTO 와만 대화" |
| 사용자 시각검증 게이트 | M4 = B (게이트 X, 자율판단). 단 reviewer 의 verdict 는 강제 | 사용자 결정 + 토큰절약 |
| 슬라이스 크기 | 시간상한 X. 원칙만 ("사용자가 화면에서 새 동작 1개 수행 최소단위") | 사용자 결정 |

## 활동 단위 표 (one team handles all activities)

| 활동 | active teammate | trigger (entry) | trigger (exit) |
|---|---|---|---|
| **Plan** | planner | 사용자 새 요청 또는 plan 수정 요청 | spec.md / tasks.md 완성 + 사용자 컨펌 |
| **Design** | designer (lead) + planner (observe) | Plan 완료 또는 UI 수정 요청 | design.md + DESIGN.md + HTML/CSS 완성 + 사용자 컨펌 |
| **Build** | developer (lead) + reviewer (parallel) + planner (observe) | Design 완료 또는 다음 ckpt 시작 | ckpt 완료 + reviewer PASS + 사용자 시각검증 |

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

## Sub-agent skills 매핑 (locked)

### planner (5 skills)
1. `gstack:office-hours` — YC 6질문 / 디자인씽킹 (의도파악)
2. `superpowers:brainstorming` — 요구사항·디자인 탐색
3. `superpowers:writing-plans` — phase/ckpt 문서작성
4. `mattpocock:grill-me` — plan 항목별 사용자 캐묻기
5. `gstack:plan-eng-review` — 기술 lens 검토

### designer (4 skills)
1. `gstack:design-consultation` — DESIGN.md 생성
2. `gstack:plan-design-review` — 디자인 plan 차원 0-10 평가
3. `gstack:design-shotgun` — UI 변형 생성
4. `gstack:design-html` — Pretext-native HTML/CSS 실코드

### developer (5 skills)
1. `superpowers:test-driven-development` — TDD 강제
2. `andrej-karpathy-skills:karpathy-guidelines` — 복잡화방지
3. `run` — 앱 띄우기 (시각테스트 환경)
4. `verify` — 변경 실작동검증
5. `superpowers:systematic-debugging` — 버그 발생시

### reviewer (5 skills)
1. `gstack:code-review` — diff 리뷰
2. `gstack:qa-only` — web QA 보고만 (수정 X)
3. `gstack:health` — lint/type/test 헬스점수
4. `gstack:design-review` — 시각 QA
5. `superpowers:requesting-code-review` — 리뷰 룰

## 파일 / 디렉토리 구조

```
harness-claude/
├── plugins/
│   ├── ceo/                            # CEO (확장)
│   │   ├── role.md
│   │   ├── commands/
│   │   │   ├── inbox.md
│   │   │   ├── msg-cto.md
│   │   │   ├── cto-pick.md
│   │   │   ├── feature-extract.md      # NEW — 비대화 워크플로우 트리거
│   │   │   └── harness-audit.md        # NEW — 하네스 자체 감사 트리거
│   │   └── workflows/                  # NEW — saved dynamic workflows
│   │       ├── feature-extract.js
│   │       └── harness-audit.js
│   └── cto/                            # CTO + sub-agents (v2)
│       ├── role.md                     # team-lead
│       ├── commands/
│       │   ├── inbox.md
│       │   ├── msg-ceo.md
│       │   └── start-project.md
│       ├── agents/
│       │   ├── planner.md
│       │   ├── designer.md
│       │   ├── developer.md
│       │   └── reviewer.md
│       ├── rules/
│       │   └── agent-team-protocol.md
│       └── skills/                     # 5 harness-internal skills
│           ├── harness-relay-qa/
│           ├── harness-team-spawn/
│           ├── harness-task-format/
│           ├── harness-evidence-pack/
│           └── harness-unknowns-check/
├── hooks/
│   ├── session_start.py
│   ├── user_prompt_inbox_check.py      # NEW — CEO 인박스 자동 노출
│   └── team/                           # AWS sample 포팅
│       ├── team_hook_common.py
│       ├── task_created_format_check.py
│       ├── task_completed_verify_gate.py
│       ├── teammate_idle_workcheck.py
│       └── skill_announce.py           # tmux RCE 가드 적용
├── docs/
│   ├── agent-teams-mapping.md          # 이 문서
│   └── claude-code-docs/               # Claude Code 공식문서 캐시
├── references/
│   └── aws-sample/                     # 포팅 원본 (aws-samples upstream)
└── run.sh                              # ⚠️구버전 명령 목록 — 현행: ceo / add-cto <plan.md경로> / attach / ls / ports / down / delete-cto / test-cto / fetch / doctor / smoke
```

런타임 sandbox:

```
sandbox/cto-<name>/
└── .claude/
    ├── settings.json                   # env + teammateMode + hooks
    ├── commands/<symlinks>
    ├── agents/<symlinks to plugins/cto/agents/>
    └── rules/<symlinks to plugins/cto/rules/>
```

## CEO 측 메타 도구 (v3 추가)

CEO 가 사용자와 직접 대화하는 슬래시 + 워크플로우:

| 도구 | 종류 | 트리거 | 출력 |
|---|---|---|---|
| ⚠️(폐기) `/stock <source-path> "<feature>"` | 인터랙티브 슬래시 | 사용자 `"이거 모듈로 만들어"` / `"창고에 쟁여둬"` | `modules/<slug>/` (벤더링 코드 + MODULE.md) |
| ⚠️(폐기) `/feature-extract` | dynamic workflow | 보통 `/stock` 내부에서 호출 | JSON plan (호출자가 markdown 변환) |
| `/harness-audit` | dynamic workflow | 사용자가 `"하네스 감사해"` 자연어 또는 슬래시 | JSON audit (호출자가 markdown 변환) |
| UserPromptSubmit hook | 자동 | 매 사용자 입력 직전 | 인박스 미읽음 prompt 컨텍스트에 주입 |

`/feature-extract` 의 phase: Setup (understand-anything graph) → Locate → Trace (6 perspective 병렬) → Adversarial → Plan.  
`/harness-audit` 의 phase: Inventory → Analyze (5 perspective) → Plan (KEEP/SHRINK/MOVE/SPLIT/CONVERT/DELETE) → Adversarial.

## 사용 사례 (사용자 입장에서)

### 1a. 새 프로젝트 시작 (무에서)
```bash
./run.sh ceo                                       # CEO 직결 시작
# (다른 터미널에서)
./run.sh add-cto deepboard /path/to/deepboard
./run.sh observe                                   # ⚠️(폐기 — attach 로 독립 접속)
tmux attach -t observe
```
CTO 화면에서 자연어 입력:
```
회원가입 + 대시보드 미리보기 기능 만들어줘.
agent team 띄워서 진행.
```
CTO 가 자연어 인식 → `TeamCreate` 호출 → 4 teammate spawn → planner
부터 활동 시작.

### 1b. 새 프로젝트 시작 (기존 프로젝트 기능 재사용)
```
[CEO 채팅]
> ⚠️(이하 예시 폐기 — 현행: /build-module → add-cto modules/<name>/plan.md)
> /stock /path/to/prime "재사용할 기능 한 줄 설명"
# CEO 가 /feature-extract 실행 (understand-anything graph + trace + adversarial)
# → 사서(librarian)가 modules/<slug>/ 에 코드 벤더링 + MODULE.md + INDEX 갱신
# → "이 모듈 활용: ./run.sh add-cto <name> <dir> --module <slug>" 안내
```
```bash
[새 터미널]
./run.sh add-cto yard /path/to/yard --module <slug>
# → use-modules.md 가 새 프로젝트 root 에 작성
# → 12초 후 자동 kickoff: "use-modules.md 읽고 해당 모듈 재사용해서 plan 시작해"
# → CTO planner 가 MODULE.md 읽고 code/ 재사용 plan 으로 team spawn
```
CEO 채팅 추가 명령 X.

### 2. 진행관찰
사용자는 CTO 화면만 본다. CTO 가 종합해서 보고:
- "planner 가 spec 작성중입니다. 5분 안에 grill-me 단계 들어갑니다."
- "designer 가 변형 3개 생성했습니다. 어느 것 선택?"
- "Group 1 reviewer PASS. <URL> 에서 시각검증 부탁드립니다."

Shift+Down 으로 sub-agent 직접확인 가능 (선택사항).

### 3. 사용자 피드백
```
designer 한테 더 minimalist 한 variant 만들어달라고 해
```
CTO 가 `SendMessage` 로 designer 에 전달.

### 4. Cleanup
모든 group PASS + 시각검증 끝나면:
```
team cleanup 해줘
```
CTO 가 documentation 단계 → `TeamDelete`.

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

## v3 후보 (지금 X)

- 메모리 활성화 (memory: project) — 일부 sub-agent
- skill 변환 패턴 (영상 2) — 성공한 workflow 를 새 skill 로 codify
- AWS sample 의 specs/<slug>/sa-review.md (Architecture review) — 별도
  sub-agent 추가
- file ownership map 자동생성 (lucasbrandao 패턴)
- multi-CTO 동시 team — 현재 한 CTO 가 한 team. 멀티 CTO 면 여러 team
  병렬 (각 CTO 가 본인 team)
- `/team <template>` 슬래시커맨드 (lucasbrandao 패턴)
