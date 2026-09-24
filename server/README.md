# 서버 (FastAPI + 정적 프론트)

추천 로직은 `../src/japan_rec` 를 그대로 쓴다. 설계: `../docs/web_design.md`, DB: `../docs/db_schema.md`, 배포: `../docs/deploy_cloudrun.md`

## 로컬 실행
```bash
pip install -r requirements.txt
cd server && uvicorn app.main:app --port 8000     # http://localhost:8000
```
필요한 데이터 (`../docs/pipeline.md` 로 생성): `data/processed/items_japan.json`, `data/interim/osm_stations_jp.json`, `data/geoip/dbip-country-lite.mmdb`(없으면 국가 기록만 빠짐)

## 환경변수 (프로젝트 루트 `.env`, 배포는 `../deploy/env.example`)
| 이름 | 설명 |
|---|---|
| SUPABASE_DB_{HOST,PORT,NAME,USER,PASSWORD} | Supabase Session pooler 접속 (필수) |
| OPENAI_API_KEY, OPENAI_MODEL | 파서 LLM (기본 gpt-5-mini). 키가 없으면 키워드 규칙 파서 |
| SESSION_SECRET | 쿠키 서명 (배포 시 필수) |
| BASE_URL | 예: https://trip.seongjae.dev (secure 쿠키·Google 콜백 기준) |
| GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET | 없으면 게스트 로그인만 (`openid` 범위만 요청 → 이메일 안 받음) |
| DAILY_CHAT_LIMIT | 사용자별 하루 대화 횟수 (기본 100) |
| APP_ENV | turn_logs 에 남는 환경 (dev / prod) |
| LLM_MOCK=1 | 부하 테스트용: LLM 대신 규칙 파서 + 1.5~2.5초 지연 |

## API
- `POST /api/auth/guest`, `GET /auth/google/login`, `POST /api/auth/logout`, `GET/DELETE /api/me`
- `POST /api/chat {message, lat?, lon?}` → `{reply, summary, cards[8], radius_km, notes, current, turn_id}`
- `POST /api/recommend {category?, theme?}` (칩, LLM 없음)
- `POST /api/location {lat, lon, name?, kind?}` 또는 `?query=교토역`, `GET /api/geo/starts`, `GET /api/geo/search?q=`
- `GET /api/places/{id}`, `POST /api/places/{id}/feedback {event: select|save|unsave|skip}`, `POST /api/log {type, place_id}`
- `GET /api/me/lists`, `PATCH /api/me/visits/{id}`, `POST /api/me/spots`, `POST /api/trips/end`

## 로그
대화 한 번 = `turn_logs` 한 줄, 반응 한 번 = `reaction_logs` 한 줄 (Supabase). 로컬로 내려받기: `python3 scripts/db/export_logs.py`

## 부하 테스트 (2026-09-24, 로컬, 워커 1개, LLM 목업)
`LLM_MOCK=1` 로 띄우고 `python3 tools/loadtest.py http://localhost:8000 <동시 사용자> <초>`

| 동시 사용자 | 처리량 | 추천 p95 | 장소 상세 p95 | 대화 p95 (LLM 2초 포함) | 오류 |
|---|---|---|---|---|---|
| 10 | 19/s | 60ms | 26ms | 2.5s | 0 |
| 50 | 87/s | 485ms | 93ms | 2.5s | 0 |
| 100 | 183/s | 178ms | 22ms | 2.5s | 0 |
| 200 | 324/s | 739ms | 79ms | 2.6s | 0 |

개선: 공간 격자 인덱스(전국 스캔 제거, 추천 p95 3.8s → 0.5s @50명), 이름·역 검색 인덱스, 스레드풀 40 → 200.
DB 를 Supabase 로 옮긴 뒤 요청당 쿼리 22 → 9회 (연결 확인 왕복 제거·조회 합치기).
