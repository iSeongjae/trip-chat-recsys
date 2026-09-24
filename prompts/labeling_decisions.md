# 정답 라벨 기준 결정 사항

few-shot 프롬프트(`prompts/fewshot_examples.txt`)의 규칙을 보완하는 결정. 정답 라벨과 예시는 이 기준을 따른다.

| 날짜 | 결정 | 근거 |
|---|---|---|
| 2026-09-24 | `amenity=bar/pub/fast_food` + 이름에 단서 없음 → `unknown` (프롬프트 규칙 6·7 대신). `amenity=cafe` + 단서 없음은 `cafe` 유지 | 일본 OSM 에서 pub/bar 는 이자카야에도, fast_food 는 소바·오뎅집에도 쓰임. 예: 大床水産(amenity=bar, 실제 해산물 이자카야), 銀嶺(amenity=fast_food, 실제 오뎅·야키토리) |
| 2026-09-24 | 고유명사 + `cuisine=japanese` 뿐 → `unknown` (jp_other 아님) | cuisine=japanese 는 라멘·소바집에도 붙는 넓은 태그 |
| 2026-09-24 | 짬뽕(ちゃんぽん)·사라우동(皿うどん) 가게 → `chinese` | 나가사키 짬뽕은 중화 계열. 皿うどん 이 udon_soba 로 잘못 가지 않게 우선 처리 |
| 2026-09-24 | インドカレー 등 인도·네팔 카레 → `asian` (`curry` 는 일본식 카레) | 프롬프트 카테고리 정의 |
| 2026-09-24 | 패밀리 레스토랑: 양식 계열(ガスト·ココス·ジョイフル·デニーズ·ジョナサン·ロイヤルホスト 등) → `western`, 일식 계열(夢庵·とんでん·かごの屋·まるまつ·藍屋·華屋与兵衛·ばんどう太郎·いっちょう 등) → `jp_other` | 프롬프트에 패밀리 레스토랑 코드가 없음. 洋食 정의(western)와 일식 일반(jp_other)에 맞춤 |
| 2026-09-24 | 흔한 이름과 겹치는 체인(大吉·五右衛門·更科·安安 등)은 이름 맨 앞에 올 때만 체인으로 인정 | 'お食事処 大吉', 'つぼ家 五右衛門' 같은 무관한 가게 오탐 방지 |
| 2026-09-24 | unknown 가게는 DB 에서 지우지 않음. 추천에서 세부 종류(include_sub 등)를 요청하면 후보에서 제외, 종류를 정하지 않은 요청에는 포함 | unknown 은 대부분 이름에 업종 단어가 없는 동네 가게라 드랍하면 로컬 가게가 체계적으로 빠짐. 상위 카테고리(식사·카페·술)는 amenity 로 알 수 있음 |
| 2026-09-24 | 블로그 검색으로 unknown 채우기는 보류 | 네이버 블로그는 일본어 가게 이름으로 거의 안 나오고, 한글 표기로 바꿔도 동네 가게는 결과가 적음 (사용자 수동 테스트) |
| 2026-09-24 | 샘플 검증 후: amenity=bar + 고유명사에 LLM 이 `bar` 라고 한 것은 인정(스낵바), amenity=pub + 고유명사(술집 단어 없음)에 LLM 이 `bar`/`izakaya` 라고 한 것은 `unknown` 으로 코드 보정 (`merge_labels.py`) | 검증 표본 LLM 40곳 중 8곳이 규칙 6 과 달리 bar. bar 태그는 주로 스낵바, pub 태그는 이자카야·요리집과 섞여 있음 |
| 2026-09-24 | Foursquare OS Places 매칭 가게: unknown 은 Foursquare 세부 카테고리로 채우고, **LLM 라벨이 Foursquare 와 다르면 Foursquare 를 따름**. 규칙 라벨은 유지 (`scripts/labeling/apply_fsq.py`) | LLM 라벨은 Foursquare 와 75% 일치·샘플 검증 63%, 규칙 라벨은 95% 일치. Foursquare 는 Apache 2.0 |
| 2026-09-24 | 남은 unknown 에 다중 라벨 BERT 확률 ≥0.8 만 적용 | 테스트셋 적용 22%, 정확도 93.4% (겹침 관계 반영 95.0%) |
| 2026-09-24 | 中華そば → 라멘, 오키나와현의 そば → 오키나와 소바 (`rules/fine_overrides.json`) | BERT 오답 분석에서 そば 가 지역에 따라 라멘·오키나와 소바를 뜻함 |
| 2026-09-24 | **카테고리 체계는 Foursquare 기준으로 통일.** LLM 분류 단계도 문서상 Foursquare 체계(`rules/categories.json` 세부 카테고리, 상위 26코드는 그 부모)를 따르는 것으로 한다. **LLM 라벨 데이터는 현시점(gpt-5-nano low, phash 082b7cacea, `llm_full/labels.jsonl`)에서 고정**하고 재실행하지 않는다. `prompts/prompt.txt` 는 고정 데이터를 만든 원본이라 수정하지 않음 | 사용자 결정. 26코드는 세부 카테고리의 상위 코드와 같아 기존 LLM 라벨을 그대로 상위 코드로 쓸 수 있음 |

few-shot 예시 ID 는 `data/interim/gold/fewshot_exclude_ids.json` — 평가 세트에서 제외.
