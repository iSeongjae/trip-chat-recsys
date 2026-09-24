"""classify.py 결과 두 개(effort 비교)를 표로. 사용: python3 compare_efforts.py test_25.csv test_min.jsonl test_low.jsonl"""
import collections, csv, json, sys
S = list(csv.DictReader(open(sys.argv[1])))
M = {json.loads(l)['id']: json.loads(l) for l in open(sys.argv[2])}
L = {json.loads(l)['id']: json.loads(l) for l in open(sys.argv[3])}
print('| # | 이름 | tags | minimal (conf) | low (conf) | 다름 |\n|---|---|---|---|---|---|')
for i, s in enumerate(S, 1):
    m, l = M[s['id']], L[s['id']]
    print(f"| {i} | {s['name']} | {s['tags'].replace('|', '/')} | {m['cat']} ({m['conf']}) | {l['cat']} ({l['conf']}) | {'✱' if m['cat'] != l['cat'] else ''} |")
for nm, D in (('minimal', M), ('low', L)):
    c = collections.Counter(D[s['id']]['cat'] for s in S)
    print(f"\n{nm}: unknown {c['unknown']} | conf=high {sum(D[s['id']]['conf'] == 'high' for s in S)} | 분포 {dict(c.most_common())}")
print('일치', sum(M[s['id']]['cat'] == L[s['id']]['cat'] for s in S), '/', len(S))
