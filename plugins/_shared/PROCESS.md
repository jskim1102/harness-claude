# 하네스 빌드 프로세스

위치: `plugins/_shared/` (RULES.md 옆 — canonical 운영 스펙). SessionStart 가
**CTO 세션에** 주입한다. 설계 배경·이력의 정본 = `plans/harness.md`.
하드룰(git/파일/포트/인박스/충실도/autopilot 경계)은 RULES.md — 본 문서는 **흐름**.

> 모드 legend: 🤚 사용자 확인 · 🤖 goal 기반 autopilot · ⚙️ 자체 리뷰

## 0. 모듈 vs 프로젝트 (가장 먼저 — 내가 뭘 짓고 있는가)

- **모듈** = 여러 프로젝트에 재사용되는 기능 단위. 그 자체가 산출물.
  프론트 **단순**(재사용 쉽게), 기능 목적 최우선. `modules/<name>/`.
- **프로젝트** = 실사용 상용 서비스. 모듈 조립+glue 또는 scratch.
  프론트 **디자인 중요**. `claude-project/<name>/`.
- 빌드타입은 **plan.md 의 부모 디렉토리가 확정**한다 (modules/ = 모듈,
  claude-project/ = 프로젝트). CTO 재량으로 재해석 금지 — 모듈을 풀
  프로젝트처럼 짓거나, 그 역도 위반.

