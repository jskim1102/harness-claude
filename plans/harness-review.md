# 하네스 재설계 검토 (read-only, 구현 X)

생성: 2026-06-11 · 방식: dynamic workflow (6 map + synth + 3 design + synth + 3 adversarial = 14 agent) + codex 자문

## 0. 목표
greenfield/feature-extract/stock 3분할이 너무 복잡 → CTO가 모듈을 프로젝트로 착각.
**새 모델**: CEO 초기 plan → CTO phase/ckpt 분해 → segment autopilot. codex on-demand. inbox `[N]` 유지.

---

## 1. 진단 — 왜 헷갈리나 (root causes)

1. **3분할 중 둘(feature-extract→module, module reuse)이 'module' 단어 공유** — 근데 모듈은 프로젝트의 **하위 부품**이지 프로젝트의 동급이 아님. 어휘가 두 altitude를 한 단어로 뭉갬.
2. **`plan.md` 가 3가지 의미로 과적재**: (a) CEO feature-extract 출력 리포트, (b) add-cto --plan 이 프로젝트에 복사하는 파일, (c) stock 전용 경량 통합 plan. 같은 파일명, 정반대 소유자/altitude.
3. **MODULE.md(정적 모듈 계약) vs stock plan.md(동적 통합)** 둘 다 spec 트리에서 'capabilities' 기술 → CTO가 모듈 capability 목록을 프로젝트 feature spec 처럼 취급 = 모듈을 프로젝트로 봄.
4. **/stock(모듈 생성, CEO) vs add-cto --module(재사용, CTO)** 가 두 tier에서 같은 명사 공유. "rtsp 모듈 만들어" 들은 CTO는 step1이 CEO 몫인 신호를 못 받음 → 반사적으로 add-cto + full-scratch greenfield, 라이브러리 안 건드림. **← 실제 발생한 실패.**
5. **모드 감지가 단일 취약 술어** — /start-project 가 use-modules.md 존재 여부로만 stock/greenfield 분기. 우발적 마커로 잘못 라우팅.
6. **라우팅이 관례뿐·우회가능** — add-cto --dir 로 마커를 임의 경로에 씀, 발견은 3개 base만 검색 → 모듈/프로젝트가 툴에 구별 불가.

**복잡도 원인**: 플래닝 엔진 2개(greenfield planner-loop vs stock 수기 plan.md) · 실행모델 2개(manned segment loop vs unmanned wake-loop) · 품질게이트 2개(G1 완전성 vs fidelity scanner) · codex 2방식(수동 §7.5 vs autopilot 자동트리거+블록).

---

## 2. 제안 — "One Project, One Engine, One Loop"
**모듈 = plan이 소비하는 라이브러리 재료(ingredient). 프로젝트의 동급 아님.**

