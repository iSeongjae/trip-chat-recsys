# 웹 프로토타입 설계 (2026-09-24)

디자인: `이제뭐하지? (design)/` (화면 7개 + `tabi_talk/DESIGN.md`)

## 1. 화면 요소 분류

✅ 지금 데이터로 가능 · 🟡 일부만/근사 · ❌ 데이터 없음 또는 약관상 불가

**결정 (2026-09-24): ❌ 항목은 프로토타입에서 모두 뺀다.** 구현: `server/` (README 참고). 파서 모델은 gpt-5-mini (nano 는 종류를 일본어로 뽑거나 놓침)

### 여행챗 (1._chat)
| 요소 | 판정 | 근거 / 대안 |
|---|---|---|
| 대화 → 추천 (LLM 파서 + 후보 생성 + 랭킹) | ✅ | 기존 `japan_rec` |
| "라멘 8곳 찾았어요" | ✅ | N_SHOW=8 |
| 위치 칩 "교토역" | 🟡 | GPS 는 가능. 역·지명 검색은 DB 에 역이 없음 → OSM `railway=station` 추출 필요 |
| 카드 이름 한국어 표기 ("혼케 다이이치아사히") | 🟡 | 식당 `name:ko` 거의 없음. 가나→한글 음역(`src/japan_rec/translit.py`)으로 적용, 한자 이름은 읽기 추정이라 부정확 → 일본어 원문 병기 |
| 카드 부제 "소유 돈코츠", "블랙 소유 라멘" | ❌ | 맛·국물 정보 없음 → 세부 카테고리("라멘") + 거리로 대체 |
| 태그 "미슐랭 빕구르망" | ❌ | 미슐랭 데이터 없음(독점) |
| 태그 "깔끔 담백", "혼밥 인기", "한국어 메뉴" | ❌ | 리뷰·메뉴 정보 없음 (Hot Pepper 파기, Google 저장 금지) |
| 태그 "심야 영업" | 🟡 | OSM `opening_hours` 식당 약 14% (추출 필요) |
| 태그 "현지인 인기" (식당) | ❌ | 언어 지수는 위키 문서 있는 관광지만 |
| 테마 칩 현지인·한국인·외국인(숨은)·○월 명소 | 🟡 | 관광지만, 수백~수천 곳 → 반경을 도시 단위로 넓혀 적용 |
| 종류 칩 구경·산책·쇼핑·휴식 | ✅ | 기존 카테고리 |
| "혼자"(혼밥) 조건 | ❌ | 필터 불가. 대화에서 받아주되 조건으로는 무시 |

### 지도 (2._map)
| 요소 | 판정 | 근거 |
|---|---|---|
| MapLibre + OpenFreeMap 지도, 추천 핀 + 거리 | ✅ | 무료 타일, 출처 표시 |
| 하단 카드 "신사 · 한적함" | 🟡 | "한적함"은 인기도 낮음으로 근사 (관광지만) |
| 한 줄 설명 "현지인들이 아침 산책으로 즐겨 찾는…" | 🟡 | 위키 문서 있는 관광지(약 1.5만)만 위키백과 요약으로 생성. 식당·위키 없는 곳은 템플릿 문장(종류·거리·테마) |

### 장소 카드 (3._place_card)
| 요소 | 판정 | 근거 |
|---|---|---|
| 이름·종류·거리 | ✅ | |
| "관람 09:00–17:00" | 🟡 | OSM `opening_hours`: 관광지 2%, 식당 약 14% — 있을 때만 표시 |
| "가까움" 칩 | ✅ | 거리 |
| 설명 + 출처 "위키백과 · CC BY-SA" + 원문 링크 | 🟡 | 위키 연결된 관광지만. 문맥 문장("점심 먹은 곳에서 가까워요")은 세션 정보로 생성 |
| 여기로 갈까요? / 저장 / 여기 말고 | ✅ | select / save / skip. 길찾기는 Google 지도 링크(딥링크, API 아님) |
| 공유, 지도 레이어 | ✅ | |
| 사진 | 🟡 | Wikidata 대표 이미지(Commons, 관광지 일부). 식당 없음 |

### 저장목록 (screen.png)
| 요소 | 판정 | 근거 |
|---|---|---|
| 내가 간 곳 / 가고 싶은 곳 | ✅ | 방문(select·mark_visited) / 저장(save) |
| 검색 | ✅ | DB + 내 목록 |
| 도시 필터 (교토·오사카·도쿄) | 🟡 | 아이템에 도시 정보 없음 → OSM 행정경계 또는 Foursquare locality 로 추가 필요 |
| "교토 3일차", 날짜·시간대 | ✅ | 여행·방문 기록 시각 |
| 별점, 평균 ★ | ✅ | 사용자가 직접 매김 (별점 입력 UI 필요) |
| 방문완료 / 발자국 | ✅ | 방문완료 = DB 장소, 발자국 = 직접 등록 장소 |
| 직접 등록하기 | ✅ | 사용자 장소 저장 |