plan.md 의 3축 선언을 그대로 따른다:
- 축1 deliverable: `module` | `project`
- 축2 target: `new` | `extend:<기존프로젝트>` (extend = 기존 tasks.md 트리에 append)
- 축3 source: `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합

## 1. 타임라인 (전체 흐름)

| 단계 | 주체 | 하는 일 | 모드 |
|---|---|---|---|
| 1 Plan 작성 | CEO ↔ 사용자 | `/build-project`·`/build-module <brief>` → `<빌드dir>/plan.md` (3축 + Library Check) | 🤚 plan 확정 |
| 1 Plan 검사 | CEO | plan.md 자체 점검 후 CTO로 | ⚙️ |
| 2 스폰 | 사용자 | `./run.sh add-cto <빌드dir>/plan.md` (plan.md 없으면 실패) | 🤚 |
| 2 분해 | CTO | plan.md → `specs/spec.md` + `specs/tasks.md` + 커버리지 기계검증 | ⚙️ |
| 3 구간지정 | 사용자 | `phaseN.ckptN~phaseM.ckptM` 지정 (= 분해 승인) | 🤚 |
| 3 phase1 환경설정 | developer | 포트·venv·Docker 준비 (실행 X) | 🤖 |
| 3 게이트1 | 사용자 | 환경설정 확인 | 🤚 |
| 3 phase2 프론트 디자인 | designer | 시스템→시안→HTML/CSS → dev 서버 기동 | 🤖 |
| 3 게이트2 | 사용자 ↔ designer/developer | 라이브 디자인 루프 → 승인 | 🤚 대화 반복 |
| 3 phase3+ 빌드 | developer | `/goal` autopilot — compose 기동 시작 | 🤖 |
| 3 자체 검증 | CTO → reviewer | 필요 시 API·DB·코드 검증 → 수정 → 완료 보고 | ⚙️ |
| 3 게이트3 | 사용자 | 브라우저 실사용 테스트 → PASS=다음 segment | 🤚 |
| 마감 (module 한정) | CTO | `specs/USAGE.md` 작성 = 재사용 가능 표시 | ⚙️ |
| codex (옵션) | 사용자 → CEO | 사용자가 원할 때만 `/codex-review <name>` | 🤚 |

- `[!]` 블로커 = 어느 단계든 goal 중단 → 사용자 surface
- 🤖 구간이라도 게이트1·2는 `/goal` 로 통과 불가 (RULES §8)

## 2. 분해 (CTO — 스폰 직후)

plan.md 읽고 전체 phase/ckpt 트리를 만든다 → `<빌드dir>/specs/spec.md` + `specs/tasks.md`.

**분해 공식 (고정):**
- phase1 = 환경설정 — 포트(offset→`.env`/`.env.example`/compose)·venv+패키지·
  Docker pull·Dockerfile(+GPU 프로젝트면 Dockerfile-gpu). DB 쓰는 빌드면
  migration 툴(alembic 등) 셋업 + plan 데이터모델 → **첫 migration** 작성
  (RULES §9). **작성·준비만, 컨테이너 실행 X**
- phase2 = 프론트엔드 — **프론트 산출물 전부 여기** (디자인이든 extract든; module=단순 / project=화려).
  extract 면 프론트 UI 추출(컴포넌트·훅·페이지)도 phase2 — 백엔드 없이도 dev 서버로 **레이아웃/시안 검수** 가능 (live 데이터는 백엔드 contract 기준 phase3+). **무조건 두 번째.**
- phase3+ = 백엔드·로직·glue — 재료(축3) **백엔드** 벤더링/추출 → glue → API/로직/DB.
  **phase3 진입 = (phase2 dev 서버 정지 →) FULL `docker compose up -d` (backend + frontend + db
  전 서비스) 기동 → phase3+ 내내 계속 떠둔다** (segment 사이에 내리지 않음; 기능·배선 추가 시
  `compose up -d --build <svc>` 로 재빌드·재기동해도 스택은 유지). **사용자가 언제든 내/외부
  네트워크로 접속 가능해야 한다** (프론트가 phase2 에 완성돼 phase3 부터 컨테이너로 뜸 — 배선이
  늦는 빌드도 프론트 컨테이너는 떠서 UI 보임, 배선 진행되며 갱신). dev 서버 안 끄고 compose 하면
  같은 호스트 포트(`FRONTEND_PORT`/`BACKEND_PORT`) 충돌 `address already in use`.
- 축2=extend 면 기존 트리에 phase append (재번호 금지)

**형식:**
```markdown
# Spec: <name>            # specs/spec.md
## Features
- [F1] <기능> [to-build]
- [F2] <기능> [supplied:modules/<name>]
```
```markdown
# Tasks: <name>           # specs/tasks.md
## phase1 — 환경설정
### phase1.ckpt1 포트→.env/compose · venv · Docker · Dockerfile
## phase2 — 프론트엔드 디자인
### phase2.ckpt1 <디자인 작업>
## phase3 — <개발...>
### phase3.ckpt1 <작업>  ← F1
```

**필수 장치 (fail-closed — RULES §7):**
- **역참조 커버리지**: 모든 ckpt 가 spec 라벨(`← F<n>`) 역참조. spec 의 모든
  Feature(supplied 포함) ≥1 ckpt. 기계 검증 실패 = 분해 미완 — segment 진행 X.
- **supplied/to-build 태그**: 재료(modules/extract) 기반 기능은
  `[supplied:<출처>]` 필수. supplied 를 from-scratch 재구현 금지.
- **extract `From:` 포인터**: `extract`(`[supplied:.sources/...]`) 기능을 덮는
  ckpt 의 task 는 `From: .sources/<proj>/<file>:Lx-Ly` 원본 위치를 인용해야 한다.
  planner 가 원본을 직접 읽어 추출하고(파일은 CEO 가 plan §3 에 짚음, 라인 추출은
  CTO 몫), acceptance 는 기능 재진술이 아니라 **원본 대비 diff**(뭘 떼고 wire 하나).
  developer 는 `From:` 원본을 복사·적응 — 산문에서 재구성 X. 커버리지 기계검증이
  `From:` 부재를 차단(modules 재사용은 USAGE.md 통합이라 면제).
- ckpt ID `phaseN.ckptN` 은 **안정적** — segment dispatch 단위, 재번호 금지.
- **스키마 = migration 전용 (RULES §9)**: 빌드 중 스키마 변경은 ad-hoc DDL
  금지, migration 파일로만. 파괴적 변경(drop/alter/rename)은 사용자 승인 후
  적용. git_guard 가 raw CLI DDL 을 결정론 차단.

분해 완료 → 사용자에게 트리 표시. **사용자의 segment 지정 = 분해 승인.**

## 3. segment 루프 (CTO — 빌드 본체)

1. 사용자 : `phaseN.ckptN ~ phaseM.ckptM 진행해` (또는 `... autopilot`)
2. CTO : segment 실행. autopilot 이면 `/goal` 설정 —
   조건 = "범위 내 전 ckpt `[✅]` + 검증 증거 제시됨, or stop after N turns".
   증거(테스트 출력)는 반드시 대화에 표면화 (goal 평가자는 transcript 만 읽음).
3. **phase1 끝** → 증거(docker ps·포트·헬스체크) 들고 🤚 게이트1 (환경설정 확인).
4. **phase2 끝** → dev 서버(hot-reload, `FRONTEND_PORT`, **`0.0.0.0` 바인딩 — RULES §5.3, 127.0.0.1 금지**) 기동 → 🤚 게이트2
   **CTO 의무 — 모든 축 예외 없음**: phase2 프론트가 끝나면 **무조건** dev 서버를
   `0.0.0.0` 으로 띄우고, 아래 **4항목**을 사용자에게 제시하며 **"접속해 디자인 시안 확인해주세요"** 를 명시 요청한다:
     1. **내부 URL(같은 머신)**: `http://127.0.0.1:<FRONTEND_PORT>` — 방화벽 무관, 항상 닿음.
     2. **외부 URL**: LAN(같은 망) `http://<hostname -I 사설 IP>:<FRONTEND_PORT>` ·
        인터넷 `http://<curl -s api.ipify.org 공인 IP>:<FRONTEND_PORT>`
        (인터넷은 라우터 포트포워딩 필요 · CGNAT 면 불가 · 공개망 노출 보안 고려).
        `hostname -I` 사설 IP 를 "인터넷 외부" 로 제시 금지 (LAN 행에만).
     3. **방화벽 개방 명령** (LAN/외부 접속하려면 사용자가 그대로 복붙 실행):
        `sudo ufw allow <FRONTEND_PORT>` [+ 외부에서 백엔드 API/WS 직접 호출 시 `sudo ufw allow <BACKEND_PORT>`].
        **§5.3 의 `0.0.0.0` 바인딩만으론 부족 — OS 방화벽(ufw)이 inbound 를 막으므로 이 명령이 있어야 외부에서 닿는다.**
     4. **포트포워딩 포트** (인터넷 접속 시 라우터 설정): 공인IP:`<PORT>` → 사설IP:`<PORT>`, 대상 = `FRONTEND_PORT`[, `BACKEND_PORT`].
   외부접속이 필요한 **모든 포트**(프론트 + 외부에서 API/WS 직접 호출 시 백엔드)에 대해 `ufw allow` + 포워딩 포트를 빠짐없이 명시한다.
   게이트2 시각 검수를 **최종 compose 로 미루지 않는다** (extract 빌드도 동일 — 프론트가 phase2 에
   있으니 빈 껍데기가 아니라 실 UI 레이아웃이 보여야 한다).
   **라이브 디자인 루프**: 사용자가 브라우저로 보며 수정사항 말함 →
   designer/developer 즉시 수정 → 사용자는 새로고침으로 확인 → 반복 → 승인.
   **compose 로 띄우지 말 것** (수정마다 재기동 비효율 — dev 서버만).
