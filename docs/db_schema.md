# DB (Supabase / Postgres 17, 도쿄 ap-northeast-1) — 2026-09-24

- 스키마: `supabase/migrations/20260924000000_init.sql` — **적용 완료** (`python3 scripts/db/migrate.py`, 기록은 `_migrations`)
- 접속: `.env` 의 `SUPABASE_DB_{HOST,PORT,NAME,USER,PASSWORD}` (Session pooler, IPv4). Data API(PostgREST)는 꺼져 있고 모든 테이블 RLS 켬·정책 없음
- 무료 플랜 NANO: max_connections 60, shared_buffers 224MB, DB 500MB. 장소 37만 곳은 DB 에 넣지 않고 서버 파일로 둔다

## 테이블

| 구분 | 테이블 | 탈퇴·게스트 30일 만료 (`forget_user`) |
|---|---|---|
| 개인 데이터 | users(actor 포함), profiles, trip_state, messages(발화 원문), spots, visits, saved, user_feedback, usage_daily | 삭제 |
| 행동 로그 | trips, **turn_logs**, **reaction_logs** | 남김 (actor 로만 묶임 → 익명). turn_logs.query 는 null, 위치는 geohash 4자리로 |

### turn_logs — 대화(추천) 한 번 = 한 줄
`id, actor, trip_id, turn_no, source(chat|chip), query, intent, context, candidates, answer, llm, versions, latency_ms, created_at`
- intent: 파서 + 프로필로 채운 최종 조건
- context: `{area_geo(geohash6), location_method, radius_km_asked, radius_km_used, n_candidates, trace, notes, personalization_w}`
- candidates: 보여준 목록 `[{rank, place_id, slot, score, pop, taste, dist_m, flags}]`
- llm: `{model, prompt_version, input_tokens, cached_tokens, output_tokens, latency_ms, status}`
- versions: `{ranker, items, variant}`

### reaction_logs — 반응 한 번 = 한 줄
`id(증가), turn_id, actor, trip_id, place_id, rank, type, props, created_at`
type: card_open, map_open, pin_click, select, directions_open, save, unsave, skip, share, wiki_open, rate, mark_visited

### 뷰 v_candidate_outcomes — 보여준 후보 1개 = 1행 + selected/saved/skipped/opened (학습 데이터)

## 로컬로 내려받기 (`scripts/db/export_logs.py`, 설정 `config/export_logs.json`)
- 기본은 reaction_logs 만 (turn_logs 는 설정에서 `enabled: true`)
- 커서(`data/logs_export/_state.json`)로 이어받기: 마지막으로 받은 행 뒤부터
- 출력: `data/logs_export/{table}/date=YYYY-MM-DD/part-{첫커서}-{끝커서}.jsonl.gz`, `_manifest.jsonl`, `_export.log`
- 장애 대처 (2026-09-24 실제 DB 로 확인)

| 상황 | 동작 | 확인 결과 |
|---|---|---|
| 새 행 추가 후 재실행 | 새 행만 받음 | 12행 → +3행 → +4행 → +2행, 파일 6개·21행·중복 0 |
| 파일 쓴 뒤 커서 저장 전에 죽음 | 같은 범위를 같은 파일 이름으로 덮어씀 | 중복 0 |
| 커서 파일 깨짐 | `.bak` 로 복구 (한 배치 다시 받아 덮어씀) | 중복 0 |
| 동시 실행 | 잠금 → 종료 코드 2 | 확인 |
| 연결 끊김·타임아웃 | 지수 백오프 재연결, 같은 커서부터 | — |
| 비밀번호·권한 오류 | 재시도 없이 실패, 커서 유지, `last_error` 기록 | 확인 |
| 늦게 커밋된 행 | 만든 지 120초 지난 행만 받음 (`safety_lag_seconds`) | — |

## 게스트 만료
- pg_cron 이 매일 04:00 KST 에 `purge_expired()` 실행 (`20260925010000_purge_cron.sql`)