### 기타
| 화면 | 판정 | 비고 |
|---|---|---|
| Google 로그인 / 게스트 | ✅ | Authlib, `openid` 범위만 (이메일 안 받음) |
| 데이터 출처 | ✅ | Wikivoyage 는 안 씀 → 빼고, 위키백과(CC BY-SA)·Wikidata(CC0)·OSM(ODbL)·Foursquare NOTICE·OpenFreeMap 표시 |
| 이용약관·개인정보 처리방침 | ✅ | 운영자·연락처·시행일 채워야 함 |
| 알림(종) | ❌ | 기능 정의 없음 → 프로토타입에서 제외 |

### 개인정보 방침과 현재 코드의 충돌 (고쳐야 함)
- 방침: "정확한 좌표는 저장하지 않음, 동네 단위만" ↔ 현재 프로필(`session.current`)·이벤트 로그가 좌표를 그대로 저장
  → 현재 위치는 요청 처리 중에만 쓰고, 저장은 geohash 6자리(약 1km) 수준으로
- 게스트 기록 30일, 접속 기록 90일 삭제 → 정기 삭제 작업 필요
- "하루 이용 횟수 제한" → 사용자·IP 별 제한

## 2. FastAPI 서버 구조

```
server/
  app/
    main.py              # FastAPI 앱, 라우터 등록, 시작 시 아이템 DB 메모리 로드
    config.py            # 환경변수 (.env: OPENAI_API_KEY, GOOGLE_CLIENT_ID/SECRET, SESSION_SECRET)
    deps.py              # 현재 사용자(쿠키 세션), DB 세션, 레이트 리밋
    routers/
      auth.py            # /auth/google/login, /auth/google/callback, /auth/guest, /auth/logout, DELETE /me
      chat.py            # POST /chat
      places.py          # GET /places/{id}, GET /places/search, POST /places/{id}/select|save|skip
      recommend.py       # POST /recommend (칩 눌렀을 때 — LLM 없이)
      me.py              # /me/visited, /me/saved, /me/spots, /me/trips, PATCH 별점·메모
      legal.py           # /legal/terms, /legal/privacy, /legal/sources (정적)
    services/
      parser.py          # LLM: 발화 → 턴 JSON (구조화 출력, gpt-5-nano)
      orchestrator.py    # 턴 JSON → 프로필 병합 → candidates.generate → recommender.recommend
      reply.py           # LLM: 추천 결과만 근거로 짧은 답변 (없는 장소 언급 금지)
      describe.py        # 장소 설명: 위키 요약(출처) 또는 템플릿
      geo.py             # 위치 → 동네 이름, 좌표 반올림(geohash)
    db/
      models.py          # SQLAlchemy
      session.py
    static/              # 프론트 빌드 (MapLibre + OpenFreeMap)
  japan_rec/             # 기존 추천 코드 (src/japan_rec) 를 라이브러리로 사용
```

### 요청 흐름: POST /chat
1. 입력 `{message, location?: {lat, lon} | {query}}`
2. `parser`: 발화 → `{session, intent, stable}` (턴 JSON)
3. `orchestrator`: 프로필 병합(`profile.apply_turn`) → 후보 생성 → 랭킹 8개 → 노출 로그
4. `reply`: 추천 목록만 보고 한두 문장 ("라멘 8곳 찾았어요")
5. 출력 `{reply, recommendations: [{id, name, name_ja, sub, fine, distance_m, lat, lon, tags}], map: {center, pins}, notes}`

칩(종류·테마)을 누르면 `POST /recommend` 로 2~4번 없이 바로 3번.

### 테이블
| 테이블 | 내용 |
|---|---|
| users | id, google_sub(없으면 게스트), created_at, last_seen |
| profiles | user_id, stable(JSON), taste(JSON), n_reactions |
| trips | id, user_id, started_at, ended_at, city |
| sessions | trip_id, current_area(geohash6), intent(JSON), candidates(JSON, 짧게 유지), last_shown |
| events | user_id, trip_id, type(impression/select/save/skip/detail), item_id, rank, at |
| visits | user_id, trip_id, item_id 또는 spot_id, visited_at, rating, memo |
| saved | user_id, item_id, saved_at |
| spots | user_id, name, lat, lon, memo (직접 등록, 사용자 콘텐츠) |

- 아이템(37만 곳)은 DB 가 아니라 **메모리** (`items_japan.json`, 로드 약 1초, 후보 생성 약 23ms)
- DB 는 Supabase(Postgres, 도쿄) — `docs/db_schema.md`
- 기존 `profile.py`·`recommender.py` 는 dict 를 받으므로 JSON 컬럼과 그대로 연결

### 비용·운영
- LLM: 턴당 파서 + 답변 2회 (gpt-5-nano, 대략 턴당 $0.001 미만 — 실측 필요)
- 서버: 메모리 1GB 안팎 (아이템 로드), 작은 VM 한 대
- 레이트 리밋: 사용자·IP 별 일일 채팅 횟수
