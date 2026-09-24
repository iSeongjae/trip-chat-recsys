"""Foursquare 매칭 결과를 라벨에 반영 → data/interim/gold/all_labels_fsq.jsonl (all_labels.jsonl 은 그대로 둠)

- fine: Foursquare 세부 카테고리(rules/categories.json). 기존 라벨이 있으면 그 상위 코드와 맞는 것만
- unknown 이고 Foursquare 세부 카테고리가 있으면 → label = 첫 세부 카테고리의 상위 코드, method 'fsq'
- LLM 라벨인데 Foursquare 세부 카테고리 중 그 상위 코드와 맞는 게 없으면 → Foursquare 를 따름 (사용자 결정 2026-09-24,
  LLM 라벨은 Foursquare 와 75% 일치·샘플 검증 63%, 규칙 라벨은 95% 일치라 유지)
- broad: 세부 종류는 모르는 넓은 분류(Japanese Restaurant → japanese 등). 넓은 조건 필터용
- closed: Foursquare date_closed 가 있으면 True (추천에서 제외)
- 남은 unknown(폐업 제외)에 다중 라벨 BERT(cuisine_bert_fsq_ml) 1순위 확률 ≥ BERT_TH(기본 0.8) 적용, method 'bert'.
  0.8: 테스트셋 적용 22%, 세부 정확도 93.4% (오답 대부분은 Foursquare 라벨 겹침·오류, 2026-09-24 분석). BERT_TH=0 이면 끔
- 마지막에 이름·지역 보정(rules/fine_overrides.json): 中華そば → ramen, 오키나와 そば → okinawa_soba
실행: [BERT_TH=0.8] python3 scripts/labeling/apply_fsq.py
"""
import os, sys, json
from collections import Counter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec.rules import load as load_rule
from japan_rec.categories import override

cats = load_rule('categories.json')
LEAF = {l: f['id'] for f in cats['fine'] for l in f['fsq']}
PARENT = {f['id']: f['parent'] for f in cats['fine']}
BROAD = cats['broad']['map']
BERT_TH = float(os.environ.get('BERT_TH', 0.8))

A = [json.loads(l) for l in open(os.path.join(ROOT, 'data/interim/gold/all_labels.jsonl'))]
M = {m['osm_id']: m for m in (json.loads(l) for l in open(os.path.join(ROOT, 'data/interim/fsq/osm_fsq_match.jsonl')))}
st = Counter()
for a in A:
    a.update(fine=[], broad=None, closed=False, fsq_place_id=None)
    m = M.get(a['id'])
    if not m: continue
    leaves = [c.split(' > ')[-1] for c in m['fsq_categories']]
    fs = list(dict.fromkeys(LEAF[l] for l in leaves if l in LEAF))
    a['fsq_place_id'] = m['fsq_place_id']
    a['closed'] = bool(m['date_closed'])
    a['broad'] = next((BROAD[l] for l in leaves if l in BROAD), None)
    if a['label'] == 'unknown' and fs:
        a.update(label=PARENT[fs[0]], method='fsq', rule=None, source=f"Foursquare OS Places {m['fsq_place_id']}")
        st['unknown→fsq'] += 1
    elif a['label'] == 'unknown' and a['broad'] == 'cafe':
        a.update(label='cafe', method='fsq', rule=None, source=f"Foursquare OS Places {m['fsq_place_id']} (Cafe, Coffee, and Tea House)")
        st['unknown→fsq'] += 1
    elif a['method'] == 'llm' and fs and not any(PARENT[f] == a['label'] for f in fs):
        a.update(label=PARENT[fs[0]], method='fsq', rule=None, llm_label=a['label'],
                 source=f"Foursquare OS Places {m['fsq_place_id']} (LLM {a['label']} 대체)")
        st['llm→fsq'] += 1
    a['fine'] = [f for f in fs if PARENT[f] == a['label']]
    if fs and not a['fine']: st['FSQ 와 상위 코드 불일치'] += 1

if BERT_TH:
    import numpy as np, torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    p = os.path.join(ROOT, 'data/models/cuisine_bert_fsq_ml'); labels = json.load(open(f'{p}/labels.json'))
    dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
    tok = AutoTokenizer.from_pretrained(p); mdl = AutoModelForSequenceClassification.from_pretrained(p).to(dev).eval()
    rest = [a for a in A if a['label'] == 'unknown' and not a['closed']]
    with torch.no_grad():
        for k in range(0, len(rest), 256):
            b = rest[k:k + 256]
            e = tok([a['name'] for a in b], padding=True, truncation=True, max_length=32, return_tensors='pt').to(dev)
            P = torch.sigmoid(mdl(**e).logits).float().cpu().numpy()
            for a, pr in zip(b, P):
                if pr.max() >= BERT_TH:
                    f = labels[int(pr.argmax())]
                    a.update(label=PARENT[f], fine=[f], method='bert', rule=None,
                             source=f'cuisine_bert_fsq_ml p={pr.max():.2f}')
                    st['unknown→bert'] += 1

for a in A:
    o = override(a['name'], a['lat'], a['lon'])
    if not o: continue
    f, parent, note = o
    if a['label'] not in (parent, 'unknown') or a['fine'][:1] != [f]:
        st['이름 보정'] += 1
        if a['label'] != parent: st[f"이름 보정: {a['label']}→{parent}"] += 1
    a['fine'] = [f] + [x for x in a['fine'] if x != f and PARENT[x] == parent]
    if a['label'] != parent:
        a.update(label=parent, method='override', rule=None, source=f'rules/fine_overrides.json ({note})')

with open(os.path.join(ROOT, 'data/interim/gold/all_labels_fsq.jsonl'), 'w') as f:
    for a in A: f.write(json.dumps(a, ensure_ascii=False) + '\n')
N = len(A); unk = [a for a in A if a['label'] == 'unknown']
print(f"전체 {N:,} | Foursquare 매칭 {sum(1 for a in A if a['fsq_place_id']):,} | 폐업 {sum(a['closed'] for a in A):,}")
print(f"LLM 라벨 → Foursquare 로 교체 {st['llm→fsq']:,}")
print(f"unknown→Foursquare {st['unknown→fsq']:,} | unknown→BERT {st['unknown→bert']:,} (기준 {BERT_TH})")
print('이름 보정', {k: v for k, v in st.items() if k.startswith('이름 보정')})
print(f"세부 카테고리 있음 {sum(1 for a in A if a['fine']):,} | 남은 불일치(규칙 라벨) {st['FSQ 와 상위 코드 불일치']:,}")
print(f"남은 unknown {len(unk):,} ({len(unk)/N:.1%}) — 폐업 {sum(a['closed'] for a in unk):,}, 넓은 분류 있음 {sum(1 for a in unk if a['broad']):,} {Counter(a['broad'] for a in unk if a['broad'])}")
print(f"폐업 제외 후 unknown {sum(1 for a in unk if not a['closed']):,}")
