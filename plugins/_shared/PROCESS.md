# 하네스 빌드 프로세스

위치: `plugins/_shared/` (RULES.md 옆 — canonical 운영 스펙). SessionStart 가
**CTO 세션에** 주입한다. 본 문서 = CTO 빌드 운영 프로세스의 **정본**.
하드룰(git/파일/포트/인박스/충실도/autopilot 경계)은 RULES.md — 본 문서는 **흐름**.

> 모드 legend: 🤚 사용자 확인 · 🤖 goal 기반 autopilot · ⚙️ 자체 리뷰

> 역할 legend: Claude Agent Team = planner/reviewer 2명. `designer`는 독립
> designer-cto 세션(2026-07-29 분리, `harness send --to designer-cto:<name>`
> 발주 — 사용자 직접 대화도 가능). `developer`는
> 별도 `codex-cto-<name>` 세션의 Codex이며 Claude teammate가 아니다.

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
- 축3 source: `scratch` | `modules:[slug…]` | `extract:[프로젝트/기능…]` | 조합 (여럿이면 `+` 로 나열: `modules:[x] + extract:[y/기능]` — 출처 귀속은 분해 때 feature 단위 `[supplied:…]` 태그로)

`plan.md` 는 **CTO lead 가 계획 단계에 사용자와 쓰고 확정한다** (`harness-plan` 스킬;
확정 후 잠금 — RULES §19, 2026-10-15). 분해는 확정된 plan.md 만 읽는다.

## 1. 타임라인 (전체 흐름)

| 단계 | 주체 | 하는 일 | 모드 |
|---|---|---|---|
| 0 폴더 생성 | 사용자 (CEO 창) | `/build-project <name>`·`/build-module <name>` → 빈 빌드 dir (계획은 CTO 몫, 2026-10-15) | 🤚 |
| 1 스폰 | 사용자 | `./run.sh add-cto <name>` (plan.md 없음 = 계획 단계로 기동, 시작 마커 보류 / 폴더 없음 = 실패) | 🤚 |
| 1 계획 | CTO ↔ 사용자 | `harness-plan`: brief → brainstorming(축2·축3) → Library Check → 재료 분석 → `plan.md`(3축) → plan-ceo-review → "plan.md 확정할까요?" | 🤚 plan 확정 |
| 1 확정 | 훅 | 승인 답 → `plan.md` 잠금 + 시작 마커 + 카메라 포트 (`plan_readonly_gate`) | ⚙️ |
| 2 팀 대기 | CTO + planner/reviewer | 확정 턴(새 빌드) 또는 첫 턴(기존 빌드 — add-cto 가 마커 시딩)에 팀 spawn (같은 턴 사용자 요청은 spawn 후 처리); 업무는 명시적 CTO dispatch 후 시작 (designer/codex 탭은 add-cto 가 이미 준비) | 🤚 |
| 3 분해 | planner (CTO 경유) | 명시적 dispatch 후 plan.md → `specs/spec.md` + `specs/tasks.md` | ⚙️ |
| 3 구간지정 | 사용자 | `phaseN.ckptN~phaseM.ckptM` 지정 (= 분해 승인) | 🤚 |
| 3 phase1 환경설정 | Codex developer | 포트·백엔드 venv·프론트 scaffold+npm·Docker·dev.sh 준비 (실행 X) | 🤖 |
| 3 게이트1 | 사용자 | 환경설정 확인 | 🤚 |
| 3 phase2 프론트 | designer-cto → Codex developer | CTO 가 inbox 로 designer 발주 → 시안 → 사용자가 브라우저(FRONTEND_PORT 목업)로 검수·수정 지시 → 계약 확정 → Codex가 실제 프론트 코드 구현 → dev 서버 기동 | 🤖 |
| 3 phase2 (design-max) | 사용자 ↔ designer-cto → Codex developer | `specs/design-mode` 마커 시: CTO 는 "phase2 시작하세요" 안내 후 비관여 → 사용자↔designer 직접 대화(mobbin refs=구조 · brief=UI구조 · system/=비주얼 정본 · assets) → designer 가 system/ 을 DesignSync 로 push → 사용자가 Claude Design 완성 후 핸드오프 번들 회수 → designer 계약 정합 → 사용자가 CTO 에 산출물 통보 → CTO 가 Codex 발주 | 🤚 대화 |
| 3 게이트2 | 사용자 ↔ designer-cto/Codex | 라이브 디자인 루프 (브라우저) → 승인 | 🤚 대화 반복 |
| 3 phase3+ 빌드 | Codex developer | 프론트/백엔드 코드 구현 (`compose up` 은 `"docker화 해"` 시만, RULES §13) | 🤖 |
| 3 자체 검증 | CTO → reviewer | **필수** API·DB·코드 검증 → 수정 → 보고 (사용자가 segment 지정 시 "검토 필요없음" 명시한 경우만 생략) | ⚙️ |
| 3 게이트3 | 사용자 | 브라우저 실사용 테스트 → PASS=다음 segment | 🤚 |
| 마감 (module 한정) | CTO | `specs/USAGE.md` 작성 = 재사용 가능 표시 | ⚙️ |
| Codex 독립리뷰 (옵션) | 사용자 → CEO | developer Codex와 별개로 `/codex-review <name>` 또는 `/codex-protocol-review` | 🤚 |

