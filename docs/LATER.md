# LATER.md — 나중에 고민할 것

> 미해결/보류(DEFER) 항목만 유지. 완료(DONE)·폐기(STALE) 항목은 삭제 (이력은 git/세션 기록).
> 마지막 정리: 2026-07-03 — 전항목 코드베이스 대조 audit. DONE 1(스트리밍 self-heal)·
> STALE 1(out-of-process teammates) 삭제, 13개 현재상태 반영 갱신.

## Sub-agent 메모리 활성화 (보류 — 파일기반 메모리로 사실상 커버, C 정착)

4 teammate (planner/designer/developer/reviewer) 모두 네이티브 `memory` field
미설정 = **비활성화** (frontmatter 확인 2026-07-03). 결정 기록:
`docs/agent-teams-mapping.md` line 44 (LATER 로 역참조 중 — 이 항목 삭제 금지).

**왜 여전히 끄나:** 원래 이유(디버깅 단순화 + 컨텍스트 오염 회피 + 토큰 절약)는
그대로 유효하고, 그 사이 **파일기반 3단 메모리 시스템**이 크로스세션 기억 수요를
이미 담당한다 — `hooks/project_memory.py`(기계적 사실 → `.claude/harness-memory.md`
캡처) + tagged block(`<decision>`/`<learning>`/`<issue>` → CTO 가
`specs/decisions.md`·`learnings.md` 파일링, `agent-team-protocol.md` §Tagged
Memory Blocks) + `harness-self-improve`/`harness-remember`(승격 게이트). 이 시스템은
**가시·git추적·human-gated** 철학(SKILL.md §Hard boundaries)이라, 네이티브
per-agent 메모리(불투명·에이전트 자체관리 저장소)를 켜면 정면충돌한다.

**아키텍처 변화(항목 전제 갱신):** teammate는 `orca claude-teams`의
native Orca split으로 표시된다 — 구 단일-프로세스 전제와 다름.

검토 옵션 (활성화 시점):
- **A. 모두 `project` scope** — 파일기반과 중복 + 불투명 저장소 유입(현 철학 상충).
- **B. 일부만 (planner + reviewer)** — 동일 상충, 약한 안.
- **C. 계속 비활성화 (기본값)** — 파일기반이 수요 충족 + 단순함. **사실상 정착.**

활성화시 위치: `plugins/cto/agents/<name>.md` frontmatter 에 `memory: project`.
재검토 trigger = 파일기반 시스템이 못 담는 **구체적 per-agent 기억 수요**가 실제로
발생할 때만 (지금은 없음).

---

## Nate Herk hacks — 도입 후보 (중기)

> 2026-07-03 감사: 둘 다 여전히 미구현·gate 트리거 미발동 — 의도적 보류 유지.

- **Hack 32 — Context7 MCP**. cutoff 이후 라이브러리 docs 자동 인젝션.
  적용: CTO **settings.json** 의 `mcpServers` 등록 → developer.md 가이드
  (plugin subagent 는 frontmatter `mcpServers` 무시 → 세션레벨 settings.json 이
  유일 경로). 현 cutoff 대응은 developer WebFetch 수동 fetch 뿐.
  (외부 MCP 공급망 — --dangerously 환경이라 신중히)
