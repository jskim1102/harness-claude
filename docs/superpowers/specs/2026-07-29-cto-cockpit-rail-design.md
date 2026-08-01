# CTO 콕핏 rail 설계 (2026-07-29)

## 배경 / 문제

`/start-project` 후 CTO lead 탭이 무질서하게 불어난다 (2026-07-29 실측, rtsp-detection):

- `orca claude-teams` 래퍼가 teammate 스폰마다 native split 을 강제 생성 —
  dormant 여도 잔류해 lead 탭 leaf 가 5+개.
- "Remote runtime disconnected" 카드 잔해 — stop 흐름이 keeper 를 먼저 죽인 뒤
  터미널 목록을 다시 읽는 순서라, 죽은 터미널이 `_orca_harness_terminals` 필터
  (`connected`/`writable`)에서 탈락해 탭 close 를 건너뜀 → UI 카드만 남음.
- 유저 임시 쉘까지 같은 탭에 섞임.

2026-07-23 잠금 설계("main view = CTO + skill activity 2 pane")는 래퍼가
in-process 에서도 무조건 split 을 연다는 사실을 몰랐던 가정 위에 있었다
(설계-현실 drift; 우리 코드 회귀 아님).

사용자 워크플로우(2026-07-29 확인): 주시 = lead + skill 피드. teammate 는 가끔
글랜스. 사용자가 목업으로 확정한 목표 화면:

```
┌──────────────────────┬──────────────────┐
│                      │ ★ skill-activity │
│                      ├──────────────────┤
│   CTO lead (좌 50%)  │ planner  viewer  │
│                      ├──────────────────┤
│                      │ designer viewer  │
│                      ├──────────────────┤
│                      │ reviewer viewer  │
└──────────────────────┴──────────────────┘
```

## 잠금된 결정

| # | 결정 | 근거 |
|---|---|---|
| 1 | lead 기동 = 순수 `claude` (`orca claude-teams` 래퍼 제거 — run.sh 반영 완료 2026-07-29) | native split 은 위치 제어 불가(Orca CLI 에 move/resize 없음) → rail 과 공존 불가. Agent Teams 런타임은 settings.json env + `teammateMode: in-process` 로 동일 동작 |
| 2 | rail = `add-cto` 가 split 체인으로 만드는 **정적 4단** (skill/planner/designer/reviewer) | 결정론 배치. 동적 열고닫기 데몬은 오폐쇄 위험 + 복잡도로 기각 |
| 3 | teammate pane = **읽기전용** 전사 뷰어. 개입/지시는 lead 에서 | 사용자 승인 2026-07-29. in-process 구조상 pane 은 뷰가 자연스러움 |
| 4 | 죽은 UI 카드 자동 제거는 비목표 | runtime 목록에 없는 순수 UI 잔해라 CLI 로 불가(실측). 발생 자체를 §close-order 수정으로 차단 |

## 구성요소

### 1. `harness/teammate_tail.py` — 읽기전용 teammate 전사 뷰어

- 인자: `<cto-name> <role>` (role ∈ planner/designer/reviewer).
- 전사 발견: 빌드 dir 경로를 Claude 프로젝트 slug 로 변환한
  `~/.claude/projects/<slug>/` 에서, 1행이
  `{"type":"agent-setting","agentSetting":"<role>"}` 인 최신 jsonl 을 폴링으로
  추적 (실측 2026-07-29: in-process teammate 도 각자 jsonl 전사를 남기고 1행에
  role 이 박힘). teammate 재spawn = 새 jsonl → 자동 전환.
- 렌더: assistant 발화 텍스트, tool_use 한줄 요약(도구명+핵심 인자 축약),
  SendMessage 송수신. meta/progress/시스템 레코드 스킵. role 색 프리픽스.
- 내구성: 파일 없음/파싱 실패 = 조용히 재시도 루프. pane 프로세스는 죽지 않는다.
  dormant teammate = 출력 없음(그 자체가 상태 표시).

### 2. `run.sh` — `_orca_ensure_skill_pane` → `_orca_ensure_rail`

- split 체인 (모든 split 은 대상 pane 을 50/50 분할한다는 가정 — 구현 시 실측
  보정, acceptance ①이 시각 검증):
  1. `split(lead, vertical)` → 우측 rail 루트 = ★skill (기존 `tail -F
     skill-activity.log | grep -F "[cto:<name>]"` 유지)
  2. `split(skill, horizontal, designer-viewer)` → 상 skill / 하 designer
  3. `split(skill, horizontal, planner-viewer)` → skill/planner 상반부 분할
  4. `split(designer, horizontal, reviewer-viewer)` → designer/reviewer 하반부 분할
  - 결과: skill/planner/designer/reviewer 균등 4단 (위→아래).
- 멱등 가드: **pgrep 기반** — skill pane 은 `tail ... skill-activity.log` +
  `[cto:<name>]` 패턴, teammate pane 은 `teammate_tail.py <name> <role>` 패턴.
  각 pane 별로 프로세스 존재 = 해당 split skip. 근거: Orca `terminal list` 는 우리 split leaf 를 레코드로 안 보여줘
  leaf 계수 불가 (실측 2026-07-29 — ✳ native split 은 보였으나 skill tail
  pane 은 목록에 없음).
- rail pane 은 keeper 비대상 (disposable 뷰).

### 3. `run.sh` — `_orca_close_cto` 순서 수정 (죽은 카드 발생 차단)

- 현행: `_keeper_kill` → `terminal list` → close. keeper kill 로 죽은 터미널이
  필터 탈락 → close 0건 → UI 카드 잔류.
- 수정: **terminal 목록 확보·`close --tab` 먼저 → keeper kill 나중**.
  rail pane 은 lead 탭 소속이라 `--tab` close 로 함께 닫힌다.

## Acceptance (구현 계획의 검증 기준)

1. `add-cto` 신규: lead 탭 = lead + rail 4 pane, 배치가 목업과 일치 (시각 확인).
2. `add-cto` 재실행: rail 중복 생성 0 (pgrep 가드 동작).
3. `/start-project` 스폰: native split 생성 0, planner viewer 에 boot 발화 출현.
4. `stop-cto`: Orca runtime 에 해당 CTO leaf 0 + "Reconnect" 카드 미발생.
5. 뷰어: teammate 재spawn 후 새 세션 jsonl 자동 추적.
6. `doctor`/`smoke` 기존 케이스 그린 유지 (skill pane 관련 케이스는 rail 로 갱신).

## 비목표

- rail 에서의 직접 입력(개입은 lead), 동적 pane 열고닫기 데몬, tmux 재도입,
  기존 Orca UI 잔해 카드의 자동 제거(리로드 안내로 갈음), Orca 앱 설정 변경.

## 영향 문서 (구현 시 함께 갱신)

- `plugins/cto/skills/harness-team-spawn/SKILL.md` — "orca claude-teams" 문구 →
  순수 claude + rail 구조로.
- `docs/agent-teams-mapping.md` — teammateMode 행·갭 D 의 표시 계층 설명.
- `hooks/team/start_project_spawn_nudge.py` — fallback `leaves - 2` 가정 재검토
  (roster 정본 경로는 유지).