- `[❓]` 블로커 = 어느 단계든 goal 중단 → 사용자 surface
- 🤖 구간이라도 게이트1·2·3은 `/goal` 로 통과 불가 (RULES §8) — 게이트3(사용자 브라우저 실사용)도 CTO 자가 선언 불가

## 2. 팀 spawn 후 대기 / 명시적 dispatch

`/start-project`는 planner/reviewer를 spawn하는 것만 수행한다 (`specs/tasks.md` 가
이미 있는 재개 빌드는 reviewer 만 — planner 는 1회용, RULES §17). 이 턴에는
plan.md, specs, tasks, phase, ckpt, segment를 읽거나 생성·검증하지 않는다. 필수 팀원이
준비되면 CTO는 사용자에게 상태만 보고하고 대기한다. (마커 소비 후 재스폰은 `/start-project`
타이핑을 요구하지 않고 `reviewer 스폰할까요?` 승인으로 한다 — 그 승인 턴은 spawn-only 가
아니라 스폰 후 하던 작업을 이어 간다. 정본 = harness-team-spawn "When To Spawn".) 아래 분해 절차는 사용자가 CTO에게
분해를 명시적으로 지시하고(`/decompose` 또는 자연어) CTO가 planner에게
dispatch한 뒤에만 시작한다.

### 2.1 분해 (명시적 CTO dispatch 후)

plan.md 읽고 전체 phase/ckpt 트리를 만든다 → `<빌드dir>/specs/spec.md` + `specs/tasks.md`.

