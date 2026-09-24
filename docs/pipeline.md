# 전체 파이프라인: 데이터 다운로드 → DB → 전처리 → 추천

프로젝트 루트에서 실행. API·다운로드 단계는 먼저 `set -a && . ./.env && set +a`
(`.env`: `CONTACT`(Wikimedia UA 연락처), `OPENAI_API_KEY`, `HF_TOKEN`. gitignore 됨).
`data/` 는 gitignore 라 이 문서 순서대로 다시 만들 수 있어야 한다.

## 1. 다운로드·추출

| # | 명령 | 출력 | 비고 |
|---|---|---|---|
| 1 | `bash scripts/download_osm.sh` | `data/raw/osm_pbf/*.osm.pbf` (8개, 약 2.5GB) | Geofabrik `latest` — 받을 때마다 조금씩 달라짐 |
| 2 | `python3 scripts/extract_pbf.py` | `data/interim/osm_eateries_jp.json` | 음식점 |
| 3 | `python3 scripts/extract_attractions.py` | `data/interim/osm_attractions_jp.json` | 관광지·쇼핑·휴식 |
| 4 | `python3 scripts/fetch_wikidata.py` → `python3 scripts/fetch_wikidata_sparql.py` | `data/raw/wikidata/entities.jsonl` | 관광지 wikidata 태그 |
| 5 | `python3 scripts/analyze_wikidata_link.py` | `data/interim/wikidata_popularity.json` | 연결 품질 점검 + 유효 QID |
| 6 | `python3 scripts/fetch_pageviews.py ja 12m` | `data/raw/wikidata/pageviews_ja.jsonl` | 아이템 인기도. 분당 200회 한도 |
| 7 | `python3 scripts/fetch_pageviews.py {ja,ko,en} 36m` → `python3 scripts/exploration/lang_indices_monthly.py` | `pageviews_*_36m.jsonl`, `data/interim/lang_indices_monthly.csv` | 계절성·언어 지수 (테마 칩: 현지인·한국인·숨은·이달 명소) |
| 8 | `python3 scripts/fsq_extract_jp.py` | `data/raw/fsq/places_jp_2026-09-15.parquet`, `categories_…` | Foursquare OS Places, 릴리스 고정 |
| 9 | `python3 scripts/labeling/fetch_brands_wikidata.py` | `data/raw/wikidata/brands.json` | 체인 브랜드 |
| 10 | `python3 scripts/extract_stations.py` | `data/interim/osm_stations_jp.json` | 역 (시작 위치 검색) |
| 11 | `curl -L https://download.db-ip.com/free/dbip-country-lite-YYYY-MM.mmdb.gz \| gunzip > data/geoip/dbip-country-lite.mmdb` | IP → 국가 | DB-IP Lite (CC BY 4.0) |
| (12) | `python3 scripts/wikivoyage_eat.py` | `data/raw/wikivoyage/…` | 설명 전파 실험용 (추천에 안 씀) |

## 2. 음식점 라벨 (전처리)

`scripts/labeling/README.md` 1~18단계. 요약:
이름 규칙(`name_rules.py`, `build_chain_list.py`) → LLM(`classify.py`, **2026-09-24 데이터 고정, 재실행 안 함**) →
`merge_labels.py` → Foursquare 매칭(`fsq_match_osm.py`) → BERT 학습(`ml/make_fsq_dataset.py`, `ml/train_bert_multi.py`) →
`apply_fsq.py` → `data/interim/gold/all_labels_fsq.jsonl`

규칙 목록은 모두 `rules/*.json` (출처 기록). 결정 사항은 `prompts/labeling_decisions.md`.

## 3. 아이템 DB

`cd src && python3 -m japan_rec.build_items` → `data/processed/items_japan.json` (`REGION=fukuoka` 면 후쿠오카만)

## 4. 추천

- 코드: `src/japan_rec/` (`candidates.py` 후보 생성, `recommender.py` 랭킹, `profile.py`, `categories.py`, `translit.py`), 웹 서버 `server/`
- 테스트: `python3 -m pytest -q tests`
- 성능 시뮬레이션: `python3 scripts/eval/sim_rec.py` (`DAYS`, `METHODS`, `N_SHOW`)

## 다시 만들 수 없는 것 / 주의

- **LLM 라벨** (`data/interim/gold/llm_full/labels.jsonl`): 다시 돌리면 비용이 들고 결과가 달라짐. 고정 데이터라 백업 필요
- OSM `latest`, Wikipedia 조회수 기간은 받는 시점에 따라 값이 달라짐 (재현은 "돌아가기만 하면 됨" 기준)
