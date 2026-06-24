# PORT.md — 포트 레지스트리 (하드룰 4 source of truth)

> **자동 생성** — `./run.sh ports` 또는 add-cto / delete-cto 가 각 프로젝트
> 의 `.env` 를 스캔해 재생성한다. **직접 편집 금지** (재생성 시 덮어씀).
> 진실원천 = 각 프로젝트 `.env`. offset = `BACKEND_PORT − 8000`.
> MinIO 등 `.env` 에 없는 포트(docker-compose 하드코딩)는 `—` 로 나온다.
> `DB` = DB 엔진 탐지 (.env DATABASE_URL/POSTGRES → docker-compose 이미지/sqlite → sqlite 파일).
> 🐳 docker · 💻 dev.sh(backend/frontend) · ✋ down

## 현황

| 프로젝트/모듈    | offset | CTO세션   | Backend | Frontend | MTX API  | MTX HLS | MTX RTSP | MTX WebRTC | MTX ICE | PostgreSQL | DB         | Redis | MinIO API | MinIO Console | 상태      |
| ---------------- | ------ | --------- | ------- | -------- | -------- | ------- | -------- | ---------- | ------- | ---------- | ---------- | ----- | --------- | ------------- | --------- |
| tunnel           | 1      | ✋ 비활성 | 8001 🐳 | 5174 🐳  | 9998 🐳  | 8889 🐳 | 8555 🐳  | —          | —       | —          | SQLite     | —     | —         | —             | ✅ 5/5 Up |
| auth-service     | 3      | ✋ 비활성 | 8003 🐳 | 5176 🐳  | —        | —       | —        | —          | —       | 5435 🐳    | PostgreSQL | —     | —         | —             | ✅ 3/3 Up |
| rtsp-streaming   | 4      | ✋ 비활성 | 8004 🐳 | 5177 🐳  | 10001 🐳 | —       | 8558 🐳  | 8893 🐳    | 8193 🐳 | —          | SQLite     | —     | —         | —             | ✅ 6/6 Up |
| cam-distance     | 6      | ✋ 비활성 | 8006 🐳 | 5179 🐳  | 10003 🐳 | —       | 8560 🐳  | 8895 🐳    | 8195 🐳 | —          | SQLite     | —     | —         | —             | ✅ 6/6 Up |
| cosmetics-recipe | 7      | ✋ 비활성 | 8007 🐳 | 5180 🐳  | —        | —       | —        | —          | —       | —          | —          | —     | —         | —             | ✅ 2/2 Up |

## 시스템 예약 (offset 무관, 건드리지 말 것)

| 항목                  | 포트       | 비고                                                                |
| --------------------- | ---------- | ------------------------------------------------------------------- |
| 시스템 PostgreSQL     | 5432       | localhost only                                                      |
| SSH                   | 8164       | —                                                                   |
| 회사망 forward (회피) | 5175, 8005 | 라우터 포트포워딩 예약 — add-cto 가 파생 offset 자동 회피           |
| harness-dashboard     | 8165, 8166 | 웹 관리 콘솔(읽기전용 v1, dashboard/) — 외부노출은 frontend 8166 만 |

> **다음 free offset = 8**