**분해 공식 (고정):**
- phase1 = 환경설정 — 포트(offset→`.env`/`.env.example`/compose; self-host mediamtx 는
  `MEDIAMTX_{API,RTSP,WEBRTC,ICE_UDP}_PORT`=base+`PORT_OFFSET`, base 9997/8554/8889/8189 —
  backend/frontend 와 동일 offset 규칙, `run.sh add-cto` 또는 plan.md 확정 훅이 자동 기록·멱등)·백엔드 venv+패키지·
  프론트 scaffold(vite 등, **vite.config `server.strictPort: true` 필수** — 포트 점유 시
  자동 +1 점프가 타 프로젝트 할당 포트를 침범하는 걸 차단)+`package.json`+`npm install`→node_modules·
  Docker pull·Dockerfile(+GPU 프로젝트면 Dockerfile-gpu)·`dev.sh`(호스트 러너 — venv+vite
  detached `up`/`down`, compose `up -d`/`down` 짝)·`.gitignore`(**RULES §16** — 하네스
  산출물 `.claude/`·`plan.md`·`specs/`·`DESIGN.md`·`.source*/`·`.env` 제외. `.gitignore` 는
  이미 추적 중인 파일에 무효라 **첫 커밋 전이 유일하게 싼 시점**)·**크로스플랫폼 방어**(아래). DB 쓰는 빌드면
  migration 툴(alembic 등) 셋업 + plan 데이터모델 → **첫 migration** 작성
  (RULES §9). **작성·준비만, 컨테이너 실행 X**
  - **크로스플랫폼(Mac/Ubuntu/Windows clone 어디서나 작동) — phase1 필수 산출물:**
    - 프로젝트 루트 `.gitattributes`: `* text=auto eol=lf` + `*.sh text eol=lf`.
      Windows `git autocrlf=true` 가 셸 스크립트를 CRLF 로 체크아웃하면 리눅스 컨테이너에서
      shebang(`#!/…bash\r`)이 깨져 `no such file or directory` 로 entrypoint 사망한다
      (rtsp-streaming 2026-07-16 Windows backend 크래시루프 = 이 방어 부재가 근인).
    - 셸 entrypoint 를 `COPY`+`ENTRYPOINT` 하는 Dockerfile 은 빌드시 CR 제거
      (`RUN sed -i 's/\r$//' docker-entrypoint.sh`) — .gitattributes 를 무시한 clone
      에서도 이미지가 정상 복구되는 2중 방어. advisory 표준(RULES 하드룰 아님 — 파일 존재라
      git_guard 결정론 강제 부적합).
- phase2 = 프론트엔드 — **프론트 UI/디자인 산출물 전부 여기** (scaffold·deps 는 phase1; 디자인이든 extract든; module=단순 / project=화려).
  designer-cto 세션은 시안·디자인 시스템·구현 계약을 `DESIGN.md`와 `specs/` 아래에
  만들고 production source는 수정하지 않는다. 승인된 계약을 Codex developer가
  `[dev]` task로 실제 프론트 소스에 구현한다. 모든 production 코드는 Codex 소유다.
  extract 면 프론트 UI 추출(컴포넌트·훅·페이지)도 Codex의 `[dev]` task로 phase2에 둔다 — 백엔드 없이도 dev 서버로 **레이아웃/시안 검수** 가능 (live 데이터는 백엔드 contract 기준 phase3+). **무조건 두 번째.** phase2 **최종 ckpt = CTO의 프론트 dev 서버 기동 task**(`vite dev`, `0.0.0.0:FRONTEND_PORT`) — 이 기동을 phase3.ckpt1 로 미루는 것은 **분해 오류**(결정론 게이트 차단). phase3.ckpt1 의 풀스택 `./dev.sh up` 과 별개다.
  - **dev-form 단독 검수 경로 의무 (게이트2 전제)**: 핵심 UI 가 백엔드 데이터에 게이트되면(예: 목록 API 0행 → 진입버튼 없음 → 핵심 화면 도달불가) dev 서버 단독은 빈 껍데기가 된다. phase2 는 백엔드/compose 없이 **핵심 UI 전 경로**가 검수되도록 mock/local-state(예: dev-only `?mock` 가드)를 **내장**한다 — phase3 진입 시 제거. planner 는 이 검수경로를 phase2 ckpt **acceptance 에 명시**하고, CTO 는 게이트2 surface 전 dev-form 으로 핵심 UI 도달을 직접 확인한다.
