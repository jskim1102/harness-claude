# LATER.md — 나중에 고민할 것

> 미해결 항목만 유지. 완료 항목은 삭제 (이력은 git/세션 기록).
> 마지막 정리: 2026-06-12 (재설계 후 — 정본 `plans/harness.md`).

## Sub-agent 메모리 활성화 (미정)

4 sub-agent (planner/designer/developer/reviewer) 모두 `memory` field
미설정 = **비활성화** 상태.

이유: 디버깅 단순화 + 컨텍스트 오염 회피 + 토큰 절약. 시스템 동작
검증 후 필요한 곳만 켜기.

검토할 옵션 (활성화 시점):
- **A. 모두 `project` scope** — 각 프로젝트당 4 sub-agent 메모리 누적
- **B. 일부만 활성화** — planner + reviewer 만 (장기관찰자). designer + developer 비활성화
- **C. 계속 비활성화 유지** — 단순함 우선

활성화시 위치: `plugins/cto/agents/<name>.md` 의 frontmatter 에
`memory: project` 추가.

---

## Nate Herk hacks — 도입 후보 (중기)

- **Hack 32 — Context7 MCP**. cutoff 이후 라이브러리 docs 자동 인젝션.
  적용: CTO settings.json 의 `mcpServers` 등록 → developer.md 가이드.
  (외부 MCP 공급망 — --dangerously 환경이라 신중히)
- **Hack 13 — Haiku tier (모델 다층화)**. 현재 4 sub-agent 다 opus+xhigh.
  대량 read/스캔 단계만 haiku 강등 검토. frontmatter `model:` 변경이면 됨.
  (운용 토큰 데이터 본 후)

---

## Out-of-process teammates — CTO 패널 visible noise 근본해결 (중기)

**문제:** Agent Teams `teammateMode: in-process` → 모든 teammate
SendMessage 가 CTO conversation 에 render. agent↔agent 정리·status
update·ack 가 화면을 채워 사용자 surface 가 위로 밀림.

**근본해결 후보 — out-of-process teammate:**

teammateMode 를 `in-process` → `spawn` 같은걸로 변경. 각 teammate 가
별도 Claude Code 인스턴스 (별도 tmux session — 각자 `./run.sh attach` 로
독립 접속). CTO 패널엔 CTO 자기 출력만.

**필요한 작업:**

1. **teammate mode 옵션 조사** — `spawn`/`subprocess` 실제 지원 여부,
   settings.json teammateMode 허용값.
2. **통신 버스 재설계** — out-of-process 면 SQLite/파일/IPC 명시 필요.
   기존 harness msg bus 확장 가능.
3. **CTO 자동조율 능력 보존** — Plan-approval gate, state sharing 이
   out-of-process 에서 어떻게 되는지.
4. **비용분석** — 4 teammate × Opus = 4 인스턴스. in-process 의
   cost-amortization 잃음.

**Decision criteria:** 사용자 결정시간 보호 vs 비용 / Claude Code 공식
multi-pane teammate render 가 곧 나올 가능성 (있으면 무의미).

---

## Hard rule 결정론 강제 — 잔여 승격 후보

git(1)·파일삭제(2)·DB파괴(4) 는 **2026-06-12 `hooks/git_guard.py` 로 승격
완료** (PreToolUse Bash 가드, CEO/CTO 양쪽 배선, HARNESS_USER_OK 마커 통로,
smoke 10케이스). 남은 후보:

| 카테고리 | 패턴 | 비고 |
|---|---|---|
| 패키지 전역 설치 | `apt install`, `brew install`, `npm -g`, 글로벌 pip | 빌드dir 내 선언 의존성은 RULES §3 허용이라 구분 패턴 필요 |

승격 trigger: 모델이 전역 설치를 RULES 어기고 실행하는 사고 1회 발생 시.

### 커버리지 게이트 — PreToolUse 승격 후보

커버리지 게이트 = `scan_spec_coverage.sh specs/` (fail-closed, PROCESS §2
장치1 — spec [F<n>] ↔ tasks ← F<n> 대조). 현재는 planner 가 분해 후 실행하는
**advisory-운영** (모델이 실행을 잊으면 우회 가능). 승격안: PreToolUse 훅이
`specs/tasks.md` 를 쓰는 Write/Edit 를 가로채 스캐너를 돌리고 nonzero 면
누락 Feature 를 명시하며 block. 스캐너 재사용, 신규 코드는 훅 wrapper 뿐.

결정기준: ① tasks.md write 마다 스캔하면 분해 중간 저장도 막힘 — "분해 완료
선언" 시점만 잡을 방법 ② segment dispatch 직전 1회 검사로 충분한가.

---

## 기타 v2 후보 (낮은 우선순위)

