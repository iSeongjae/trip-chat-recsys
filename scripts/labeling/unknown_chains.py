"""미분류 가게 중 프랜차이즈 후보 (로컬 집계, API 호출 없음) → unknown_chains.csv, test_25.csv (seed 42)"""
import collections, csv, json, os, random, re, unicodedata
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', 'gold')
OUT = os.path.join(R, 'llm_test')
EXCLUDE = set(json.load(open(os.path.join(R, 'fewshot_exclude_ids.json'))))  # few-shot 예시는 테스트에서 제외
U = [json.loads(l) for l in open(os.path.join(R, 'unlabeled.jsonl'))]

def base(name):
    """지점명 떼기: '空白+○○店', '○○支店', '○○店' (이름 전체가 지워지지 않게 3글자 이상 남을 때만)."""
    n = unicodedata.normalize('NFKC', name).strip()
    for rx in (r'[\s]+\S*店$', r'\S{1,8}支店$', r'\S{1,8}店$'):
        m = re.sub(rx, '', n).strip()
        if m != n and len(m) >= 2:
            return m
    return n

groups = collections.defaultdict(list)
for u in U:
    groups[base(u['name'])].append(u)
multi = sorted(((k, v) for k, v in groups.items() if len(v) >= 3), key=lambda x: -len(x[1]))
brand = sum(1 for u in U if re.search(r'(^|\s)brand(:wikidata)?=', u['tags']))
brand_wd = sum(1 for u in U if 'brand:wikidata=' in u['tags'])

with open(os.path.join(OUT, 'unknown_chains.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.writer(f); w.writerow(['name', 'count', 'example_tags', 'has_brand_tag'])
    for k, v in multi:
        tags = collections.Counter(x['tags'] for x in v).most_common(1)[0][0]
        w.writerow([k, len(v), tags, sum('brand' in x['tags'] for x in v)])
print(f'미분류 {len(U):,}곳 | 3곳 이상 반복 이름 {len(multi):,}개, 해당 가게 {sum(len(v) for _, v in multi):,}곳 ({sum(len(v) for _, v in multi)/len(U):.1%})')
print(f'brand 또는 brand:wikidata 태그 있음 {brand:,}곳 (그중 brand:wikidata {brand_wd:,}곳)')
print('\n상위 50 (이름 | 개수 | 대표 tags):')
for k, v in multi[:50]:
    print(f'  {k} | {len(v)} | {collections.Counter(x["tags"] for x in v).most_common(1)[0][0]}')

# ── 테스트 25: 상위 50 후보 중 서로 다른 이름 25개, 이름당 1곳 (seed 42) ──
rng = random.Random(42)
names = rng.sample([k for k, _ in multi[:50]], 25)
rows = []
for k in names:
    cand = [x for x in groups[k] if x['id'] not in EXCLUDE]
    x = rng.choice(cand)
    rows.append({'id': x['id'], 'name': x['name'], 'tags': x['tags']})
with open(os.path.join(OUT, 'test_25.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['id', 'name', 'tags']); w.writeheader(); w.writerows(rows)
print(f'\ntest_25.csv: {len(rows)}개 → {[r["name"] for r in rows]}')