- phase3+ = 백엔드·로직·glue — 재료(축3) **백엔드** 벤더링/추출 → glue → API/로직/DB.
  **개발·검수는 dev 서버로 (RULES §13 — docker build/compose 는 사용자 명시 시만).** 백엔드
  `uvicorn --reload`(`0.0.0.0:BACKEND_PORT`) + 프론트 `vite dev`(`0.0.0.0:FRONTEND_PORT`,
  `/api` 프록시)를 **CTO 가** 띄운다 → 코드 고치면 사용자가 **새로고침으로 즉시** 확인(컨테이너
  재빌드 불편 회피). **사용자가 언제든 내/외부 네트워크로 접속 가능해야 한다.** 이미지로만 도는
  의존(mediamtx/db 등)만 컨테이너로 띄운다. **docker build / `compose up` 은 사용자가
  `"docker화 해"` 지시할 때만** — 그 전엔 dev 서버 유지.
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
### phase1.ckpt1 포트→.env/compose · 백엔드 venv · 프론트 scaffold+npm · Docker · Dockerfile · dev.sh · .gitattributes(eol=lf) · .gitignore(RULES §16)
## phase2 — 프론트엔드 디자인
### phase2.ckpt1 <시안·디자인 계약>
- [ ] [design] <mockup/contract task>
### phase2.ckpt2 <프론트 구현>
- [ ] [dev] Codex: 승인 시안을 production frontend로 구현 | <files> | <acceptance>. Run: <cmd>
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
  planner 가 원본을 직접 읽어 추출하고(파일은 CTO 가 계획 단계에 plan §3 에 짚음, 라인 추출은
  분해 때 planner 몫), acceptance 는 기능 재진술이 아니라 **원본 대비 diff**(뭘 떼고 wire 하나).
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
   사용자 승인 뒤 CTO는 `[dev]` 범위를 same-name inbox
   (`cto:<name> → codex-cto:<name>`)로 구조화해 전달한다. Codex는 inbox를 읽은
   같은 턴에는 요약만 하고, 사용자가 Codex TUI의 다음 턴에서 명시 승인한 뒤
   실행한다(RULES §6). 완료증거/blocker는 역방향 inbox로 회신한다. 이 bridge는
   CEO나 다른 프로젝트로 연결하지 않으며 `SendMessage(developer)`도 쓰지 않는다.

   **2.1 `files` 열은 인수기준에서 역산한다** (2026-08-02 승격 — 7빌드 중 6에서 재발).
   `files` 를 "이 기능이 사는 파일" 로 적으면 인수기준을 만족할 수 없다. 인수기준을
   먼저 읽고 **그걸 충족하려면 무엇이 필요한지 거꾸로 뽑아라** — 테스트 픽스처
   (`conftest.py`), 마이그레이션, 모델/스키마, 설정 상수, 그리고 **네가 쓴 `Run:` 이
   실행되기 위한 전제**까지. 실측: rate-limit 는 데코레이터라 라우트 모듈에 있어야
   하는데 목록에 없었고, JWKS `kid` 는 발행자 `tokens.py` 를 요구했으며(둘 다
   auth-service), `docker compose exec backend pytest` 라는 Run 은 `Dockerfile` 의
   `COPY tests` 없이는 **실행 자체가 불가능**했다(cam-distance).
   - **`files` 초과는 그 자체로 위반이 아니다.** developer 가 보고하면 CTO 가
     판정한다. 범위를 지키려다 인수기준을 못 맞추는 쪽이 더 나쁘다.
   - 반대 방향도 실패다: 파일을 좁게 못박고 그 밖을 요구하는 검증 명령을 함께 주면
     developer 는 어느 쪽도 만족시킬 수 없다 (dataset-trainer 세그먼트 7: 파일을
     `training.py` 하나로 고정하고 존재하지 않는 테스트 셀렉터를 요구 →
     `147 deselected`, 왕복 1회 손실).

   **2.2 매 ckpt 완료 노트에 전체 스위트 카운트를 남긴다** (2026-08-02 승격).
   `Run:` 은 스코프 셀렉터(`pytest -k …`)여도 된다. 다만 완료 노트에는 **전체 스위트
   총계**(`pytest -q` 의 passed/failed)를 숫자로 적는다. 숫자가 단조 증가하지 않으면
   그 자리에서 멈춘다.
   근거는 반례다 — auth-service 는 스코프 Run 이 25개인데도 이 사고가 안 났다. CTO 가
   24개 체크포인트에서 전체 스위트를 돌리고 `43 → 67 → 101 → 141 → 167 passed` 로
   **기록**했기 때문이다. 반대로 dataset-trainer 는 그 기록이 없어 전체가 빨간 채로 6
   ckpt 를 지나갔고 마지막에 **132 errors** 가 한꺼번에 터졌다 — 원인은 하나였고 6
   ckpt 전에 잡을 수 있었다. 즉 문제는 스코프 셀렉터가 아니라 **전체 카운트를 기록하지
   않는 것**이다.