5. segment 완료 시 CTO 판단으로 reviewer 호출(무조건 X) — API 테스트(curl·pytest)·
   DB 무결성(SQL)·코드 평가. 지적 → `[dev]` 수정 → 재검증.
6. CTO → 사용자 "완료" 보고 (검증 증거 포함). reviewer 결과는 **파일 X, 보고 메시지**.
7. 사용자 : 브라우저 실사용 테스트 (🤚 게이트3) → PASS = 다음 segment / FAIL = 재작업.
   **서버 노출 시점(게이트3 compose 기동 등 — 게이트2 뿐 아니라 사용자에게 서버 URL 을
   주는 모든 지점)에서 step4 의 4항목(내부 URL · 외부 URL · `sudo ufw allow <PORT>` · 포트포워딩 포트)
   형식으로 접속 정보를 제시한다.**
8. 진행 상태는 `specs/tasks.md` 체크박스만 갱신 (완료 `[✅]`, 미완 `[ ]`, 블로커 `[!]`) — 별도 상태파일 금지. (레거시 `[x]` 도 완료로 인식.)

**phase3+ 스택 상시 가동 (사용자 요구)**: phase3 진입부터 compose 스택(**backend + frontend + db
전 서비스**)이 **계속 떠있어야** 한다. segment 사이에 `compose down` 금지 — 기능·배선 추가 시
`compose up -d --build <svc>` 무중단 갱신. **사용자는 phase3+ 내내 언제든** 내/외부 네트워크로
접속할 수 있다 (게이트3 segment 완료 때만이 아니라 상시). 프론트가 백엔드에 아직 안 붙어도
프론트 컨테이너는 떠서 UI 가 보인다.

**segment 완료 판정 + 1회 surface (CTO 규율 — 중복질문 방지):**
- **완료 앵커 (결정론)**: dispatch 한 segment `phaseN.ckptN~phaseM.ckptM` 는
  **범위 내 모든 ckpt 가 `[✅]`(전 task 완료) + 검증 증거 확보** 됐을 때만 완료다.
  그 전 = teammate 가 아직 작업 중 → **다음 segment 를 입에 올리지 않는다**
  (진행 보고만, 또는 침묵). dispatch 할 때 그 범위를 기억해 완료 경계로 삼는다.
- **진행 보고도 검증 필수 (dispatch ≠ 진행)**: "구동 중"·"진행 중" 보고 전
  **실제 진행을 verify** 한다 — 파일 변경 / `tasks.md` 체크박스 전진 / plan 산출물
  중 하나라도 실제로 늘었는가. dispatch 했다는 사실만으로 "진행 중"이라 보고 금지
  (= `verification-before-completion` 정신을 진행 보고에도 적용 — 검증 안 된 낙관 보고는 주장이다).
