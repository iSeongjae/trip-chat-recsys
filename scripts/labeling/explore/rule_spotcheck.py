"""이름 규칙 라벨 오탐 점검: 흔한 체인·키워드 토큰별 사례, 여러 규칙 걸린 사례, 무작위 40개 표본(seed 7)."""
import collections, json, os, random
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
L = [json.loads(l) for l in open(os.path.join(ROOT, 'data/interim/gold/name_rule_labels.jsonl'))]
for w in ['ウエスト', '天狗', '松屋', 'てんや', '秋吉', '庄や', '家系', '二郎', '鍋', 'パン', 'フォー', 'インド', '大吉', 'ずし', '寿し', '五右衛門', 'ドミノ', '更科', 'ガスト']:
    c = collections.Counter((x['name'], x['label']) for x in L if w in x['name'])
    print(f'{w}: {sum(c.values())}건 예: {[k for k, _ in c.most_common(8)]}')
random.seed(1); m = [x for x in L if len(x['matched']) > 1]
print('\n여러 규칙 걸린 예:', [(x['name'], x['matched']) for x in random.sample(m, 12)])
random.seed(7)
print('\n무작위 40개:')
for x in random.sample(L, 40): print(f"  {x['name'][:26]:<28} → {x['label']:<14} {x['rule']}")