3. **phase1 끝** → 증거(docker ps·포트·헬스체크 + `./run.sh git-listup <name>` 출력 —
   RULES §16 A 목록이 "올라감" 에 남아 있으면 그 자리에서 `.gitignore` 수정) 들고
   🤚 게이트1 (환경설정 확인).
4. **phase2 끝** → dev 서버(hot-reload, `FRONTEND_PORT`, **`0.0.0.0` 바인딩 — RULES §5.3, 127.0.0.1 금지**) 기동 → 🤚 게이트2
   **CTO 의무 — 모든 축 예외 없음**: phase2 프론트가 끝나면 **무조건** dev 서버를
   `0.0.0.0` 으로 띄우고, 아래 **3항목**을 사용자에게 제시하며 **"접속해 디자인 시안 확인해주세요"** 를 명시 요청한다:
     1. **접속 URL 3줄 정본 양식 (2026-08-04 사용자 지시 — 보고 마지막에 무조건 이 형태로)**:
        ```
        http://192.168.0.36:<FRONTEND_PORT>/<경로>     ← LAN
        http://100.81.96.110:<FRONTEND_PORT>/<경로>    ← tailscale
        http://211.106.144.18:<FRONTEND_PORT>/<경로>   ← 외부(포워딩)
        ```
        `<경로>` = 산출물 진입점 (dev 서버면 `/`, 시안 목업이면 `/web-mock.html` 등).
        **phase2.ckpt1 시안(목업) 게이트도 동일** — 목업은 자기 `FRONTEND_PORT`
        정적 서빙(RULES §4.1)이므로 같은 3줄 양식으로 제시한다.
        내부 확인용 `http://127.0.0.1:<FRONTEND_PORT>` 는 CTO 자가검증에만 쓰고
        사용자 제시 줄에는 위 3줄을 쓴다.
     2. **방화벽 개방 명령** (LAN/외부 접속하려면 사용자가 그대로 복붙 실행):
        `sudo ufw allow <FRONTEND_PORT>` [+ 외부에서 백엔드 API/WS 직접 호출 시 `sudo ufw allow <BACKEND_PORT>`].
        **§5.3 의 `0.0.0.0` 바인딩만으론 부족 — OS 방화벽(ufw)이 inbound 를 막으므로 이 명령이 있어야 외부에서 닿는다.**
     3. **포트포워딩 포트** (인터넷 접속 시 라우터 설정): 공인IP:`<PORT>` → 사설IP:`<PORT>`, 대상 = `FRONTEND_PORT`[, `BACKEND_PORT`].
   외부접속이 필요한 **모든 포트**(프론트 + 외부에서 API/WS 직접 호출 시 백엔드)에 대해 `ufw allow` + 포워딩 포트를 빠짐없이 명시한다.
   게이트2 시각 검수를 **최종 compose 로 미루지 않는다** (extract 빌드도 동일 — 프론트가 phase2 에
   있으니 빈 껍데기가 아니라 실 UI 레이아웃이 보여야 한다).
   **게이트2 전제 (사용자 명시)**: phase2 종료 시 CTO 는 **무조건** 위 3항목(3줄 URL 양식 포함)을 제시하고,
   사용자는 그 URL 에 접속해 **프론트엔드 UI 디자인을 실제로 검수할 수 있어야** 한다. 핵심 UI 가 백엔드에
   게이트돼 빈 화면만 보이면 게이트2 불성립 — 백엔드/compose 없이 핵심 UI 전 경로가 보이도록
   mock/local-state 를 phase2 에 내장한다(§2 분해공식 참조). 사용자가 빈 화면 보고서야 패치하는 사후대응
   금지 — by-design 으로 phase2 에 들어가야 한다.
   **라이브 디자인 루프**: 사용자가 브라우저로 보며 수정사항 말함 →
   designer-cto 가 시안/계약 수정 → Codex가 production 코드 반영 → 사용자는 새로고침으로 확인 → 반복 → 승인.
   **compose 로 띄우지 말 것** (수정마다 재기동 비효율 — dev 서버만).