### 흐름
- **STEP 0 (CEO 라이브러리 트랙, 선택)**: `/feature-extract`(추출 리포트), `/stock`(librarian 벤더링 → modules/<slug>/). **재료만 생산, 빌드 시작 X.** 추출/벤더링 파워 전부 유지, '재사용 부품 준비'로 재프레임.
- **STEP 1 (CEO PLAN)**: 사용자 목표 → CEO가 `plans/<slug>.md` 짧은 전략 브리프(goal/constraints/선택적 `## Reuse`로 모듈 slug 명시). phase 분해 X, codex 자동호출 X. **유일한 plan.md 의미.**
- **STEP 2 (SPAWN)**: `./run.sh add-cto <name> --plan plans/<slug>.md`. **항상 claude-project/<name>/**. --module 없음, use-modules.md 없음, claude-module/ 없음, 모드분기 없음, send-keys kickoff 없음.
- **STEP 3 (CTO 분해 — 유일 플래닝 엔진)**: `/start-project` → planner가 brief 읽고 동일 skills-loop → `spec.md`(## Features 그라운드트루스, 재사용 모듈 capability도 1급 ## Features) + `tasks.md`(phase→ckpt 트리, phaseN.ckptN). **G1 완전성 게이트 모든 프로젝트 적용.**
- **STEP 4~5**: env 셋업(🤚) → design.
- **STEP 6 (SEGMENT BUILD — 보편 manned loop)**: 사용자가 phaseN.ckptN~phaseM.ckptM 범위 선택 → blockedBy 체인 → SEGMENT-READY-FOR-GATE → 2-test(reviewer 기계검증 + 사용자 브라우저). 3연속 FAIL시 surface. **모듈 통합 = 그냥 ckpt 작업.**
- **STEP 6b (opt-in auto-advance)**: 'autopilot' 하면 segment 연속 실행, 기계검증만 사이에. wake-loop/state파일 없음, tasks.md만.
- **STEP 7~9**: 통합리뷰+G1 → **codex on-demand only** → 시각검증 → retro.

### 핵심 변경
- **add-cto**: 3모드 → 1개 (`--plan`만). --module 삭제, claude-module/ 삭제, send-keys kickoff 삭제.
- **/plan (CEO 신규)**: plans/<slug>.md 작성(goal/constraints/## Reuse).
- **/stock, /feature-extract**: 메커니즘 유지, '라이브러리 큐레이션=재료준비'로 재프레임. 'next use' → add-cto --module 대신 plan ## Reuse 참조.
- **/autopilot**: unmanned wake-loop 폐기 → manned segment loop의 'auto-advance' 얇은 verb.
- **codex**: 자동트리거 전부 삭제, /codex-review 메커니즘은 그대로 on-demand.
- **유지**: inbox [N], SQLite 큐, 4인 팀, segment 엔진, G1, modules/ 라이브러리+librarian, 포트 flock.

---

## 3. ⚠️ adversarial 비평 — 반드시 해결할 것 (제안 그대로 실행 금지)

### A. 기능 회귀
- **[CRITICAL] fidelity scanner 삭제 = 재사용 보증 상실.** G1은 fail-OPEN(planner가 spec에 안 적은 capability는 안 보임), scan_module_coverage.sh는 fail-CLOSED(MODULE.md 모든 기능 ON, 빼려면 날짜박힌 사용자 승인). rtsp 모듈 10개 capability 중 planner가 빠뜨리면 통과. → **scanner 유지 OR planner가 MODULE.md 기능당 ## Features 1개 기계적 seed + G1이 MODULE.md 대조**.
- **[HIGH] librarian 멀티소스 머지 지능이 빌드에서 분리됨.** 지금은 머지된 code/+## 통합 단계를 기계적 소비. 제안은 planner가 prose 참조만 → 머지 구조 재생성 위험. → 재사용 모듈은 생성형 planner 우회, ## 통합 단계 직접 ckpt 변환.
- **[MEDIUM] RULES §7 처방형(부분재사용=날짜박힌 cut) 폐기 = 조용한 subsetting 허용.** → decisions.md에 드롭 capability 명시 요구(체크리스트라도).
- **[LOW] 재사용 빌드에 full skills-loop 강제 = 처리량 회귀.** → 100% 재사용 plan은 생성형 front 스킵.

### B. 마이그레이션 위험 (라이브 세션 충돌)
- **[CRITICAL] freeze 스캔이 틀린 디렉토리.** claude-module/ 는 **존재 안 함**. 라이브 stock 프로젝트 rtsp-cctv-monitoring은 claude-project/ 에 있고 mode-state.json = `{"active":true,"phase":"CODEX"}` **codex 루프 진행 중**. 제안 freeze는 이걸 못 보고 그 밑의 scanner/state 파일을 삭제 → 활성 세션 붕괴. → 스캔을 claude-project/*/ 로 수정, active:true면 마이그레이션 차단.
- **[CRITICAL] 라이브 CTO 2개(auth-jwt-social, rtsp) 붙어있음.** write_role_settings가 매 spawn마다 `rm -rf .claude/commands` 후 심링크 재생성. 플러그인 파일 삭제하면 **라이브 세션 심링크 dangling**. → 라이브 CTO는 OLD wiring으로 완주시키고 NEW spawn만 마이그레이션. 라이브 세션 심링크하는 .md 절대 삭제 X.
- **[HIGH] --plan 복사 경로 사실오류.** 제안은 `.claude/plan.md` 라는데 실제 run.sh:411 = `$dir/plan.md`(루트). planner는 루트 읽음. 안 맞추면 brief 안 보여 cold-start. → 경로 1개로 통일 + planner.md 읽기경로 같은 커밋에.
- **[HIGH] 기존 프로젝트 mv 금지.** 둘 다 이미 claude-project/, 라이브 셸 cwd. mv하면 stale-cwd로 slash 깨짐. rtsp는 이미 late-stage/done → re-plan은 파괴적. → **신규=새 흐름, 기존 2개=grandfather**.
- **[MEDIUM] 라인번호 앵커 brittle** (run.sh 863줄, 당일 수정됨) → content anchor + `bash -n` 게이트.
- **[MEDIUM] big-bang 위험.** SessionStart가 RULES/role/PROCESS를 매 턴 라이브 주입 → 공유doc 수정 즉시 라이브 세션에 반영, 빌드 중 불일치. → 공유doc 수정은 라이브 drain 후 마지막.

### C. 착각이 진짜 사라지나 (usability)
- **[CRITICAL] 실제 실패를 못 막음 — 오히려 재발.** 실패는 'CTO가 디렉토리 잘못 고름'이 아니라 'CTO가 존재하는 재사용 부품을 벤더링 대신 full-scratch 빌드'. 제안은 default를 from-scratch decompose로 만들고 재사용을 **사용자가 기억해서 추가하는 선택적 ## Reuse prose 줄**로 강등 → salience 감소. → **plan/decompose 시점에 modules/INDEX.md 대조 의무 게이트**(reuse <slug> OR no-overlap OR rejected:X 명시, G1처럼 fail-closed).
- **[HIGH] 'module' 명사 과적재는 이름만 바뀜.** verb로 분기('만들어'=stock vs '써'=Reuse)는 CTO가 틀렸던 바로 그 분류. → **사용자대면에서 'module' 단어 폐기, 부품/ingredient/PART.md 로 rename**.
- **[HIGH] plans/auth-jwt-social.md 가 이미 '짧은 brief' 계약 위반** — 200줄 feature spec. 첫 산출물부터 모순. → brief 스키마 확정(goal+constraints+## Reuse만) + CTO-로컬 복사본은 `.claude/brief.md`로 개명(프로젝트 트리에 plan.md 두 번 안 나오게).
- **[MEDIUM] one-directory 전제가 이미 거짓** (claude-module/ 없음, rtsp가 claude-project/에 마커 들고 있음) → 디렉토리는 착각의 load-bearing 원인 아니었음. 진짜 레버 = planner 라이브러리 대조 게이트 + 명사 rename.
- **[MEDIUM] 재사용에 full skills-loop = spec.md 안에서 모듈-as-project 재출현.** → ## Reuse 있으면 ## Features 각 항목 `[supplied:<slug>/<cap>]` vs `[to-build]` 의무 태그(기계검증).
- **[LOW] auto-advance가 wake-loop 최악 실패면 재수입** — 3연속FAIL 카운터가 compaction 못 버팀. → 카운터를 tasks.md에 영속 OR single-segment로 제한.

---

## 4. 결론
방향(one engine/one dir/on-demand codex/라이브러리 유지)은 옳다. 단 제안 그대로 실행 시:
1. **fidelity 보증 상실**(scanner 삭제),
2. **라이브 세션 붕괴**(freeze 오스캔 + 심링크),
3. **실제 착각 재발**(reuse를 선택적 prose로 강등),
4. **명사 과적재 잔존**.

→ 4개 must-fix 반영 전엔 구현 착수 금지. 아래 open decisions 사용자 확정 필요.

---

## 5. codex 자문 (gpt, read-only consult)
**방향 동의** — 단 "one flow ≠ one 생성형 planner가 전부 처리". 재사용은 prose 아닌 **타입드 입력 + 기계강제 소비**여야. one-directory는 메인 수정 아님.

**내 리뷰가 놓친 것 (codex 추가):**
1. **세션 버저닝** — 라이브 CTO는 시작 시점 role/skill/process 파일을 핀고정해야. 공유 prompt 수정이 mid-run semantic drift 계속 유발.
2. **재사용 provenance** — 벤더 부품에 source/version/license/update 메타 필요. 없으면 stock = 추적불가 코드덤프.
3. **명령 호환성** — --module/구 slash/구 plan 의미 제거는 명시적 deprecation 동작 필요(그냥 삭제 X).
4. **재시작 semantics** — tasks.md가 유일 state면 ckpt상태/fail카운트/reviewer상태/사용자게이트가 tmux 죽음+compaction 견뎌야.
5. **brief 미명세 위험** — '짧은 brief'가 제품결정을 CTO에 조용히 떠넘김. brief에 작은 스키마 필요(goal/non-goals/reuse decision/constraints/open questions).

**가장 load-bearing must-fix**: 재사용을 선택적 prose로 두면 안 됨(= 원래 실패). 단순 구조적 수정 = **CTO 분해 전 의무 라이브러리-overlap 게이트**, 정확히 하나 emit: `reuse:<slug>`(capability를 spec에 매핑) / `reject:<slug> because...` / `no-overlap`. 그담 G1이 각 재사용 capability를 `[supplied:<slug>/<cap>]` 또는 승인된 cut으로 검증. **별도 scanner 평행 운영보다 깔끔 — 단 fail-closed semantics는 보존.**

**codex가 다르게 할 것**: 명사를 **더 세게·더 일찍 rename**. 'module' 사용자/에이전트 노출 중단 → `parts/`, `PART.md`, `vendor part`/`use part` verb. **add-cto는 brief만 받게**, 재사용은 brief 계약+검증게이트에만.

→ 내 워크플로우 critic은 scanner '유지'를 권했고 codex는 'G1으로 통합 + fail-closed 보존'을 권함 — 미세 차이, 둘 다 **fidelity fail-closed 보존**엔 동의. 결정 필요.

