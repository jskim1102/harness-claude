# /decompose --design (design-max 모드) 설계 (2026-08-05)

사용자 확정. 이 문서가 design-max 모드의 정본이다. 일반 `/decompose` 는 현행 유지
— 이 설계는 **별도 신설 모드**이며 기존 경로를 교체하지 않는다.

## 배경 / 문제

- 현행 phase2 (일반 모드): lead-CTO 가 inbox 로 designer-cto 발주 → designer 가
  시안(목업 HTML/CSS) + 구현계약(md) 산출 → lead 경유 Codex 구현. **유지.**
- `designer-cto/role.md` §"Claude Design 미세조정 루프" 는 2026-07-29 설계 때
  글로만 박힌 미실행 계약 — 실빌드(perf-eval-gen 등)는 전부 폴백(standalone
  HTML)으로만 돌았다. 이번 범위 밖 (건드리지 않음).
- 사용자 요구: 디자인 품질이 중요한 빌드에서 **사용자가 designer-cto 와 직접
  대화**하며 mobbin 레퍼런스 기반 초안을 만들고, **Claude Design**(claude.ai/design
  앱)으로 완성한 뒤 하네스로 되가져오는 흐름. lead-CTO 는 비관여.

## 실측으로 확정된 제약 (2026-08-05 라이브 검증)

| 사실 | 근거 |
|---|---|
| Claude Design 본체(Projects 탭·캔버스)는 도구로 접근 불가 | DesignSync 는 Design systems 탭 전용. 사용자 실 프로젝트가 `list_projects` 에 안 뜸(빈 목록) |
| mobbin 페이지 직접 fetch 불가 | WebFetch 403 (로그인 벽) |
| mobbin MCP 검색 = 스크린샷 인라인 수신 | `search_flows/screens/sections` 3툴, 실호출 성공 |
| MCP 스크린샷 파일 저장 가능 | `mobbin.com/api/mcp/short/<id>` curl 200, 인증 불필요, 768px webp 실이미지. 서명 URL 이라 검색 직후 저장 |
| gpt-image-1 이미지 생성 동작 | 키 `~/.harness-claude/openai.env`(600), 저품질 1024px 실호출 성공, ≈$0.011/장 |
| Claude Design 디자인시스템 입력 = 전부 optional | 생성 다이얼로그: GitHub/로컬폴더/.fig/이미지/폰트·로고/노트. 이미지 1장으로도 풀세트 생성 (영상 실증) |
| Claude Design → 코드 회수 경로 존재 | Share → "Hand off to Claude Code": 구현 프롬프트 + `_ds/<system>/tokens/*.css`(fonts·motion·radius·spacing·typography) + assets 파일 번들 |

참고 영상: youtube T96O8dTzi2Q (브리프 md → 노시스템 생성=generic → 레퍼런스
이미지로 디자인시스템 생성 → attach 후 재생성=품질 급상승 → Claude Code 핸드오프).

## 확정 플로우

```
[사전] planner 분해 시 /decompose --design → specs/design-mode 에 "design-max" 마커
       (현행 decompose.md 그대로) + phase2 [design] task 는 아래 산출물 계약으로 생성

phase2 진입
1. lead-CTO: 사용자에게 "phase2 시작하세요 (design-max — designer 탭에서 진행)"
   한 줄 안내 후 비관여 대기. inbox 발주 없음.
2. 사용자 ↔ designer-cto 직접 대화 (attach-designer-cto 탭):
   a. 레퍼런스 확정 — 두 경로:
      A) designer 가 mobbin MCP 검색 → 스크린샷 후보 제시 → 사용자 pick
      B) 사용자가 mobbin URL 제시 → designer 가 URL 에서 앱이름 추출 → MCP 검색
         역매칭 → 스크린샷 "이 화면 맞아?" 컨펌
      → 확정 즉시 curl 로 이미지 파일 저장 (서명 URL 만료 대비)
   b. designer 초안 제작 (아래 산출물 계약)
3. 사용자: Claude Design 에서 완성 (하네스 밖, 사용자 작업)
   a. refs/ + assets/ 이미지로 디자인시스템 생성 (프로젝트명 = 빌드명)
   b. brief.md 첨부해 implement + 디자인시스템 attach
   c. 캔버스/Tweaks 로 미세조정
4. 사용자: Share → Hand off to Claude Code 번들(export) 확보 →
   빌드 dir 의 specs/design/handoff/ 에 두거나 designer 에게 전달
5. designer-cto: 번들을 하네스 산출물로 정합
   - tokens css → 구현계약(web-contract.md 상당)에 반영
   - handoff HTML/프롬프트 → 컴포넌트·레이아웃 계약으로 번역
   - tasks.md 의 [design] 행 [✅] 체크
6. 사용자 → lead-CTO: "디자인 확정, 산출물 <경로>" 통보 (= 복귀 트리거)
7. lead-CTO: Codex 에 프론트 구현 발주 → 이후 일반 플로우 (dev 서버 → 게이트2)
```

