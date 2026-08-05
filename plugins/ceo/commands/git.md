---
description: 빌드/하네스 git 관리 — 상태 확인은 항상, commit·push 는 사용자 명시 지시가 있을 때만 (RULES §1). Usage: /git <build|harness> [status|commit|push]
argument-hint: <build|harness> [status|commit|push]
---

빌드 저장소(`claude-project/*`, `modules/*` 의 own `.git`) 또는 하네스 루트 저장소의
git 을 안전 절차로 관리한다. 대시보드 Git 탭(stage/stage취소/commit/remote/push 버튼)과
**같은 동작의 대화형 경로**다 — 사용자는 버튼을, CEO 는 이 절차를 쓴다.

## 절차

1. **대상 결정** — `$0` = 빌드명(kebab) 또는 `harness`(루트). 빌드명이면
   `claude-project/<name>` → `modules/<name>` 순으로 해석. own `.git` 없으면
   "진행중 빌드 — 부모(하네스) 저장소 소속" 이라고 보고하고 끝.

2. **상태 (항상 실행, 읽기전용)**
   - 빌드: `./run.sh git-listup <name>` — "올라감/안올라감" 이 정본 정의.
   - 하네스: `git status --short` + `git log --oneline -3`.
   - **경계 검사 (RULES §16)**: 올라감 목록에 `.sources/`·`.source/`·`specs/`·
     대용량 데이터셋이 보이면 **commit 전에 `.gitignore` 부터** — doctor[9] 가 잡는
     위반을 커밋으로 박제하지 않는다.
   - dirty 카운트는 대시보드 노드의 빨간 링과 같은 수치다 (`git status --porcelain` 줄 수).

3. **commit — 사용자 명시 지시가 이번 대화에 있을 때만 (RULES §1)**
   - 지시 없으면 상태 보고까지만 하고 멈춘다. "커밋하는 게 좋아보임" 자체 판단 금지.
   - stage: `git add -A` 전에 2번 경계 검사 통과 확인. 원치 않는 경로가 섞이면
     `git reset` (인덱스만 — 작업트리 무변경) 후 `.gitignore` 정리, 다시 stage.
   - 메시지 컨벤션: 하네스 루트 = `vX.Y.Z [YYMMDD] - 한 줄 요약` (기존 로그 스타일).
     빌드 = 짧은 서술형 한 줄.
   - 실행: `HARNESS_USER_OK=git git commit -m "..."` — 마커는 사용자 지시가 이번
     대화에 실재할 때만 붙인다 (지시 없이 붙이는 것 자체가 §1 위반).

4. **push — 역시 사용자 명시 지시만**
   - `git remote -v` 로 origin 확인. 없으면 사용자에게 주소를 받아 `git remote add`.
   - upstream 없으면 `-u origin <branch>`. force-push 금지 (§1).
   - 실행: `HARNESS_USER_OK=git git push ...`.

## 금지

- **대시보드 API 를 curl 로 호출하지 않는다** — `.env` 의 DASH_TOKEN 으로 mutation
  엔드포인트를 때리는 것은 git_guard §1 우회다 (2026-07-31 결정: 버튼은 사용자 것,
  에이전트는 git CLI + 마커 경로만).
- README 생성 금지 (§1 — README 는 사용자가 쓴다).
- `git reset --hard`·rebase·`checkout --`·tag·`gh pr` 금지 (§1 목록 그대로).
- 다른 CTO 가 빌드 중인 저장소는 건드리지 않는다 — 상태 보고만.