5. **segment 완료 시 reviewer 호출 필수** — API 테스트(curl·pytest)·DB 무결성(SQL)·
   코드 평가. 사용자의 accepted goal과 현재 working behavior가 리뷰 baseline이다.
   실제 goal·계약·데이터·보안을 깨뜨리는 BLOCKER만 승인을 차단한다. SHOULD/NIT는
   후속 제안으로 기록하며 정상 동작을 바꾸거나 승인을 차단하는 근거로 사용할 수 없다.
   BLOCKER 지적만 → `[dev]` 수정 → 재검증. SHOULD/NIT는 보고서에 남기고 후속으로
   관리한다. **생략은 사용자가 segment 지정 때 "이번
   segment 검토 필요없음" 이라고 명시한 경우에만** (그 외엔 항상 리뷰). 결정론 백스톱:
   planner 가 각 phase3+ ckpt 에 `[review]` task 를 박고, reviewer 가 그 task 를
   verify sentinel 과 함께 완료해야 ckpt 가 닫힌다 (완료게이트 훅 — RULES §8).
   segment 의 독립 `[dev]` task는 외부 Codex developer 하나가 파일 충돌 없이 처리하고, reviewer teammate 하나가 검증을 Task subagent로 병렬 실행한다. CTO는 Claude developer나 두 번째 reviewer를 spawn하지 않는다.

   **5.1 리뷰 채점표 = planner 의 인수기준 (정본: `reviewer.md` §Input Contract).**
   reviewer 는 그 ckpt task 의 `<acceptance>` 문구와 `Run:` 명령, `spec.md` 의
   `← F<n>` 라벨, `specs/decisions.md` 를 기준으로 판정한다. 일반 코드품질
   (`CODE_QUALITY.md`)은 2차 참고자료다. 모든 finding 은 근거 태그를 단다 —
   `[인수기준]` `[사양F<n>]` `[회귀]` `[범위밖]`.

   **5.2 계획 정합성 판정 (빌드 진행 중 필수 경유 — 판정자 = CTO).** `[범위밖]`
   이거나 계획과 충돌하는 발견은 reviewer 가 **CTO 에게** 물어 3택 판정을 받는다
   (계획누락 / 의도된선택 / 새요구사항). **CTO 는 판정을 거치지 않은 범위 밖
   발견을 `[dev]` 수정 task 로 만들지 않는다.**
   (2026-08-11 변경: 구 판정자였던 planner 직통 경로 폐지 — planner 는 최초
   분해와 사용자 명시 지시 외 구동 금지, RULES §17 + planner_dispatch_gate 훅.)
   판정별 처리:
   - 계획누락 → CTO 가 spec/tasks 를 직접 갱신 → `[dev]` 발주. 갱신 규모가
     재분해 수준이면 사용자에게 올린다 (planner 가동은 사용자 지시 필요)
   - 의도된선택 → 기각 + CTO 가 `decisions.md` 기록 (같은 지적 재발 방지)
   - 새요구사항 → 사용자 판단으로 surface

   **5.3 승인 동작 보호 규칙 (하드).** **사용자가 승인해서 현재 동작하는 behavior 는
   "사양과 다르다"는 지적만으로 되돌릴 수 없다.** 되돌리려면 사용자 확인이
   필요하며, 그런 발견은 `새요구사항` 으로 분류해 사용자에게 올린다. 이는
   in-team reviewer 뿐 아니라 **`/codex-review` 등 외부 리뷰 결과를 반영할 때도
   동일하게 적용**된다 (2026-07 cam-distance `enabled` · rtsp-detection fix9 사고:
   둘 다 minor/major 사양불일치 지적이 사용자 승인 동작을 뒤집어 기능이 죽었다).

   **5.4 회귀 = 최우선 BLOCKER.** 이전 ckpt 에서 통과하던 `Run:` 명령이 지금
   실패하면 다른 어떤 finding 보다 우선해 승인을 차단한다. reviewer 는 리뷰
   착수 시와 수정 반영 후 두 번 재실행해 비교한다.