- **Hack 13 — Haiku tier (모델 다층화)**. 현재 4 sub-agent 다 opus+xhigh
  (agents/*.md frontmatter + 프로젝트 settings.json 전부 opus-4-8·high).
  대량 read/스캔 단계만 haiku 강등 검토. frontmatter `model:` 변경이면 됨.
  (운용 토큰 데이터 본 후 — 아직 미수집. CodeBurn 비용 대시보드도 미도입)

---

## Hard rule 결정론 강제 — 잔여 승격 후보

git(1)·파일삭제(2)·DB파괴(4) 는 **2026-06-12 `hooks/git_guard.py` 로 승격
완료** (PreToolUse Bash 가드, CEO/CTO 양쪽 배선, HARNESS_USER_OK 마커 통로,
smoke 케이스). docker build/compose(§13) 는 **2026-06-24 승격 완료**
(`docker build`/`compose build`/`--build` up/서비스 미지정 bare up 차단, 예외 ②
이미지전용 서비스 named up 통과, `HARNESS_USER_OK=docker` 마커). 남은 후보:

| 카테고리 | 패턴 | 비고 |
|---|---|---|
| 패키지 전역 설치 | `apt install`, `brew install`, `npm -g`, 글로벌 pip | 빌드dir 내 선언 의존성은 RULES §3 허용이라 구분 패턴 필요 |

승격 trigger: 모델이 전역 설치를 RULES 어기고 실행하는 사고 1회 발생 시.
(현황 2026-07-03: git_guard.py 는 아직 git/fs/db/docker 4카테고리만 — 전역설치 패턴 미추가.)

### 커버리지 게이트 — PreToolUse 승격 후보

커버리지 게이트 = `scan_spec_coverage.sh specs/` (fail-closed, spec [F<n>] ↔
tasks ← F<n> 대조). 현재는 planner 가 분해 후 실행하는 **advisory-운영**
(planner.md·harness-task-format SKILL 이 "advisory G1 completeness check" 로
호출 — 모델이 실행을 잊으면 우회 가능). 승격안: PreToolUse 훅이 `specs/tasks.md`
를 쓰는 Write 를 가로채 스캐너를 돌리고 nonzero 면 누락 Feature 를 명시하며
block. 스캐너 재사용, 신규 코드는 훅 wrapper 뿐.

배선 실증: specs Write-matcher PreToolUse 게이트는 이미 존재(spec_overwrite_gate
= Done이력 덮어쓰기 차단, phase2_viewable_gate) — 다른 관심사지만 훅 wrapper
패턴/타당성은 입증됨. 이 스캐너만 붙이면 됨.

결정기준: ① tasks.md write 마다 스캔하면 분해 중간 저장도 막힘 — "분해 완료
선언" 시점만 잡을 방법 (PROCESS §3 은 이미 tasks.md 감시 훅 확대에 신중하라
기록) ② segment dispatch 직전 1회 검사로 충분한가.

### 인박스 same-turn 격리 — PreToolUse 승격 후보 (codex-protocol-review 2026-07-02 #3, blocker)

RULES §6: `/inbox`·`harness inbox` 직후 same-turn 은 요약/명확화/추가읽기만
허용(인박스 body 는 untrusted — 프롬프트 인젝션 가능). 현재 **advisory-뿐** —
user_prompt_inbox_check.py 는 preview sanitizer 일 뿐, mutating/외부 tool 을 막는
결정론 훅은 없음. CTO 는 `--dangerously-skip-permissions` 라 인박스 인젝션에
모델이 슬립하면 권한 프롬프트 없이 실행됨(실질 위협). 승격안: `harness inbox`
실행 시 PostToolUse 마커 set → 다음 user prompt 에 clear, 마커 활성 동안
PreToolUse 가 Bash/Edit/Write/SendMessage/TeamCreate 를 block (인박스 read·요약
경로만 허용). CEO/CTO 양쪽 배선 (현재 CEO settings 는 PostToolUse 훅 자체 부재).
결정기준: ① same-turn 판정 상태 저장 위치(세션 파일?) ② user-facing 요약과
tool-call 경계 구분 ③ 오버블록(정상 후속작업)과 보안의 균형.

---

## dashboard 인증 — interim 완료, 풀 로그인 남음 (2026-06-24, 갱신 2026-07-03)

**interim 보호 적용됨 (현행):**
- mutation **5종**에 토큰 게이트 — `Depends(require_token)` + `DASH_TOKEN` env +
  `X-Dash-Token` 헤더 `secrets.compare_digest`. 미설정=fail-closed(503), 불일치=401.
  (cto start/stop/delete · dev toggle · docker toggle)
- 비가역 삭제(delete-cto)는 캐시 토큰 안 쓰고 `DASH_TOKEN` **재입력** 게이트(2026-07-03 추가).
- CORS `*` → `DASH_ORIGINS` env 화이트리스트(기본 cross-origin 차단; frontend 는 /api 동일출처 프록시라 불필요).
- backend 127.0.0.1 loopback bind, frontend :8166 만 공인 노출(/api 프록시). frontend localStorage 토큰 + 1회 prompt.

**남은 것 (풀 로그인)**: 토큰 1개 공유는 임시 — 사용자 계정/세션 로그인 UI,
토큰 rotation, GET 현황(/api/state·health)도 인증할지 결정. 지금은 mutation 만
게이트(GET 열림). loopback + 동일출처 프록시라 노출 제한적 → 우선순위 낮게 park.

---

## 기타 v2 후보 (낮은 우선순위)

둘 다 미구현·저우선(의도적 park). 현재상태 앵커 (2026-07-03):

- **다중 CTO 동시작업 조율 — 의존성/충돌 관리** (동시 3~5 CTO 시점). 현재
  cross-CTO 안전장치는 spawn 시 포트충돌 회피 offset 카운터뿐 (`run.sh` add-cto,
  flock + RULES §4 TOCTOU floor). shared-module feature drift 한 조각은
  `harness/lineage_parity_scan.py`(CEO 판단보조)가 이미 커버. 남은 갭 = 동시
  활성 CTO 간 **task-level 의존성/충돌 조율**. 동시 3~5 CTO 스케일 도달 전까지 park.
- **relay 라운드 상한 강제 (hook)**. 5라운드 **soft cap** 은 이미 문서화됨
  (`plugins/cto/skills/harness-relay-qa/SKILL.md` gotcha #7 — advisory,
  "user 가 engaged 면 계속"). 미구현 = 이를 **하드 hook** 으로 강제하는 부분
  (`hooks/team/teammate_idle_workcheck.py` 의 MAX_NUDGES 카운터 패턴 응용).
  soft-by-design 이라 ROI 낮음 — 실제 drift 관측 시에만 승격.

---

## 외부 OSS 도구 조사 후보

- **CodeBurn** (`npx codeburn` 무설치, 또는 `brew tap getagentseal/codeburn && brew install codeburn`;
  `getagentseal/codeburn`) — 로컬 on-disk 세션 로그를 읽어 Claude Code·Codex·Cursor 등 25+ 툴의
  토큰·비용을 model/project/task 별로 집계 (TUI + 로컬 웹 대시보드 + macOS 메뉴바, 무가입·완전로컬,
  Node≥22.13). 지금 harness 는 **운용 토큰/비용 데이터가 전무** (대시보드는 상태만 표시, 비용 추적
  코드 없음 — 확인함). 이 데이터 부재가 곧 위 "Hack 13 — Haiku tier" 결정을 막는 병목("운용 토큰
  데이터 본 후")이고, 현재 4 sub-agent 가 전부 opus+xhigh 라 실제 cost 압력도 있음 → CodeBurn 이
  그 갭을 정면으로 채움. 주의: 외부 npm/brew 툴 = 공급망 CSO 검토대상(Context7 MCP·agentmemory 와
  동일 규율). 단 read-only·로컬(상주 프로세스/포트 없이 세션로그만 읽음)이라 agentmemory(2상주+4포트+12훅)
  대비 도입 위험은 낮음.

---

## agentmemory 도입 — 보류 (native 파일메모리로 대체 충족, semantic recall 만 갭)

`@agentmemory/agentmemory` (<https://github.com/rohitg00/agentmemory>) — 미도입.
당초 재개 트리거였던 **동시 3~5 CTO 스케일은 사실상 도달**(PORT.md: rescue-pose·
cosmetics·rtsp-detection·rtsp-keypoint 4 세션 ✅ 활성 — "활성"은 상주 Orca tab이지
4중 동시빌드는 아님). 그러나 그 사이 **native 파일기반 3단 메모리**가 구축돼
agentmemory 가 팔던 이득 대부분을 커버 → 계속 보류.

- **native 메모리 (live)**: `hooks/project_memory.py` PostToolUse(run.sh:240)가
  build/test/env/hot-path 를 `.claude/harness-memory.md`(FIFO 20 + flock, 동시 CTO
  안전)에 자동캡처 → `session_start.py` 가 다음 세션에 주입. 위로 `harness-remember`
  (라우팅 분류기) + `harness-self-improve`(재발 탐지) + agent-team-protocol Tagged
  Memory Blocks + CEO `MEMORY.md`(+토픽파일). → 12훅 자동캡처·CTO/CEO scope 격리·
  decay 를 파일로 이미 제공.
- **남은 갭(agentmemory 만의 것)**: **semantic recall** — BM25+벡터+그래프 검색 /
  recall@5 / ~2000토큰 선택주입. native 는 flat md 를 통째 surface 라 검색품질 없음.
- **보류 사유(여전히 유효)**: 글로벌 npm + 바이너리 + Node≥20(설치=하드룰 컨펌),
  상주 2프로세스 + 포트 4개, 훅 12개가 매 tool 호출 가로챔 — `--dangerously` 환경에서
  성능·공급망 리스크(CSO 검토대상).
- **재개 게이트(갱신)**: 트리거는 이제 "스케일 도달"이 아니라 **native 메모리가
  실측 실패**할 때 — memory-miss 로 CTO 가 반복 사고를 낼 때 CTO 1명 isolated trial →
  측정 → 롤아웃 판단.

---

## CEO 메모리 dir → repo 이동 (심링크) — 보류

**현황(2026-07-03 검증):** CEO 메모리 = `~/.claude/projects/<repo>/memory/`
— Claude Code 네이티브 **실디렉터리**(심링크 아님) · .md 19개(학습 18 + MEMORY.md) ·
**git 미추적**. repo 에 `memory/` 없음, 심링크 없음, `.gitignore` 항목 없음,
코드 어디도 이 경로 참조 안 함(harness/hooks/run.sh/plugins/.claude grep clean —
순수 Claude Code 소관).

**안:** 실파일을 `harness-claude/memory/` 로 이동 + 네이티브 경로를 심링크로
→ git 추적 + 가시성 + 백업. 단순 mv 는 고아됨(경로는 Claude Code 소관 — 검증함).

**보류사유 갱신:** 원래 근거 "write 가 드물어 급하지 않음" 은 **이제 거짓** —
최근 24h 에 19개 중 9개 수정(MEMORY.md 포함, 하루 수차례). 활성 write 로 미추적
학습이 계속 축적 → `~/.claude` 유실 시 CEO 학습 18건 전부 소실 위험, git 백업·
버전관리 가치는 오히려 커짐. 여전히 blocking 은 아니라 우선순위 park 유지 가능하나,
"rare 라 불필요" 근거는 폐기.

---

## 루프 영상 (oZUeRib1Xec) 고찰 — 남은 갭 G3·G4

하네스는 이미 결정론 구현체(verify gate / coverage 스캐너 fail-closed /
doctor·smoke) — 아래는 남은 빈틈. 둘 다 *의미 판단*이라 정규식 결정론 강제
불가 — advisory + 스캐너 보조 수준. 과-spec 주의.

**상태(2026-07-03 확인):** 둘 다 여전히 미구현·전제 그대로 → 의도적 보류
유지. 결정론 강제 불가 + 가치 미확정(G3 ①) + 저 CTO 스케일이라 지금 안 함이
맞음. 규모가 커지거나 사용자 요구가 생길 때 재검토.

### G3 — 운영 감시 루프 (monitor-only, 빌드 완료 이후)

**갭:** 하네스 루프(segment 루프 + `/goal` autopilot)는 분해→빌드→검증→
사용자 시각검증에서 끝난다. 그 뒤 PR/CI/머지/배포는 전부 사람 ("개발인가
경비인가" 병목). 데몬(`harness/daemon.py`)은 현재 stall-detector + inbox-nudge
전용 — CI/PR watch 없음.

**안전모델:** 하드룰1이 자율 git/머지/배포 금지(`git_guard.py` 가 `gh pr
create|merge`·`gh release` 결정론 차단) → **monitor-only**: 감시+분류+surface
만, 비가역은 사람. 하네스 철학과 일치.

**후보 접근:** 데몬을 CI/PR watch 로 확장 (gh CLI read-only) / 또는 CTO
`/loop` 폴링 → CI FAIL 로그 분류 → 자동수정 가능(린트/타입)은 `[dev]` task,
비가역은 surface.

**결정기준:** ① monitor-only 로 가치 있나 ② 데몬 확장 vs CTO `/loop`
③ `/goal`(RULES §8)의 턴 상한 + `[!]`/`[❓]` surface 모델 재사용.

### G4 — 측정(measurable) tier 임계·추세

**갭:** `health` 0-10 은 reviewer.md 상 "Flexible(your judgment)" — 측정만
하고 gate/trend 없음. "테스트는 통과하나 커버리지/성능이 회귀"를 못 잡음.
plan.md `## 5 Constraints` 에도 수치 임계(커버리지/번들) 필드 없음.

**후보 접근:** reviewer 보고 메시지에 `health` before/after 인용 의무화 →
프로젝트별 임계(plan.md ## 5 Constraints 에 "커버리지 ≥ N, 번들 ≤ M") +
cycle 간 trend (회귀 시 Warning). advisory 임계.

**결정기준:** ① 임계의 거처 ② binary/measurable 분리가 reviewer verdict
복잡도를 키우나 ③ module 빌드는 USAGE.md 가 임계 보유 / project 만 적용?

---

## 슬래시 `!`-line injection 완전차단 — instruction-only 전환

**갭:** `!`-line 의 `$0`/`$1`/`$ARGUMENTS` 는 파싱 전 bash SOURCE 에 raw splice —
in-line quoting 은 완전 방어 불가 (codex consult 결론; RULES §6.1 에 상세). 파싱
가능한 kebab 인자는 **이미 완전 차단**됨: `codex-review`(codex_review_launch.py)·
`codex-protocol-review`(codex_protocol_review_launch.py) 는 인자를 quoted-heredoc
stdin 으로 `shell=False` 헬퍼에 넘겨 bash 재해석 경로 자체를 제거한다. `build-*`·
`start-project` 의 `$ARGUMENTS` 는 `!`-line 이 아닌 instruction 텍스트(bash 미실행)
라 injection 표면이 아니다.

**남은 표면 = 자유텍스트 본문 2개뿐:** `msg-cto`(msg-cto.md:8, `printf '%s' '$1'`)·
`msg-ceo`(msg-ceo.md:8, `printf '%s' '$0'`) 는 여전히 single-quote inline splice.
현 방어(RULES §6.1) = single-quote + **작성자가 신뢰 에이전트(자기 본문 직접 작성,
외부 붙여넣기 아님)** + 외부/relay 신뢰불가 콘텐츠는 §6 규율로 붙여넣기 전 sanitize
의무. = 신뢰경계 안이라 **의도적 risk-acceptance**(지금 미전환이 맞음).

**완전한 fix (queue):** 두 커맨드를 **instruction-only** 로 전환 — `!` 자동실행 제거,
에이전트가 `shell=False` 헬퍼(heredoc/파일 채널 body)로 명시 호출. codex_review_launch.py
패턴 재사용.

**결정기준:** ① UX(한 줄 호출) 손상 정도 ② 헬퍼 stdin vs 파일-채널 본문.
(③ 다른 커맨드 일괄 스윕 = 해소됨: `!`-line 자유텍스트 경로는 msg-cto/msg-ceo 둘뿐.)

---

## 게이트 런타임 상태 결정론 검증 (스트리밍 사고 백스톱)

**갭:** 완료 게이트가 `compose config -q`·`/health 200`·포트설정 등 **부품 체크**만 하고,
**핵심기능 실동작(런타임 cross-service 상태)** 은 기계 검증 안 함. 현 완료게이트
(`hooks/team/task_completed_verify_gate.py`, `run.sh:154`)는 `Run:` 존재 + teammate
**sentinel 자기증명**까지만 강제 — teammate 가 실검증을 돌렸다는 **주장**이지, 상태 자체를
훅이 재확인하지 않는다. "상태형 의존 재기동 후 재싱크+실검증" 규칙은 `PROCESS §3`
(`plugins/_shared/PROCESS.md:154-163`, 2026-06-22 mediamtx path 사고 정본화)에
**advisory** 로 박혀 SessionStart 로 CTO 에 주입되나 — **결정론(hook) 강제는 아직 없다.**

**fix (queue):** 스트리밍류 완료 게이트에 "카메라별 path ready + 실제 재생" 기계 검증 훅.

**결정기준:** ① 모듈별 검증이라 일반 훅화 어려움 ② 위 "backend path self-heal" 이 2026-06/07
전 lineage 전파 완료(구현됨)라 이 백스톱은 더 저ROI(최후 그물) — 저ROI·모듈종속으로
**의도적 park**(필요성 낮음, 최후 그물로만 남김).

---

## 하네스 웹 관리 UI — 잔여 관리액션 (v1+핵심v2 완료, 2026-07-03 갱신)

**완료 (dashboard/ 라이브):**
- **v1 읽기전용 현황** — `GET /api/state` (`dashboard/backend/main.py:126`): 이름·타입·완성여부(own `.git`, USAGE.md 대신 신호 변경)·CTO 활성·포트셋(cells)·docker/dev 가동·DB 엔진 + lineage 그래프. 프론트 5s 폴링(`App.jsx:604`) = 결정기준③ 실시간 충족.
- **v2 CTO 라이프사이클** — add-cto=`POST /api/cto/{name}/start`(main.py:280), stop-cto=`.../stop`(298), delete-cto=`.../delete`(316), + dev/docker 토글(361/400, 원문 미포함 보너스).
- **결정기준① destructive 안전선 충족** — mutation 은 `DASH_TOKEN` 토큰 게이트(fail-closed, main.py:37) + CORS 제한, 프로젝트별 non-blocking lock(245-267)로 연타/동시 직렬화, 끝상태 검증(거짓 성공 금지). delete 는 프론트 DASH_TOKEN 재입력 게이트(`App.jsx:736`). 신뢰성 설계=`docs/superpowers/specs/2026-06-25-dashboard-control-reliability-design.md`.

**남은 것 (진짜 미구현, 편의 액션):**
- 웹에서 **msg-cto/msg-ceo** — daemon/sqlite 큐 write API 필요, CLI `/msg-cto` 와 동일 §6 sanitize 규율.
- **start-project 트리거** — CTO tab 안 커맨드라 exact Orca terminal input 경로
  필요(add-cto=terminal 스폰과 별개).
- **ports 재생성** — `.env` 충돌 위험 → 게이트 필수.

**중복 주의(이 항목 밖):** 결정기준② 인증(풀 로그인)=별도 항목 "dashboard 인증"(위)에서 추적. "Shared Infra 패널"=아래 "harness infra"와 겹침.

**결정기준:** 잔여 3개는 CLI(`/msg-cto`·`/start-project`·`ports`)로 이미 되고 편의 목적이라 ROI 낮음 → 필요 시. 추가 시 위 토큰 게이트 + 끝상태 검증 패턴 재사용.

---

## 공유 인프라 통합 관리 — `harness infra` (2026-06-29, 재확인 2026-07-03: 미구현 그대로)

**현황:** 공유 PostgreSQL(`infra/docker-compose.postgres.yml`, 127.0.0.1:5435) 은 **수동**
`docker compose -f infra/... up -d | stop` 로만 관리. (공유 MediaMTX 는 2026-07-18 폐지 —
각 카메라 프로젝트가 자기 mediamtx 를 self-host, offset 파생 포트로 번들.) 통합 명령 없음 —
`harness` CLI 서브커맨드는 send/inbox/list/roles/status/ports/db 뿐이고 `db` 는 db-per-project
provision 용이지 인프라 라이프사이클(up/down/status) 이 아님. 대시보드도 공유 인프라 **제어 없음**:
cto start/stop/delete + 프로젝트 dev/docker 토글만 있고, 공유 pg 는 `🔗` 상태 셀 **표시만**(가동중=🔗 /
중지=○). `restart: unless-stopped` always-on 이라 자주 안 만지지만 흩어져 있고, 공유 인프라가 더
늘면(redis 등) 더 분산됨.

**fix 후보:**
- `harness infra up | down | status` — `infra/*.yml` 전부 한 번에 기동/정지/상태. add-cto 가
  db provision 하듯 인프라 라이프사이클도 CLI 일원화. up = §13 `HARNESS_USER_OK=docker`,
  down/stop = `-v` 금지(볼륨/데이터 보존).
- (선택) 대시보드 "Shared Infra" 패널 — pg 상태 + start/stop 토글.

**결정기준:** ① CLI 일원화로 충분한가 vs 대시보드 패널까지 ② 공유 pg down 은 **전 pg 프로젝트
동시 영향** → 확인 게이트 필수(위 "웹 관리 UI v2" 안전선과 동일) ③ `infra/*.yml` 자동 발견 vs 명시 목록.

---

## 빌드 base dir rename `claude-project`→`harness-project` · `modules`→`harness-modules` (2026-07-24 조사, 실행 보류)

**목표(사용자 요청):** 빌드 base 두 개를 `harness-` 접두로 통일 rename. 의미(claude-project=
greenfield/feature-extract, modules=재사용 라이브러리)는 그대로, 접두만 변경.

**blast radius (2026-07-24 실측):** 자동 "문제없음" 아님 — 리터럴 + 라이브 인프라 + 실행 세션 걸림.
- **코드/설정 리터럴:** `claude-project` **94곳(~26파일)** + build-base `modules/` **75곳**
  (run.sh 25, harness/*.py 8 [cli·lineage_parity_scan·parity_scan·netbind_scan·schema_scan],
  dashboard/backend/main.py 2, hooks/team, plugins/*.md+*.py, docs, .gitignore 3, README, AGENTS, smoke).
- ★**`node_modules` 함정:** `modules` 는 흔한 토큰 → 순진한 `sed s/modules/harness-modules/g` 가
  `node_modules`→`node_harness-modules` 로 전 프론트 파괴. build-base 만(경계 `/`·`"`·` `·`$`·줄시작 +
  node_modules 제외) 골라 치환 필수. 조사 시 격리 regex 로 75건에 node_modules 0 확인.

**하드코딩 지적 정리(사용자 Q):** 이 리터럴들은 **§4.1(포트/.env) 위반 아님** — §4.1 "하드코딩 X"
(RULES.md:174·253)는 **포트·시크릿·config 런타임값** 한정(.env 단일소스). 디렉토리 base 이름은
배포마다 안 변하는 **하네스 구조 상수**라 다른 클래스. 단 **DRY 냄새는 실재**: 스캐너 4개가 각자
`BASES = (REPO/"modules", REPO/"claude-project")` 재정의, run.sh 도 리터럴 반복.

**2단계 fix (blind sed 대신):**
1. **먼저 코드 base 를 상수 1곳으로 중앙화** — harness 공유 `BASES` 상수(스캐너 import) + run.sh
   `BUILD_BASES` 변수. rename 무관하게 그 자체로 DRY 개선 + 스캐너 drift 방지. 중앙화 가능=코드 경로만.
2. 그 다음 rename = 상수값 + `.gitignore` 3줄 + 문서/스킬 **산문**(~120, 변수 불가=리터럴 불가피)만.

**실행 절차(세션 다운타임 필요):** ① stop-ceo + 4×stop-cto ② `mv modules harness-modules && mv
claude-project harness-project` ③ 리터럴 치환(격리 regex) ④ Orca 4건 재등록(옛 `repo.rm`→새 `repo add`,
또는 add-cto 자동재등록) ⑤ doctor+smoke ⑥ add-cto 재기동(새 git-init 로직이 .git 존재로 skip).

**자동 생존(손 안 대도 됨):** dev.sh(`cd "$(dirname "$0")"` 자기위치) · docker(compose project명=
빌드dir basename `rtsp-streaming` 이지 부모 아님 → 계속 돌고 다음 배포 때 새 경로 자동유도, **데이터
손실 0**) · inbox sqlite(msg 테이블 name 키, path 컬럼 없음) · `.env`/빌드dir 내부(상대·자기완결) ·
새 git-init 로직(`$dir/.git` 상대). **깨지는 것:** Orca 4 라이브 등록(abs `/…/modules/<slug>` dangle →
CTO worktree 상실) · 실행 세션 cwd · 빌드dir `.claude/harness-memory.md` 캐시 abs 경로(낡음 but
자동실행 아님=self-heal, 비치명).

**사용자 결정(2026-07-24):** rename 범위에 **docs·메모리까지 전부** 포함(옛 경로 언급 산문도 치환).
실행은 **보류(조사만)** — GO 시 위 2단계로.

**결정기준:** ① 중앙화-먼저 vs blind-sed(중앙화가 다음 rename 을 1줄로 만듦) ② 세션 stop 다운타임
타이밍 ③ 산문 ~120 치환은 기능 무영향이나 일관성용 — 사용자가 "전부" 선택.
