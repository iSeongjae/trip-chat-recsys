"""제출한 Batch 가 모두 끝날 때까지 5분마다 상태 확인 → 끝나면 classify.py batch-collect 로 labels.jsonl 에 저장.
사용: cd data/interim/gold/llm_full && python3 ../../../../scripts/labeling/wait_and_collect.py"""
import json, os, subprocess, sys, time
from openai import OpenAI
cl = OpenAI(); st = json.load(open('.classify_state.json'))
while True:
    ss = {b: cl.batches.retrieve(b) for b in st['batches']}
    line = ' | '.join(f"{b[-6:]} {x.status} {x.request_counts.completed}/{x.request_counts.total}" for b, x in ss.items())
    print(time.strftime('%H:%M'), line, flush=True)
    if all(x.status in ('completed', 'failed', 'expired', 'cancelled') for x in ss.values()):
        break
    time.sleep(300)
C = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'classify.py')
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'prompts')
subprocess.run([sys.executable, C, 'batch-collect', '--out', 'labels.jsonl', '--prompt', f'{P}/prompt.txt', '--fewshot', f'{P}/fewshot.jsonl'], check=True)
