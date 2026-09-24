# 외부 검색 API 조사 (2026-09-24)

미분류(unknown) 음식점을 검색으로 채우기 위한 후보 정리. 서비스 대상은 일본 전역.

## NAVER API HUB (네이버클라우드) — 후보

네이버 개발자센터의 검색 API 는 2026-07-31 부로 신규 신청이 종료되고 NAVER API HUB 로 이관됨.
콘솔: Application Service → NAVER API HUB (Cloud Search 아님). 우리는 **검색 API(블로그)** 만 사용.

사용자가 확인한 요금표 (2026-09-24, VAT 별도):

| API | 구간 | 호출량 구간·한도 | 요금 | 비고 |
|---|---|---|---|---|
| 검색어 트렌드 | 무료 | 0 ~ 30,000건 | 0원 | 기본 무료 제공 |
| 검색어 트렌드 | 유료 | 30,001 ~ 50,000건 | 0원 | 한시적 무료 제공 |
| 쇼핑 인사이트 | 무료 | 0 ~ 30,000건 | 0원 | 기본 무료 제공 |
| 쇼핑 인사이트 | 유료 | 30,001 ~ 50,000건 | 0원 | 한시적 무료 제공 |
| **검색 API** | 무료 | **0 ~ 775,000건** | 0원 | **일 최대 25,000건 호출 제한** |

- unknown 약 4.5만 곳 × 가게당 최대 2회 검색 ≈ 9만 회 → 하루 25,000건 한도로 약 4일.
- **결정 (2026-09-24)**: 가게당 검색 1회("이름 + 지역명", 지역명은 OSM 지명으로 좌표에서 오프라인 추출). 결과 없는 가게는 `no_result` 로 기록하고 나중에 따로 처리. 대상은 unknown 먼저(약 4만 곳 → 약 이틀). 유료 구간이 없어 돈을 내도 하루 한도는 늘지 않음.
- 한국어 블로그 위주라 일본 동네 가게는 결과가 적을 수 있음 → 25곳 테스트로 확인 예정.
- 약관(결과 저장 가능 여부) 확인 필요.

## 사용하지 않기로 한 것

| 서비스 | 이유 | 출처 |
|---|---|---|
| Hot Pepper | 약관 리스크(24시간 캐시, DB 복제 금지)로 데이터 파기 | `TODO.md` 결정 사항 |
| Yahoo! JAPAN 로컬 서치 (YOLP) | 약관이 결과 저장·캐시 금지 (2022-12-01 시행), 상업 이용은 유료판 필요할 수 있음, 가입에 일본 전화번호 필요 | https://developer.yahoo.co.jp/changelog/2022-08-17-map.html |
| Bing Search API | 2025-08-11 서비스 종료 | https://learn.microsoft.com/en-us/lifecycle/announcements/bing-search-api-retirement |
| Google Custom Search JSON API | 2025년 신규 가입 중단, 2027-01-01 종료 예정 | https://developers.google.com/custom-search/v1/overview |

## 유료 대안

| 서비스 | 요금 | 비고 |
|---|---|---|
| OpenAI 웹 검색 도구 (gpt-5 계열) | 1,000회당 $10 + 검색 결과 토큰은 모델 단가 | 기존 OpenAI 키로 바로 사용 가능. 전국 unknown 약 4.5만 곳이면 $450 이상. https://developers.openai.com/api/docs/pricing |

## 블로그 플랫폼 정책 (2026-09-24 확인) — 여행 코스 참고용

| 플랫폼 | robots.txt | 약관·공식 답변 | 판단 |
|---|---|---|---|
| 네이버 블로그 | 주석 "BOT ACCESS FOR THE PURPOSES OF AI TRAINING AND RETRIEVAL-AUGMENTED GENERATION (RAG) IS STRICTLY PROHIBITED." GPTBot·ClaudeBot·Claude-SearchBot 등 전체 차단 (사용자가 직접 확인) | 미확인 | 사용 안 함 (AI·RAG 목적 명시 금지) |
| 브런치스토리 | GPTBot·ClaudeBot·anthropic-ai·Claude-Web 전체 차단 (2026-04-22 수정) | 약관 제10조 2항 2호: 서비스에서 얻은 정보를 회사 승낙 없이 복제·제3자 제공 금지 | 사용 안 함 |
| 티스토리 | 방명록·관리·검색만 차단, 글 본문 허용 (notice.tistory.com 기준) | 카카오 통합 약관 제외(계열사 별도 약관, 미확인). Open API 2024-02 종료 | 소량 열람·사실(장소·순서)만 추출까지 |
| Daum 검색 API | - | 카카오 데브톡 답변(2026-09-03, 09-07): 집계 수치 표시는 가능, AI 학습·외부 LLM 전달은 제한 (https://devtalk.kakao.com/t/api-llm/151458) | LLM 입력용 불가 |

시뮬레이션 코스는 Wikivoyage 일정(CC BY-SA)과 공개 통계로 만드는 것을 기본으로 한다.
