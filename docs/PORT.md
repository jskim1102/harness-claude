# PORT.md — 포트 레지스트리 (하드룰 4 source of truth)

> **자동 생성** — `./run.sh ports` 또는 add-cto / delete-cto 가 각 프로젝트
> 의 `.env` 를 스캔해 재생성한다. **직접 편집 금지** (재생성 시 덮어씀).
> 진실원천 = 각 프로젝트 `.env`. offset = `BACKEND_PORT − 8000`.
> MinIO 등 `.env` 에 없는 포트(docker-compose 하드코딩)는 `—` 로 나온다.

## 현황

| 프로젝트 | offset | Backend | Frontend | MTX API | MTX HLS | MTX RTSP | PostgreSQL | Redis | MinIO API | MinIO Console | 상태 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| tunnel | 1 | 8001 | 5174 | 9998 | 8889 | 8555 | — | — | — | — | 컨테이너 가동중 |
| rtsp-streaming | 2 | 8002 | 5175 | 9999 | 8890 | 8556 | — | — | — | — | .env만 |
| auth-service | 3 | 8003 | 5176 | — | — | — | 5435 | — | — | — | .env만 |

## 시스템 예약 (offset 무관, 건드리지 말 것)

| 항목 | 포트 | 비고 |
|---|---|---|
| 시스템 PostgreSQL | 5432 | localhost only |
| SSH | 8164 | — |

> **다음 free offset = 4**
