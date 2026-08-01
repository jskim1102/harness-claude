# PORT.md — 포트 레지스트리 (하드룰 4 source of truth)

26.06.24

> **자동 생성** — `./run.sh ports` 또는 add-cto / delete-cto 가 각 프로젝트
> 의 `.env` 를 스캔해 재생성한다. **직접 편집 금지** (재생성 시 덮어씀).
> 진실원천 = 각 프로젝트 `.env`. offset = `BACKEND_PORT − 8000`.
> MinIO 등 `.env` 에 없는 포트(docker-compose 하드코딩)는 `—` 로 나온다.
> `DB` = DB 엔진 탐지 (.env DATABASE_URL/POSTGRES → docker-compose 이미지/sqlite → sqlite 파일).
> 공유 pg = 단일 인스턴스(127.0.0.1:5435), 프로젝트 구분은 database 이름(db-per-project). PostgreSQL 열은 공유 프로젝트면 자기 컨테이너 포트가 없어 `공유→db명` 으로 표기.
> MTX API/RTSP/TCP/UDP = 각 카메라 프로젝트가 자기 mediamtx 를 base+offset 로 self-host (9997/8554/8889/8189 + offset, .env MEDIAMTX_*_PORT). 공유 mediamtx 는 폐지됨(2026-07-18).
> 🐳 docker · 💻 dev.sh(backend/frontend) · 🔗 공유 인프라 · ✋ down

## 현황

| 프로젝트/모듈  | offset | CTO세션   | Backend | Frontend | MTX API  | MTX RTSP | MTX TCP | MTX UDP | PostgreSQL | DB         | Redis | MinIO API | MinIO Console |
| -------------- | ------ | --------- | ------- | -------- | -------- | -------- | ------- | ------- | ---------- | ---------- | ----- | --------- | ------------- |
| rescue-pose    | 1      | ✋ 비활성 | 8001 💻 | 5174 💻  | 9998 🐳  | 8555 🐳  | 8890 🐳 | 8190 🐳 | —          | SQLite     | —     | —         | —             |
| auth-service   | 3      | ✋ 비활성 | 8003 ✋ | 5176 ✋  | —        | —        | —       | —       | 5435 🔗    | PostgreSQL | —     | —         | —             |
| rtsp-streaming | 4      | ✋ 비활성 | 8004 ✋ | 5177 ✋  | 10001 ✋ | 8558 ✋  | 8893 ✋ | 8193 ✋ | —          | SQLite     | —     | —         | —             |
| cam-distance   | 6      | ✋ 비활성 | 8006 ✋ | 5179 ✋  | 10003 ✋ | 8560 ✋  | 8895 ✋ | 8195 ✋ | —          | SQLite     | —     | —         | —             |
| bulk-receipe   | 7      | ✋ 비활성 | 8007 💻 | 5180 💻  | —        | —        | —       | —       | —          | —          | —     | —         | —             |
| rtsp-detection | 8      | ✋ 비활성 | 8008 ✋ | 5181 ✋  | 10005 ✋ | 8562 ✋  | 8897 ✋ | 8197 ✋ | —          | SQLite     | —     | —         | —             |
| rtsp-keypoint  | 9      | ✋ 비활성 | 8009 ✋ | 5182 ✋  | 10006 ✋ | 8563 ✋  | 8898 ✋ | 8198 ✋ | —          | SQLite     | —     | —         | —             |
| dataset-viewer | 10     | ✋ 비활성 | 8010 ✋ | 5183 ✋  | —        | —        | —       | —       | 5435 🔗    | PostgreSQL | —     | —         | —             |

## 시스템 예약 (offset 무관, 건드리지 말 것)

| 항목                      | 포트       | 비고                                                                                                                                           |
| ------------------------- | ---------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| 시스템 PostgreSQL         | 5432       | localhost only                                                                                                                                 |
| 공유 PostgreSQL (harness) | 5435       | 전 프로젝트 공용 단일 인스턴스 · db-per-project · 127.0.0.1 전용 · infra/docker-compose.postgres.yml (컨테이너망 harness-shared-postgres:5432) |
| SSH                       | 8164       | —                                                                                                                                              |
| 회사망 forward (회피)     | 5175, 8005 | 라우터 포트포워딩 예약 — add-cto 가 파생 offset 자동 회피                                                                                      |
| harness-dashboard         | 8165, 8166 | 웹 관리 콘솔(읽기전용 v1, dashboard/) — 외부노출은 frontend 8166 만                                                                            |

> **다음 free offset = 11**