복귀 트리거 = **designer 완료 + 사용자 확인** (사용자가 lead 에 직접 알림).
lead 는 inbox 본문 자동실행 금지(RULES §6) 그대로 — 사용자 발화가 착수 신호.

## designer 초안 산출물 계약 (specs/design/ 아래)

```
specs/design/
├── refs/       ① mobbin 레퍼런스 이미지 팩 (검색→curl 저장, webp/png)
├── brief.md    ② 상세 브리프 — 페이지 구조·컴포넌트·인터랙션·수용기준
│               + 레퍼런스 매핑 ("로그인 폼 구조 = refs/ig-login.png 우측" 식)
│               + 생성자산 매핑 ("히어로 이미지 = assets/hero-people.png")
├── assets/     ③ AI 생성 콘텐츠 이미지 (gpt-image-1) — 레퍼런스에서 재사용
│               불가한 사진·일러스트 대체물. 키 없으면 스킵(①②만으로 진행)
└── handoff/    (3~4단계 후) Claude Design 핸드오프 번들 — tokens css + html
```

- ①: 디자인시스템 생성 입력. ②: implement 입력. ③: 디자인시스템 visual asset
  또는 implement 첨부 (인스타 로그인 예: 우측 폼=레이아웃 계약②, 좌측 사진=③).
- ③ 호출: `source ~/.harness-claude/openai.env` 후 `/v1/images/generations`
  (model gpt-image-1). 품질 기본 low(초안)·필요시 medium. 키 부재/크레딧 소진 시
  degrade — ①② 만으로 진행하고 brief.md 에 "자산 생성 대기" 표기.

## 역할 경계 (불변)

- designer-cto: 시안·계약·refs/assets 생성. production 소스 금지 (현행 유지).
- 사용자: Claude Design 조작 전담 (도구 접근 불가 영역), pick/컨펌/통보.
- lead-CTO: phase2 시작 안내 + 복귀 후 Codex 발주만. 중간 비관여.
- Codex: handoff tokens/계약 기반 production 프론트 구현.
- 게이트2 (dev 서버 3줄 URL 검수)는 현행 그대로 — design-max 여도 면제 없음.

## 구현 변경 목록

| # | 파일 | 변경 |
|---|---|---|
| 1 | `plugins/cto/commands/decompose.md` | `--design` 절의 "강화 내용 미정" 문구를 본 설계 요약으로 교체 (마커 기록은 유지) |
| 2 | `plugins/designer-cto/role.md` | "design-max 모드" 절 신설: specs/design-mode 마커 확인 → 위 초안 산출물 계약 + mobbin 검색/저장 + gpt-image-1 절차. 기존 미실증 "Claude Design MCP push" 절은 이번 범위 밖(별도 정리 항목으로 docs/LATER.md 에 기록) |
| 3 | `plugins/_shared/PROCESS.md` | phase2 행에 design-max 분기 1줄 추가 (마커 존재 시 위 플로우) |
| 4 | `plugins/cto/role.md` 또는 lead 절차 문서 | design-max 시 "phase2 시작하세요" 안내 + 비관여 + 사용자 통보로 복귀 규칙 |
| 5 | (선택) `plugins/designer-cto/` 스크립트 | gpt-image-1 호출 헬퍼 (curl 래퍼, quality/size 인자) — 최소 구현 |

스모크/게이트 추가 없음 (플로우가 사용자 주도라 결정론 검증 지점이 마커 파일
존재 여부 정도 — 과잉 게이트 금지).

## 인프라 전제 (완료 상태)

- mobbin MCP: user 스코프 등록 + OAuth 인증 완료 (2026-08-05). designer 세션에서
  1회 동작 확인 필요 (첫 실사용 때).
- OpenAI API: 키 발급(Images Request + List models Read, Owned by You),
  `~/.harness-claude/openai.env` 저장(600), 크레딧 충전, 실호출 검증 완료.
  구키 폐기 사용자 확인 필요.

## 미해결 / 후속

- stall 오탐 근본원인(사용자-대기 억제): STALL_SEC 300→1200 완화 적용(2026-08-05,
  harnessd 재시작 대기). design-max 대기가 길어 재발 시 awaiting-peer 확장 검토.
- role.md 의 죽은 "Claude Design MCP push" 계약 정리 — 별도 건.
- mobbin MCP 가 designer-cto 세션(--dangerously-skip-permissions)에서 인증
  공유되는지 첫 실사용 때 확인. 실패 시 CEO 세션에서 재인증 절차 안내.