- 다중 CTO 동시작업 조율 — 의존성/충돌 관리 (3~5 CTO 시점)
- relay 라운드 상한 강제 — hook 으로 가능 (TeammateIdle 패턴 응용).

---

## 외부 OSS 도구 조사 후보

- **CodeBurn** (`brew install codeburn`) — AI 사용량/비용 6축 달러 환산
  대시보드. 토큰 한도·cost 이슈에 유용할 수도.

---

## agentmemory 도입 — 보류 (스케일 + 안정화 후 trial)

목표 스케일: **동시 3~5 CTO**. `@agentmemory/agentmemory`
(<https://github.com/rohitg00/agentmemory>) — 지금은 파일기반 메모리로
충분 → 보류.

- 이득: 12훅 자동캡처 / recall@5 95.2% + ~2000토큰 선택주입 / CTO 격리·CEO
  공유 scope / BM25+벡터+그래프 + decay.
- 비용: 글로벌 npm + 바이너리 + Node≥20 (설치=하드룰 컨펌), 상주 2프로세스 +
  포트 4개, 훅 12개가 매 tool 호출 가로챔 (성능+공급망, CSO 검토대상).
- 순서: 3~5 CTO 운용 도달 → CTO 1명 isolated trial → 측정 → 롤아웃 판단.

---

## CEO 메모리 dir → repo 이동 (심링크) — 보류

현재 CEO 메모리 = `~/.claude/projects/<repo>/memory/` (Claude Code 네이티브
경로). 옮기는 안: 실파일을 `harness-claude/memory/` 로 이동 + 네이티브
경로를 심링크로 → git 추적 + 가시성. 단순 mv 는 고아됨 (경로는 Claude Code
소관 — 검증함). write 가 드물어 급하지 않음.

---

## 루프 영상 (oZUeRib1Xec) 고찰 — 남은 갭 G3·G4

하네스는 이미 결정론 구현체(verify gate / coverage 스캐너 fail-closed /
doctor·smoke) — 아래는 남은 빈틈. 둘 다 *의미 판단*이라 정규식 결정론 강제
불가 — advisory + 스캐너 보조 수준. 과-spec 주의.

### G3 — 운영 감시 루프 (monitor-only, 빌드 완료 이후)

**갭:** 하네스 루프(segment 루프 + `/goal` autopilot)는 분해→빌드→검증→
사용자 시각검증에서 끝난다. 그 뒤 PR/CI/머지/배포는 전부 사람 ("개발인가
경비인가" 병목).

**안전모델:** 하드룰1이 자율 git/머지/배포 금지 → **monitor-only**:
감시+분류+surface 만, 비가역은 사람. 하네스 철학과 일치.

**후보 접근:** 데몬을 CI/PR watch 로 확장 (gh CLI read-only) / 또는 CTO
`/loop` 폴링 → CI FAIL 로그 분류 → 자동수정 가능(린트/타입)은 `[dev]` task,
비가역은 surface.

**결정기준:** ① monitor-only 로 가치 있나 ② 데몬 확장 vs CTO `/loop`
③ `/goal` 의 턴 상한 + `[!]` surface 모델 재사용.

### G4 — 측정(measurable) tier 임계·추세

**갭:** `health` 0-10 을 측정만 하고 gate/trend 없음 — "테스트는 통과하나
커버리지/성능이 회귀"를 못 잡음.

**후보 접근:** reviewer 보고 메시지에 `health` before/after 인용 의무화 →
프로젝트별 임계(plan.md ## 5 Constraints 에 "커버리지 ≥ N, 번들 ≤ M") +
cycle 간 trend (회귀 시 Warning). advisory 임계.

**결정기준:** ① 임계의 거처 ② binary/measurable 분리가 reviewer verdict
복잡도를 키우나 ③ module 빌드는 USAGE.md 가 임계 보유 / project 만 적용?

---

## 슬래시 `!`-line injection 완전차단 — instruction-only 전환

**갭:** `!`-line 의 `$ARGUMENTS` 는 파싱 전 bash SOURCE 에 raw splice —
in-line quoting 은 완전 방어 불가 (codex consult 결론). 현 방어는 부분적:
kebab 인자(`codex-review`)는 `shell=False` 헬퍼로 차단, 자유텍스트
(`msg-cto`/`msg-ceo`)는 신뢰 에이전트 가정 + §6 sanitize 규율뿐.

**완전한 fix (queue):** 자유텍스트 커맨드를 **instruction-only** 로 전환 —
`!` 자동실행 제거, 에이전트가 `shell=False` 헬퍼(heredoc/파일 채널 body)로
명시 호출. `codex_review_launch.py` 패턴 재사용.

**결정기준:** ① UX(한 줄 호출) 손상 정도 ② 헬퍼 stdin vs 파일-채널
③ `$ARGUMENTS` 쓰는 다른 커맨드 일괄 스윕 여부.
