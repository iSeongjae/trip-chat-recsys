"""미분류 가게 전체 → classify.py 입력 CSV (id, name, tags). 출력: data/interim/gold/llm_full/unlabeled_all.csv"""
import csv, json, os
G = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', 'gold')
U = [json.loads(l) for l in open(os.path.join(G, 'unlabeled.jsonl'))]
with open(os.path.join(G, 'llm_full', 'unlabeled_all.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'tags']); w.writeheader()
    w.writerows({k: u[k] for k in ('id', 'name', 'tags')} for u in U)
print(f'{len(U):,}곳')
