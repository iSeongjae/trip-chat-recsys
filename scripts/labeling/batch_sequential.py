"""Batch 대기열 토큰 한도(gpt-5-nano 조직당 200만 enqueued tokens) 안에서 순서대로 제출·수집.
남은 가게를 CHUNK_SHOPS 씩 잘라 → classify.py batch-submit → 완료까지 대기 → batch-collect → 반복.
사용: cd data/interim/gold/llm_full && python3 ../../../../scripts/labeling/batch_sequential.py"""
import csv, json, os, subprocess, sys, time
from openai import OpenAI
HERE = os.path.dirname(os.path.abspath(__file__))
C, P = os.path.join(HERE, 'classify.py'), os.path.join(HERE, '..', '..', 'prompts')
ARGS = ['--prompt', f'{P}/prompt.txt', '--fewshot', f'{P}/fewshot.jsonl', '--effort', 'low', '--out', 'labels.jsonl']
CHUNK_SHOPS = 450 * 25   # 요청 450개 ≈ 170만 토큰 (요청당 약 3,700 토큰)
cl = OpenAI()
shops = list(csv.DictReader(open('unlabeled_all.csv', encoding='utf-8')))
while True:
    done = {json.loads(l)['id'] for l in open('labels.jsonl')} if os.path.exists('labels.jsonl') else set()
    todo = [s for s in shops if s['id'] not in done]
    print(time.strftime('%H:%M'), f'완료 {len(done):,} / 남음 {len(todo):,}', flush=True)
    if not todo:
        break
    with open('chunk.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['id', 'name', 'tags']); w.writeheader(); w.writerows(todo[:CHUNK_SHOPS])
    subprocess.run([sys.executable, C, 'batch-submit', '--input', 'chunk.csv', '--per-file', '1000'] + ARGS, check=True)
    ids = json.load(open('.classify_state.json'))['batches']
    while True:
        time.sleep(60)
        st = [cl.batches.retrieve(b) for b in ids]
        print('  ', ' | '.join(f'{x.status} {x.request_counts.completed}/{x.request_counts.total}' for x in st), flush=True)
        if all(x.status in ('completed', 'failed', 'expired', 'cancelled') for x in st):
            break
    for x in st:
        if x.status != 'completed':
            print('  배치 실패:', x.id, [(e.code, e.message[:100]) for e in (x.errors.data if x.errors and x.errors.data else [])], flush=True)
    subprocess.run([sys.executable, C, 'batch-collect'] + ARGS, check=True)
    if any(x.status != 'completed' for x in st):
        print('실패한 배치가 있어 중단 — 원인 확인 후 다시 실행', flush=True); sys.exit(1)
print('전체 완료', flush=True)
