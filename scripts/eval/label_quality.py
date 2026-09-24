"""음식점 라벨 품질 보고서 (README '라벨 품질' 표의 숫자를 다시 계산).

- 출처별 라벨 수 (규칙 / LLM / Foursquare / BERT / 이름 보정)
- 규칙·LLM 라벨이 Foursquare 세부 카테고리의 상위 코드와 얼마나 일치하나 (all_labels.jsonl 기준, Foursquare 반영 전)
- 샘플 검증 요약 (validation/judgments.csv, scripts/labeling/validation_judgments.py 가 만든 판정)
- 미분류(unknown): Foursquare·BERT 반영 전 → 후, 폐업 제외
출력: 화면 + data/reports/label_quality.json
실행: python3 scripts/eval/label_quality.py
"""
import os, sys, json, csv
from collections import Counter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec.rules import load as load_rule

G = os.path.join(ROOT, 'data', 'interim', 'gold')
cats = load_rule('categories.json')
LEAF = {l: f['id'] for f in cats['fine'] for l in f['fsq']}
PARENT = {f['id']: f['parent'] for f in cats['fine']}

before = {r['id']: r for r in map(json.loads, open(os.path.join(G, 'all_labels.jsonl')))}
after = [json.loads(l) for l in open(os.path.join(G, 'all_labels_fsq.jsonl'))]
match = {m['osm_id']: m for m in map(json.loads, open(os.path.join(ROOT, 'data', 'interim', 'fsq', 'osm_fsq_match.jsonl')))}
rep = {}

# 1) 출처별 수
rep['n_eateries'] = len(after)
rep['by_method_final'] = dict(Counter(a['method'] for a in after))
rep['by_method_before_fsq'] = dict(Counter(r['method'] for r in before.values()))

# 2) 규칙·LLM vs Foursquare (상위 코드 기준, 세부 카테고리가 있는 매칭만)
agree = {}
for method in ('rule', 'llm'):
    n = ok = 0
    for i, r in before.items():
        if r['method'] != method or r['label'] == 'unknown' or i not in match:
            continue
        parents = {PARENT[LEAF[c.split(' > ')[-1]]] for c in match[i]['fsq_categories'] if c.split(' > ')[-1] in LEAF}
        if not parents:
            continue
        n += 1; ok += r['label'] in parents
    agree[method] = dict(n=n, agree=round(ok / n, 4) if n else None)
rep['agreement_with_foursquare'] = agree

# 3) 샘플 검증
jp = os.path.join(G, 'validation', 'judgments.csv')
if os.path.exists(jp):
    by = {}
    for r in csv.DictReader(open(jp)):
        by.setdefault('llm' if r['rule'] == 'llm' else 'rule', Counter())[r['verdict']] += 1
    rep['validation_sample'] = {k: dict(v) for k, v in by.items()}

# 4) 미분류
unk_before = sum(1 for r in before.values() if r['label'] == 'unknown')
unk_after = [a for a in after if a['label'] == 'unknown']
rep['unknown'] = dict(before=unk_before, after=len(unk_after), after_open=sum(1 for a in unk_after if not a['closed']),
                      share_open=round(sum(1 for a in unk_after if not a['closed']) / len(after), 4),
                      closed_total=sum(1 for a in after if a['closed']),
                      llm_replaced_by_fsq=sum(1 for a in after if a.get('llm_label')))

print(json.dumps(rep, ensure_ascii=False, indent=1))
os.makedirs(os.path.join(ROOT, 'data', 'reports'), exist_ok=True)
json.dump(rep, open(os.path.join(ROOT, 'data', 'reports', 'label_quality.json'), 'w'), ensure_ascii=False, indent=1)
