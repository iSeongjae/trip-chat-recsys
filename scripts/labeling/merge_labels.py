"""규칙 라벨 + LLM 라벨 → 전체 음식점 라벨 하나로. 출력: data/interim/gold/all_labels.jsonl
source: 규칙 쪽은 name_rules.py 의 source, LLM 쪽은 'llm: gpt-5-nano low (phash)'."""
import collections, json, os, re
# 결정(2026-09-24): amenity=bar+고유명사의 LLM 'bar' 는 인정(스낵바), amenity=pub+고유명사의 LLM 'bar'/'izakaya' 는 unknown 으로 보정
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
from japan_rec.rules import words as _words
DRINK_WORDS = re.compile('|'.join(_words('drink_words.json')))  # rules/drink_words.json
G = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', 'gold')
out = {}
for l in open(os.path.join(G, 'name_rule_labels.jsonl')):
    d = json.loads(l); out[d['id']] = dict(d, method='rule')
llm = {}
for l in open(os.path.join(G, 'llm_full', 'labels.jsonl')):
    d = json.loads(l); llm[d['id']] = d          # 같은 id 는 마지막 기록
missing = 0
for l in open(os.path.join(G, 'unlabeled.jsonl')):
    u = json.loads(l); d = llm.get(u['id'])
    if not d:
        missing += 1; continue
    lab, src = d['cat'], f"llm: {d.get('model')} low ({d.get('phash')})"
    if 'amenity=pub' in u['tags'] and lab in ('bar', 'izakaya') and not DRINK_WORDS.search(u['name']):
        lab, src = 'unknown', src + ' + postfix: pub 고유명사 → unknown'
    out[u['id']] = dict(u, label=lab, conf=d['conf'], method='llm', rule='llm', source=src)
with open(os.path.join(G, 'all_labels.jsonl'), 'w') as f:
    for d in out.values(): f.write(json.dumps(d, ensure_ascii=False) + '\n')
c = collections.Counter(d['method'] for d in out.values()); u = sum(1 for d in out.values() if d['label'] == 'unknown')
fixed = sum(1 for d in out.values() if 'postfix' in d.get('source', ''))
print(f"pub 고유명사 보정 {fixed:,}곳")
print(f"전체 {len(out):,} | 규칙 {c['rule']:,} | LLM {c['llm']:,} | LLM 결과 없음 {missing:,} | unknown {u:,} ({u/len(out):.1%})")
print('카테고리:', collections.Counter(d['label'] for d in out.values()).most_common())
