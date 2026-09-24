"""brand 태그가 있는 미분류 가게에서 서로 다른 브랜드 25개 (seed 42) → data/interim/gold/llm_test/test_brand_25.csv"""
import collections, csv, json, os, random, re
G = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', 'gold')
EX = set(json.load(open(os.path.join(G, 'fewshot_exclude_ids.json'))))
U = [json.loads(l) for l in open(os.path.join(G, 'unlabeled.jsonl'))]
by = collections.defaultdict(list)
for u in U:
    m = re.search(r'(?:^|\s)brand=(.+?)(?=\s\S+=|$)', u['tags'])
    if m and u['id'] not in EX:
        by[m.group(1)].append(u)
print(f'brand 태그 있는 미분류 {sum(len(v) for v in by.values())}곳, 브랜드 {len(by)}개')
rng = random.Random(42)
rows = [rng.choice(by[b]) for b in rng.sample(sorted(by), min(25, len(by)))]
with open(os.path.join(G, 'llm_test', 'test_brand_25.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'tags']); w.writeheader()
    w.writerows({k: r[k] for k in ('id', 'name', 'tags')} for r in rows)
print('test_brand_25:', [r['name'] for r in rows])
