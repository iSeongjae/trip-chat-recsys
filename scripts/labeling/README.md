# 음식점 카테고리 정답 라벨 파이프라인

모든 단계는 아래 스크립트로 재현된다. 프로젝트 루트에서 실행.
Claude 가 지식이나 웹 검색으로 정한 라벨은 코드 안에 그대로 두고, 출처(`source` / `verified_source` / 주석)에 기록한다.

## 실행 순서

| # | 명령 | 출력 | 비고 |
|---|---|---|---|
| 1 | `python3 scripts/extract_pbf.py` | `data/interim/osm_eateries_jp.json` | Geofabrik pbf → 음식점 (OSM ID·태그 포함) |
| 2 | `python3 scripts/labeling/name_rules.py` | `data/interim/gold/name_rule_labels.jsonl`, `unlabeled.jsonl` | 이름 키워드 규칙(code) + 체인 목록(Claude knowledge) |
| 3 | `python3 scripts/labeling/build_fewshot.py` | `data/interim/gold/fewshot_examples.jsonl`, `fewshot_exclude_ids.json`, `prompts/fewshot.jsonl`, `prompts/fewshot_examples.txt` | few-shot 36개 (라벨·근거·출처 포함) |
| 4 | `python3 scripts/labeling/unknown_chains.py` | `data/interim/gold/llm_test/unknown_chains.csv`, `test_25.csv` | 미분류 중 반복 이름 집계, 테스트 25개 (seed 42) |
| 5 | `scripts/labeling/run_llm_test.sh` | `test_min.jsonl`, `test_low.jsonl` + 비교표 | **과금** (gpt-5-nano, 25개 × 2회) |
| 6 | `python3 scripts/labeling/fetch_brands_wikidata.py` | `data/raw/wikidata/brands.json` | Wikidata SPARQL (`.env` 의 `CONTACT` 필요) |
| 7 | `python3 scripts/labeling/build_chain_list.py` | `data/interim/gold/chains_wikidata.csv` | brand:wikidata 340개 → 카테고리 (A 지점 다수결 / B Wikidata / C 이름 규칙 / MANUAL) |

| 8 | `python3 scripts/labeling/name_rules.py` (다시) | 위 2번 출력 갱신 | 7번 체인 목록이 있으면 brand:wikidata QID·브랜드 이름 규칙이 추가로 적용됨 |
| 9 | `python3 scripts/labeling/make_brand_test.py` | `llm_test/test_brand_25.csv` | brand 태그 미분류 25개 (seed 42) |
| 10 | `python3 scripts/labeling/make_full_input.py` | `llm_full/unlabeled_all.csv` | 미분류 전체 |
| 11 | (**데이터 고정 2026-09-24, 재실행 안 함**) (`llm_full` 에서) `classify.py batch-submit --input unlabeled_all.csv --out labels.jsonl --effort low --prompt ../../../../prompts/prompt.txt --fewshot ../../../../prompts/fewshot.jsonl` | `.classify_state.json` | **과금** (Batch) |
| 12 | (`llm_full` 에서) `python3 ../../../../scripts/labeling/wait_and_collect.py` | `labels.jsonl` | 완료까지 5분마다 확인 후 수집 |

| 13 | `python3 scripts/labeling/merge_labels.py` | `all_labels.jsonl` | 규칙 + LLM 합치기, pub 보정 |
| 14 | `set -a && . ./.env && set +a && python3 scripts/fsq_extract_jp.py` | `data/raw/fsq/places_jp_<release>.parquet` | Foursquare OS Places 일본 (`HF_TOKEN`) |
| 15 | `python3 scripts/fsq_match_osm.py` | `data/interim/fsq/osm_fsq_match.jsonl` | 100m + 같은 이름 |
| 16 | `OUT_DS=cuisine_ds_fsq_ml python3 scripts/ml/make_fsq_dataset.py` | `data/interim/cuisine_ds_fsq_ml/` | 세부 카테고리 학습 데이터 |
| 17 | (`scripts/ml` 에서) `DS=cuisine_ds_fsq_ml RUN=cuisine_bert_fsq_ml python3 train_bert_multi.py` | `data/models/cuisine_bert_fsq_ml/` | 다중 라벨 BERT, 약 50분 (MPS) |
| 18 | `python3 scripts/labeling/apply_fsq.py` | `all_labels_fsq.jsonl` | Foursquare 카테고리·폐업, BERT ≥0.8, 이름 보정 |

API 를 쓰는 단계(5, 6, 11, 12, 14)는 `set -a && . ./.env && set +a` 후 실행.

## 탐색용 (결정 근거 확인)

- `explore/fewshot_candidates.py`: few-shot 후보 샘플
- `explore/rule_spotcheck.py`: 규칙 오탐 점검, 무작위 40개 표본
- `explore/top_unlabeled_names.py`: 미분류 빈도 상위 이름 (체인 보강 후보)
- `explore/wikidata_gaps.py`: Wikidata 브랜드 항목의 음식 종류 공백 통계

## 기준 문서

- 라벨 정책: `prompts/labeling_decisions.md`
- 세부 카테고리: `rules/categories.json` (Foursquare 대응, also_match), `rules/fine_overrides.json`, `rules/regions.json`
- 분류 프롬프트: `prompts/prompt.txt` (+ `prompts/fewshot.jsonl`) — 고정된 LLM 라벨을 만든 원본
- 카테고리 체계: Foursquare 기준 (`rules/categories.json`). LLM 분류도 이 체계를 따르는 것으로 하되, LLM 라벨 데이터는 2026-09-24 시점에서 고정
- 분류기: `scripts/labeling/classify.py` (원본: ~/Downloads/classify.py, 수정하지 않음)

## 라벨 출처 표기

| 출처 | 의미 |
|---|---|
| `code: keyword rule` | 이름 키워드 규칙 |
| `code: A/B/C vote` | 체인 목록: 지점 다수결·Wikidata·이름 규칙의 투표 |
| `Claude knowledge 2026-09-24` | Claude 가 지식으로 지정 (체인 목록, MANUAL, few-shot) |
| URL | 웹 검색으로 확인한 출처 |
