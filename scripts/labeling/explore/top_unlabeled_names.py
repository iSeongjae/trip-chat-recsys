"""미분류 가게의 빈도 상위 이름 (지점명 제거 후). 체인 목록 보강 후보를 볼 때 사용."""
import collections, json, os, re, unicodedata
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
U = [json.loads(l) for l in open(os.path.join(ROOT, 'data/interim/gold/unlabeled.jsonl'))]
def base(n):
    n = unicodedata.normalize('NFKC', n); n = re.sub(r'[\s　]+\S*店$', '', n)
    return (re.sub(r'\S{1,6}店$', '', n) if len(n) > 6 else n).strip()
c = collections.Counter(base(u['name']) for u in U)
top = [(n, k) for n, k in c.most_common(120) if n]
print(f'남은 {len(U):,}곳 중 상위 100개 이름이 {sum(k for _, k in top[:100]):,}곳')
for n, k in top[:100]: print(f'{k:>5} {n}')
