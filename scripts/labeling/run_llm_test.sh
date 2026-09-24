#!/usr/bin/env bash
# classify.py 1배치 effort 비교 (2026-09-24 에 실행한 명령 그대로). 과금 발생 — 필요할 때만.
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; . ./.env; set +a
cd data/interim/gold/llm_test
P=../../../../prompts; C=../../../../scripts/labeling/classify.py
python3 $C run --input test_25.csv --out test_min.jsonl --effort minimal --prompt $P/prompt.txt --fewshot $P/fewshot.jsonl
python3 $C run --input test_25.csv --out test_low.jsonl --effort low --prompt $P/prompt.txt --fewshot $P/fewshot.jsonl
python3 ../../../../scripts/labeling/compare_efforts.py test_25.csv test_min.jsonl test_low.jsonl
