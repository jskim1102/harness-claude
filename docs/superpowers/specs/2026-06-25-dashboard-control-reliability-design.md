# 대시보드 컨트롤 신뢰성 강화 (Approach A: 의도고정 + 멱등 + 검증)

> **Historical design record.** 이 문서는 Orca 전환 전 dashboard 제어면의
> tmux 상태를 분석한 기록이다. 현재 CTO lifecycle은 Orca terminal API와
> `run.sh stop-cto/add-cto`가 정본이다. 아래 tmux 명령·가정은 현재 운영 지침이 아니다.

작성: 2026-06-25 · 대상: harness-claude 대시보드 제어 플레인

## 배경 / 문제

대시보드 mission control 의 프로젝트 제어 버튼 3개 — **CTO 세션 / dev 서버 / docker** —
를 사용자가 여러 번 눌렀을 때 시스템이 일관되지 않은 상태에 빠졌다.

구체 사고 (tunnel, 2026-06-25 dashboard backend access log):
```
POST /api/cto/tunnel/stop  200 OK   ← 사용자 종료 클릭. tmux cto-tunnel 죽음.
POST /api/cto/tunnel/start 200 OK   ← 그 직후 start 가 눌려 세션 부활.
```

원인은 "버튼이 안 먹힘"이 아니다. 각 버튼의 동작 자체는 맞다. 진짜 원인:

1. **토글 라벨 뒤집힘 + 연타.** 버튼은 상태에 따라 `종료`/`실행` 라벨이 바뀐다
   (App.jsx `s.on ? '종료' : '실행'`). `종료` 클릭 → stop → refresh → `cto_active=false`
   → 라벨이 `실행`으로 뒤집힘 → 연타/confirm-OK 연타 → START → 부활.
2. **잠금 타이밍.** `setBusy('')` 가 `refresh()` 완료 **전**에 실행되어, 상태(라벨)가
   stale 인 채 버튼이 재활성화되는 창이 생긴다.
3. **busy 가 전역 단일 문자열** (`'cto'|'dev'|'docker'`) — 프로젝트별이 아니라 교차오염.
4. **백엔드 `ok` 의 의미가 약함.** `ok = (returncode==0)` = "명령이 실행됨"이지
   "목표 상태에 도달함"이 아니다. 검증이 없어 거짓 성공을 UI 에 보고한다.
5. **멱등성 없음 / 프로젝트별 lock 없음.** 동일 프로젝트에 빠른/동시 요청이 들어오면
   상태 추론(toggle)과 액션이 인터리브된다.

## 목표 / 비목표

**목표:** 버튼 3개를 그대로 유지하면서, **연타·동시요청에도 일관된 결과**를 보장한다.
각 버튼: 클릭=의도고정 → 전체 사이클 잠금 → 멱등 실행 → 끝상태 검증 → UI는 검증된 진실 반영.

**비목표 (YAGNI):**
- 버튼 추가 / 의미 변경 안 함.
- desired-state endpoint 재설계 안 함 (toggle 유지).
- CTO-stop 이 dev 서버까지 끄게 만들지 않음 — 3버튼 독립 유지.

## 컴포넌트별 설계

### A. 프론트엔드 — `dashboard/frontend/src/App.jsx`

현행: `busy` 전역 문자열, `setBusy` 가 confirm 이후·refresh 이전에 토글됨
(`ctoToggle` L680, `devToggle` L691, `dockerToggle` L699; 버튼 render L800-804).

변경:
1. **busy 를 (프로젝트,컨트롤)별 키로.** 전역 `'cto'` → `` `${it.name}:cto` `` 형태(또는 Set).
   버튼 `disabled` 판정도 해당 키로. 한 프로젝트의 한 버튼만 잠긴다.
2. **잠금을 전체 사이클로 확장.** `setBusy(''); refresh()` →
   `await refresh(); setBusy('')`. 상태가 정착하기 전엔 라벨이 뒤집히지 않는다.
3. **액션 후 쿨다운 (~800ms).** refresh 완료 후에도 그 버튼을 짧게 disabled 유지 →
   연타 후속 클릭과 confirm-OK 연타를 삼킨다.
4. **검증된 상태로 즉시 갱신.** 버튼 라벨/색은 백엔드가 반환한 실제 끝상태를 반영
   (refresh 폴링과 별개로 응답 body 의 상태를 우선 적용).
5. **lock 충돌 응답 처리.** 백엔드가 `{ok:false, busy:true}` 반환 시 "진행중" 토스트.

### B. 백엔드 — `dashboard/backend/main.py`

엔드포인트는 sync `def` (FastAPI threadpool 에서 실행) → `threading.Lock` 으로 직렬화 가능.

1. **프로젝트별 lock.** 모듈 레벨 `dict[str, threading.Lock]`. 모든 mutation
   (`cto_start`/`cto_stop`/`dev_toggle`/`docker_toggle`) 진입 시 해당 프로젝트 lock
   을 **non-blocking acquire**. 실패(점유중)면 즉시 `{ok:False, busy:True, "error":"진행중"}`.