- **autopilot stall 감지 + 즉시 surface**: `/goal` dispatch 후 손 놓지 않는다.
  주기적으로 진행(위 verify 신호)을 확인해, teammate idle·파일변경 0·태스크 전진 0 이
  지속되면 = **무진행 stall** → 자동 nudge 시도 + **사용자에게 즉시 surface**. 사용자가
  물어봐서야 멈춘 걸 발견하는 일이 없게 한다. (TeammateIdle 훅은 CTO-dispatch 된 STORE
  큐만 보므로, dispatch 자체가 STORE 에 안 들어간 무진행은 훅이 못 잡는다 — CTO 능동
  확인이 유일한 안전장치. 훅을 `tasks.md` 로 넓히지 말 것: 미dispatch 미래 phase 로
  잘못 nudge 되어 segment 1개씩 게이팅이 깨진다.)
- **1회 surface**: 앵커 충족 시 **딱 한 번** — "segment <range> 완료(증거 …)
  → [게이트] → 다음 segment 지정해주세요" — 만 사용자에게 올린다.
- **올린 뒤 = 사용자 대기 = 침묵.** TeammateIdle nudge · stale task 재dispatch
  no-op · teammate 상태 메시지가 들어와도 **다음 segment 질문을 재발행하지 않는다**
  (조용히 확인/파일만). 다음 segment 질문은 완료당 정확히 1회.
- 게이트(직전 segment 산출물 승인)·dispatch(다음 범위 지정)는 **직전 segment** 건 —
  현재 segment teammate 가 작업 중일 때 "다음 범위?" 를 묻지 않는다.

- `/goal` 은 phase3+ 전용. 게이트1·2 를 goal 로 넘기지 않는다 (RULES §8).
- `[!]` 블로커 → goal 중단 + 사용자 surface. 우회 진행 금지.
- codex 는 빌드 단계 아님 — 사용자가 CEO 창에서 직접 명령할 때만 (RULES §6).

## 4. 모듈 마감 (module 빌드 한정)

마지막 segment + 사용자 브라우저 테스트 통과 후, CTO 가
`modules/<name>/specs/USAGE.md` 를 작성한다:

```markdown
# <모듈명>      # 무엇을 하는 모듈인지 2~3줄
## 기능         # 뭘 제공하나
## 사용법       # 다른 프로젝트에 붙이는 방법
## 환경         # 필요 env, 의존성, 포트
## API          # 노출 엔드포인트/함수
```

**USAGE.md 존재 = 모듈 완성(재사용 가능) 표시.** 없으면 빌드 중 — 다른 plan 이
소비 금지 (RULES §7). 빌드 잔재(plan.md, specs/)는 그대로 둔다 (이력).
README.md 는 작성하지 않는다 (RULES §1 — 사용자 전용).

## 5. 단계·에이전트별 스킬 (고정 = 무조건 / 유동 = 시스템 판단)

### 분해 (planner)
- 고정: `writing-plans`
- +기계 검증: 커버리지 체크 자동 실행
- 유동: `plan-eng-review` / `harness-unknowns-check`

### phase1 환경설정 (developer)
- 고정: `verification-before-completion` — 완료 주장 전 증거 → 게이트1
- 유동: `run` / `investigate` / `careful`

### phase2 프론트 디자인 (designer)
- project 고정 3: `design-consultation`(open-design 디자인시스템 152개에서
  선택/참조) → `design-shotgun`(시안 보드→사용자 선택) → `design-html`(선택된
  open-design tokens.css 사용)
- module 고정 1: `design-html` (+필요시 open-design 시스템 1개 참조)
- 유동: `browse` / `design-review` / `frontend-design` / open-design 스킬들
  (`.sources/open-design/skills/` 디자인 계열)

### phase3+ 개발 (developer)
- 고정: `test-driven-development`(비즈로직, 플러밍 예외는 완료노트 명시) /
  `verify`(완료 보고 전 라이브 앱 실동작 확인)
- 유동: `run` / `systematic-debugging` / `investigate` / `simplify` / `careful`

### reviewer (CTO 판단 호출)
- 고정: `code-review`(1차 high/재리뷰 medium) / `qa-only`(report-only)
- 직접 실행 (스킬 X, 필수 임무): API 테스트(curl·pytest) + DB 무결성(SQL)
- 유동: `health` / `browse`
- 결과 = 파일 X, 보고 메시지

## 6. CTO 세션 표시 의무

- 현재 작업 중인 `phaseN.ckptN` 을 tmux 상태줄/statusline 에 상시 표시.
- 스킬 사용 표시는 `<에이전트> ★ <스킬>` 형식 (예: `developer ★ verify`).