6. CTO → 사용자 **자체검증 보고** (검증 증거 포함) — 이는 자체검증일 뿐, "완료" 아님(게이트3 PASS 후 완료). reviewer 결과는 **파일 X, 보고 메시지**.
7. 사용자 : 브라우저 실사용 테스트 (🤚 게이트3) → PASS = 다음 segment / FAIL = 재작업.
   **서버 노출 시점(게이트3 서버 노출(dev 서버 URL) 등 — 게이트2 뿐 아니라 사용자에게 서버 URL 을
   주는 모든 지점)에서 step4 의 3항목(**3줄 URL 정본 양식**[LAN 192.168.0.36 · tailscale 100.81.96.110 · 외부 211.106.144.18] · `sudo ufw allow <PORT>` · 포트포워딩 포트)
   형식으로 접속 정보를 제시한다.**
8. 진행 상태는 `specs/tasks.md` 체크박스만 갱신 (완료 `[✅]`, 미완 `[ ]`, 블로커 `[❓]`) — 별도 상태파일 금지. 완료는 반드시 초록 체크 `[✅]` (레거시 `[x]` 도 완료로 인식하나 신규 작성 금지), 블로커는 `[❓]` (레거시 `[!]` 도 인식하나 신규 금지).

**phase3+ dev 서버 상시 가동 (RULES §13)**: phase3 진입부터 **dev 서버**(backend
`uvicorn --reload` + frontend `vite dev`)가 **계속 떠있어야** 한다 — CTO 가 자기 Bash 에서
`./dev.sh up`(phase1 산출물 호스트 러너, `0.0.0.0` 바인딩) 으로 한 방 기동, `./dev.sh down` 으로 정지. **사용자는 phase3+ 내내 언제든** 내/외부 네트워크로 접속해 **수정사항을
새로고침으로 즉시** 확인. 이미지로만 도는 의존(mediamtx/db)만 컨테이너. **docker build /
`compose up` 은 사용자가 `"docker화 해"` 지시할 때만** — 그때부터 compose 스택을 띄우고,
상태형 의존 재기동 시 재싱크(아래) 규칙을 따른다.

**상태형 의존 재기동 = 재싱크 의무 + 핵심기능 실검증 (2026-06-22 mediamtx path 사고 정본화):**
- `compose up -d <svc>` 로 **런타임 상태를 보유한 서비스**(예: mediamtx 의 동적 path — backend 가
  API 로 등록, 컨테이너 재생성 시 소멸)를 갈아끼우면 그 상태가 날아간다. **재기동 후 dependent
  재싱크(backend 재시작/sync 호출) 또는 모듈 self-heal 로 상태 복원을 확인하기 전엔 "완료" 아님.**
  (사고: 포트 적용하려 `compose up -d mediamtx` → path 소멸 → backend 재싱크 안 함 → 스트림 죽음.)
- **검증·게이트는 부품 체크로 끝내지 않는다** — `compose config -q`·`/health 200`·포트설정 PASS ≠
  기능 동작. **핵심 사용자 기능이 실제로 동작하는지**(스트리밍이면 카메라별 path ready + 실제
  재생)를 증거로 확인한다.
- 모듈은 **각 서비스가 독립적으로 재시작돼도 자가복구(self-heal)** 되어야 한다 — 이 견고성은
  모듈 "완성" 기준이다(미충족 모듈은 재사용 시 깨진다). USAGE.md 존재 ≠ 검증완료.

