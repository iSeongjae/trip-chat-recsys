"""brand:wikidata 기반 체인 목록: QID → 카테고리.
근거 A: 같은 브랜드 지점들의 이름 규칙 라벨 다수결 / B: Wikidata 설명·P31·P2012·P452 키워드 / C: 브랜드 이름에 이름 규칙.
출력: data/interim/gold/chains_wikidata.csv (+ 검토 필요 목록)"""
import collections, csv, json, os, re, sys
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from name_rules import label as name_label

sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec.rules import load as _load, patterns as _patterns
WD = _patterns('wikidata_keywords.json')  # rules/wikidata_keywords.json
WDX = [(c, re.compile(p, re.I)) for c, p in WD]

B = json.load(open(os.path.join(ROOT, 'data/raw/wikidata/brands.json')))
O = [o for o in json.load(open(os.path.join(ROOT, 'data/interim/osm_eateries_jp.json'))) if o['name'].get('name')]
LAB = {}
for l in open(os.path.join(ROOT, 'data/interim/gold/name_rule_labels.jsonl')):
    d = json.loads(l)
    if d['rule'] in ('keyword', 'chain'): LAB[d['id']] = d['label']
shops = collections.defaultdict(list)
for o in O:
    for q in (o['tags'].get('brand:wikidata') or '').split(';'):
        if q.strip().startswith('Q'): shops[q.strip()].append(o)

# 수동 지정·제외 목록: rules/chain_manual.csv, rules/not_eatery.json
MANUAL = {r['qid']: (r['category'], r['source']) for r in _load('chain_manual.json')}
NOT_EATERY = {r['qid']: r['source'] for r in _load('not_eatery.json')}

rows, review = [], []
for q, v in sorted(shops.items(), key=lambda x: -len(x[1])):
    b = B.get(q, {})
    names = collections.Counter(o['tags'].get('brand') or o['name']['name'] for o in v)
    # A: 지점 다수결 — 각 지점 이름에 브랜드 규칙을 뺀 이름 규칙을 직접 적용 (파일·실행 순서와 무관)
    lc = collections.Counter(x for x in (name_label(o['name']['name'], use_brands=False)[0] for o in v) if x)
    A = lc.most_common(1)[0][0] if lc and lc.most_common(1)[0][1] >= 2 and lc.most_common(1)[0][1] / sum(lc.values()) >= 0.8 else None
    # B: Wikidata 텍스트 (P2012 요리 > 설명 > P31 > 업종 순으로 먼저 걸리는 것)
    Bc = None
    for field in ('cuisine', 'desc_ja', 'desc_en', 'p31', 'industry'):
        t = b.get(field, '')
        hit = next((c for c, rx in WDX if rx.search(t)), None)
        if hit: Bc = hit; break
    # C: 브랜드 이름에 이름 규칙
    C = next((name_label(n, use_brands=False)[0] for n in [b.get('ja'), b.get('en'), names.most_common(1)[0][0]] if n and name_label(n, use_brands=False)[0]), None)
    votes = [x for x in (A, C, Bc) if x]
    cat = conf = None
    source = ''
    if q in NOT_EATERY:
        cat, conf, source = '', 'excluded', NOT_EATERY[q]
    elif q in MANUAL:
        cat, source = MANUAL[q]; conf = 'manual'
    elif votes:
        top, n = collections.Counter(votes).most_common(1)[0]
        if n == len(votes):
            cat, conf = top, ('high' if n >= 2 else 'single')
        elif n >= 2:
            cat, conf = top, 'majority'   # 3개 중 2개 일치 (Wikidata 설명이 '외식 체인'처럼 일반적인 경우)
        else:
            cat, conf = (A or C), 'conflict'   # 지점 다수결·이름 규칙을 우선하되 검토 대상
        source = 'code: A/B/C vote'
    rec = dict(qid=q, ja=b.get('ja', ''), en=b.get('en', ''), brand_tag=names.most_common(1)[0][0], n_shops=len(v),
               n_unlabeled=sum(1 for o in v if o['osm_id'] not in LAB), cat=cat or '', conf=conf or 'none', source=source,
               A_branch=A or '', B_wikidata=Bc or '', C_name=C or '', desc=(b.get('desc_ja') or b.get('desc_en', ''))[:60])
    rows.append(rec)
    if conf in (None, 'conflict'): review.append(rec)

with open(os.path.join(ROOT, 'data/interim/gold/chains_wikidata.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
c = collections.Counter(r['conf'] for r in rows)
print(f"브랜드 {len(rows)} | " + ' | '.join(f'{k} {c[k]}' for k in ('high', 'majority', 'single', 'manual', 'excluded', 'conflict', 'none')))
print('카테고리 분포:', collections.Counter(r['cat'] for r in rows if r['cat']).most_common())
print(f"\n검토 필요 {len(review)}개 (가게 많은 순):")
for r in review:
    print(f"  {r['qid']} {r['ja'] or r['en']} ({r['brand_tag']}) 가게 {r['n_shops']} | A={r['A_branch']} B={r['B_wikidata']} C={r['C_name']} | {r['desc']}")