2. **멱등 가드 + 끝상태 검증** (각 엔드포인트):

   - **`cto_start` (add-cto)** — `tmux has-session -t cto-<name>` 이 이미 있으면
     run.sh 호출 없이 no-op 성공. 없을 때만 `add-cto`. 후 `has-session` 재확인 →
     실제 `cto_active` 반환.
   - **`cto_stop` (stop-cto)** — 세션 있으면 `stop-cto`, 없으면 no-op 성공.
     후 `has-session == false` 검증 → 실제 상태 반환.
   - **`dev_toggle`** — 현행대로 fresh 서버 상태로 방향 결정. `down` 후 백/프론트
     포트가 여전히 listen 이면 **port/dir kill 폴백** (`run.sh _kill_project_processes`
     패턴: cmdline `pkill -f <dir>` + cwd 매치). 후 포트 listen 여부 재확인 →
     실제 `dev_up` 반환. `up` 은 미listen 일 때만 `dev.sh up`.
   - **`docker_toggle`** — `down` 을 `docker compose down **--remove-orphans**` 로
     (스테일/orphan 컨테이너까지 — 2026-06-12 rtsp 부활 사고 대비). `up` 은 현행
     detached 빌드 유지(요청 블록 X). down 후 컨테이너 gone 검증.

3. **응답 계약.** `ok` 는 **"목표 상태 도달"**을 의미한다. 끝상태 미달
   (예: down 후 포트 still up, kill 폴백도 실패) → `{ok:False, msg}` 반환 → UI 빨강.
   거짓 성공 금지.

### C. run.sh

- `_kill_project_processes` (L532) 는 이미 존재 — dev `down` 폴백에서 재사용
  (직접 호출 또는 동일 로직). $REPO 하위 빌드 dir 안전핀 그대로.
- `stop-cto` / `add-cto` 동작 자체는 변경 없음 — 멱등 가드는 백엔드 레이어에서.

## 에러 처리

| 상황 | 동작 |
|---|---|
| lock 점유중 재요청 | `{ok:False, busy:True}` → UI "진행중" 토스트, 액션 무시 |
| 액션 실행됐으나 끝상태 미달 | `{ok:False, msg}` → UI 빨강(실패), 거짓 green 금지 |
| 네트워크/타임아웃 | 현행 mutate() 처리 유지 |

## 테스트 (검증 기준)

1. **사고 재현 테스트:** 한 프로젝트 CTO `종료` 직후 즉시(쿨다운 내) 재클릭 →
   세션 부활 안 함. (프론트 쿨다운 + 백엔드 멱등 둘 다 검증)
2. **백엔드 멱등 단위:**
   - 이미 stopped 상태에 `cto_stop` → `ok:True`, 세션 없음 유지.
   - 이미 running 상태에 `cto_start` → 중복 spawn 없음 (`has-session` 1개).
   - `dev_toggle down` 후 백/프론트 포트 free 검증.
3. **lock:** 동일 프로젝트 동시 2요청 → 하나는 `busy:True`.
4. **smoke:** `tests/smoke.sh` 에 대시보드 컨트롤 멱등 케이스 추가 검토.

## 영향 범위 (변경 파일)

- `dashboard/frontend/src/App.jsx` — busy 키/잠금/쿨다운/검증상태 반영.
- `dashboard/backend/main.py` — 프로젝트별 lock, 멱등 가드, 끝상태 검증, 응답 계약.
- `run.sh` — 변경 없음 (`_kill_project_processes` 재사용). 필요 시 dev down 폴백 훅만.
- `tests/smoke.sh` — 컨트롤 멱등 케이스 (선택).

## 구현 상태 (2026-06-25, 구현 완료 — uncommitted)

**`dashboard/backend/main.py`:**
- `import time / threading`, `from contextlib import contextmanager` 추가.
- `_proj_lock`/`_hold` (프로젝트별 non-blocking lock), `_cto_alive` (tmux has-session),
  `_BUSY` 추가. 4개 mutation 전부 `_hold` 로 래핑 (점유중 → `_BUSY`).
- `cto_start`/`cto_stop`: `_cto_alive` 로 멱등(이미 목표상태면 no-op) + 액션 후 재확인 →
  `ok`="세션 실제 상태 도달", `cto_active` 반환.
- `dev_toggle`: down 시 `_free_ports`(fuser TERM→KILL) + 포트 free 검증 (먼저 적용됨).
- `docker_toggle`: down 에 `--remove-orphans`.

**`dashboard/frontend/src/App.jsx`:**
- `busy` 를 `` `${name}:${control}` `` 키로 (전역 단일문자열 → 프로젝트·컨트롤별).
- 핸들러: `setBusy('')` 를 `await refresh()` **이후** + `cooldown()`(800ms) 뒤로 →
  라벨 뒤집힘/연타 차단. docker 는 빌드(`waitDocker`) 끝까지 busy 유지.
- 버튼 `disabled`/라벨도 `` `${sel.name}:${s.key}` `` 비교.

**검증:**
- dev 버튼: 라이브 — tunnel :8001 (orphan) 실제 종료 확인.
- 단위: lock 직렬화(2nd=busy)+해제+프로젝트독립, `_cto_alive('tunnel')==False`(ground truth) 통과.
- 구문: backend `py_compile` OK + uvicorn reload 클린, frontend esbuild 파싱 OK + vite HMR.

미적용(선택): `tests/smoke.sh` 멱등 케이스.