**segment 완료 판정 + 1회 surface (CTO 규율 — 중복질문 방지):**
- **완료 앵커 (결정론)**: dispatch 한 segment `phaseN.ckptN~phaseM.ckptM` 는
  **범위 내 모든 ckpt 가 `[✅]`(전 task 완료) + 검증 증거 확보 + 게이트3 PASS 기록** 됐을 때만 완료다.
  ckpt `[✅]` + 검증 증거 = **CTO 자체검증 완료**(step6 = 자체검증 보고)일 뿐 — "완료" 는 사용자 게이트3
  통과 후로 예약한다. CTO 자체검증만으로 "완료" 선언 금지.
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

- `/goal` 은 phase3+ 전용. 게이트1·2·3 을 goal 로 넘기지 않는다 (RULES §8).
  게이트3(사용자 브라우저 실사용 테스트)도 `/goal` autopilot 으로 통과 불가 — CTO 가 자가 선언 불가.
- `[❓]` 블로커 → goal 중단 + 사용자 surface. 우회 진행 금지.
- **review-codex** (`/codex-review <name>`, `/codex-protocol-review`) 는 빌드
  단계가 아니다 — 사용자가 CEO 창에서 직접 명령할 때만 돈다 (RULES §6). 이는
  빌드 참여자인 **codex-cto developer**(§3 same-name bridge)와 별개다.

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

### phase1 환경설정 (Codex developer)
- 고정: 테스트/명령 증거를 남긴 뒤 완료 보고 → 게이트1

### phase2 프론트 디자인 (designer-cto → Codex developer)
- **design-max 분기** (`specs/design-mode` 마커): CTO 발주·아래 고정 스킬 체인 대신
  designer role.md "Design-Max 모드" 절차를 따른다 — 사용자 직접 대화, 산출물 =
  `specs/design/refs/`(구조 refs) + `refs-visual/`(톤 refs) + `brief.md`(UI 구조
  전용) + `sample/`(구조 스케치 — 전 화면 무채색 와이어프레임, 사용자 검수 완료) +
  `system/`(비주얼 정본 — 정본 규격 디자인시스템, DesignSync push 원본) +
  `assets/`(필요 시) + `handoff/`(사용자가 놓는 수신함). acceptance 게이트는
  designer 가 스스로 닫을 수 있는 산출물만 검사한다 — `handoff/`·`assets/` 는
  존재 자체를 게이트로 걸지 않는다. CTO 는 사용자 통보 후에만
  Codex 발주. 게이트2(dev 서버 3줄 URL 검수)는 동일하게 적용.
- project 고정 3: `design-consultation`(open-design 디자인시스템 152개에서
  선택/참조) → `design-shotgun`(시안 보드→사용자 선택) → `design-html`(선택된
  open-design tokens.css 사용)
- module 고정 1: `design-html` (+필요시 open-design 시스템 1개 참조)
- 유동: `browse` / `design-review` / `frontend-design` / open-design 스킬들
  (`.sources/open-design/skills/` 디자인 계열)
- designer-cto 는 시안/계약만(발주·보고는 harness inbox), Codex는 production frontend 코드와 테스트를 담당.

### phase3+ 개발 (Codex developer)
- 비즈니스 로직 TDD, 완료 전 관련 테스트와 라이브 동작 증거 필수.

### reviewer (segment 완료 시 필수 호출)
- 고정: `code-review`(1차 high/재리뷰 medium) / `qa-only`(report-only)
- 직접 실행 (스킬 X, 필수 임무): API 테스트(curl·pytest) + DB 무결성(SQL)
- 유동: `health` / `browse`
- 결과 = 파일 X, 보고 메시지
- 병렬: 독립 검증 항목이 여러 개여도 reviewer teammate 는 1명 — Task subagent 로 fan-out 후 findings 를 한 SendMessage 로 aggregate.

## 6. CTO 세션 표시 의무

- 현재 작업 중인 `phaseN.ckptN` 을 Claude statusline 에 상시 표시.
- Claude 스킬 사용 표시는 `<에이전트> ★ <스킬>` 형식 (예: `designer ★ design-html`).
