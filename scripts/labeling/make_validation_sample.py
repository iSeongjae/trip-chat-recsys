"""샘플 검증용 50곳 (seed 42): LLM unknown 8, LLM conf=high 12, LLM conf=low 20, 규칙 10. few-shot 예시 제외.
출력: data/interim/gold/validation/sample_50.csv (판정은 judgments.csv 에 기록)"""
import csv, json, os, random
G = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', 'gold')
EX = set(json.load(open(os.path.join(G, 'fewshot_exclude_ids.json'))))
A = [json.loads(l) for l in open(os.path.join(G, 'all_labels.jsonl'))]
A = [a for a in A if a['id'] not in EX]
rng = random.Random(42)
pools = {
    'llm_unknown': [a for a in A if a['method'] == 'llm' and a['label'] == 'unknown'],
    'llm_high': [a for a in A if a['method'] == 'llm' and a['label'] != 'unknown' and a.get('conf') == 'high'],
    'llm_low': [a for a in A if a['method'] == 'llm' and a['label'] != 'unknown' and a.get('conf') == 'low'],
    'rule': [a for a in A if a['method'] == 'rule'],
}
N = {'llm_unknown': 8, 'llm_high': 12, 'llm_low': 20, 'rule': 10}
rows = []
for k, n in N.items():
    for a in rng.sample(pools[k], n):
        rows.append(dict(stratum=k, id=a['id'], name=a['name'], tags=a['tags'], label=a['label'], conf=a.get('conf', ''), rule=a.get('rule', '')))
with open(os.path.join(G, 'validation', 'sample_50.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
for i, r in enumerate(rows, 1): print(f"{i}. [{r['stratum']}] {r['name']} | {r['tags']} → {r['label']} {r['conf']} {r['rule']}")
