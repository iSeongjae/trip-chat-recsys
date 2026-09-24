"""검증: Wikivoyage 설명 속성을 이름 임베딩 그래프로 전파하면 다른 가게의 속성을 맞히는가.

- 씨앗: 영어 Wikivoyage 일본 먹거리·술 항목 중 일본어 이름(alt 또는 매칭된 OSM 이름)이 있는 것. 같은 이름은 하나로(체인 누수 방지)
- 속성(설명·가격에서 규칙으로 뽑음): cheap / pricey / local / famous, 가격대 3단계(¥ 최저값 <1000, <3000, 그 이상)
- 임베딩: cuisine_bert_fsq_ml 의 BERT 층 평균 벡터 (이름만)
- 방법: (1) kNN 전파 leave-one-out (k=10, 코사인 가중) (2) 라벨 전파(LabelSpreading, 씨앗 + 라벨 없는 OSM 음식점 2만 곳) 5-fold
- 기준선: 전체 비율(사전확률) → AUC 0.5, 가격대는 최빈값 정확도
실행: python3 scripts/eval/propagation_check.py  (임베딩은 torch 가 sklearn 과 한 프로세스에서 충돌해(segfault) 하위 프로세스로 따로 계산)
"""
import os, re, json, sys, random
import subprocess
import numpy as np
from sklearn.metrics import roc_auc_score
from sklearn.semi_supervised import LabelSpreading
from sklearn.model_selection import StratifiedKFold

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec.textnorm import norm

ATTR = {'cheap': r'cheap|inexpensive|affordable|budget|reasonabl|bargain|good value',
        'pricey': r'expensive|pricey|upscale|high-end|luxur|splurge|fine dining',
        'local': r'\blocals?\b(?! specialt)|neighbou?rhood|hole-in-the-wall|salarym',
        'famous': r'famous|popular|well[- ]known|renowned|queue|long line|wait(ing)? in line|michelin'}
JA = re.compile(r'[぀-ヿ一-鿿]')
random.seed(0); np.random.seed(0)

W = [json.loads(l) for l in open(os.path.join(ROOT, 'data/raw/wikivoyage/en_japan_eat.jsonl'))]
M = {(m['article'], m['name']): m['osm_id'] for m in map(json.loads, open(os.path.join(ROOT, 'data/interim/wikivoyage/eat_osm_match.jsonl')))}
O = {o['osm_id']: o for o in json.load(open(os.path.join(ROOT, 'data/interim/osm_eateries_jp.json')))}


def ja_name(w):
    if (w['article'], w['name']) in M:
        return O[M[(w['article'], w['name'])]]['name'].get('name')
    for x in re.split(r'[,;/()（）]| or ', w['alt']):
        if JA.search(x): return x.strip()


def price_bucket(p):
    n = [int(x.replace(',', '')) for x in re.findall(r'[¥￥]\s*(\d[\d,]*)', p or '')] + \
        [int(x.replace(',', '')) for x in re.findall(r'(\d[\d,]*)\s*(?:yen|円)', p or '')]
    n = [x for x in n if x >= 50]
    return None if not n else 0 if min(n) < 1000 else 1 if min(n) < 3000 else 2


seeds, seen = [], set()
for w in W:
    n = ja_name(w)
    if not n or len(w['content']) < 20 or norm(n) in seen: continue
    seen.add(norm(n))
    txt = (w['content'] + ' ' + w['price']).lower()
    seeds.append(dict(name=n, price=price_bucket(w['price']), **{a: int(bool(re.search(rx, txt))) for a, rx in ATTR.items()}))
print(f'씨앗 {len(seeds)}곳 (일본어 이름 + 설명 20자 이상, 같은 이름 하나로)')
for a in ATTR: print(f'  {a}: {np.mean([s[a] for s in seeds]):.1%}')
print(f"  가격대 있음 {sum(s['price'] is not None for s in seeds)} 분포 {np.bincount([s['price'] for s in seeds if s['price'] is not None])}")

EMB = os.path.join(ROOT, 'data/interim/wikivoyage/prop_emb.npz')
unl = random.sample([o['name']['name'] for o in O.values() if o['name'].get('name') and norm(o['name']['name']) not in seen], 20000)
json.dump({'seeds': [s['name'] for s in seeds], 'unl': unl}, open(EMB + '.names.json', 'w'), ensure_ascii=False)
subprocess.run([sys.executable, '-c', f"""
import json, numpy as np, torch
from transformers import AutoTokenizer, AutoModel
p = {os.path.join(ROOT, 'data/models/cuisine_bert_fsq_ml')!r}
tok, bert = AutoTokenizer.from_pretrained(p), AutoModel.from_pretrained(p).eval()
d = json.load(open({EMB + '.names.json'!r}))
def embed(names):
    out = []
    with torch.no_grad():
        for i in range(0, len(names), 256):
            e = tok(names[i:i + 256], padding=True, truncation=True, max_length=32, return_tensors='pt')
            h = bert(**e).last_hidden_state; m = e['attention_mask'].unsqueeze(-1)
            out.append(torch.nn.functional.normalize((h * m).sum(1) / m.sum(1), dim=-1).numpy())
    return np.concatenate(out)
np.savez({EMB!r}, X=embed(d['seeds']), XU=embed(d['unl']))
"""], check=True, capture_output=True)
E = np.load(EMB); X, XU = E['X'].astype(np.float64), E['XU'].astype(np.float64)

print('\n[kNN 전파, leave-one-out, k=10] / [라벨 전파, 5-fold]   (AUC 0.5 = 무작위)')
S = X @ X.T; np.fill_diagonal(S, -1)
nn = np.argsort(-S, 1)[:, :10]
for a in ATTR:
    y = np.array([s[a] for s in seeds])
    w = np.clip(np.take_along_axis(S, nn, 1), 0, None) + 1e-6
    pred = (y[nn] * w).sum(1) / w.sum(1)
    auc_knn = roc_auc_score(y, pred)
    pr = np.zeros(len(y))
    for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(X, y):
        lab = np.full(len(y) + len(unl), -1); lab[tr] = y[tr]
        ls = LabelSpreading(kernel='knn', n_neighbors=10, alpha=0.2, max_iter=100).fit(np.vstack([X, XU]), lab)
        pr[te] = ls.label_distributions_[te, 1]
    print(f'  {a:7} 양성 {y.mean():.0%}: kNN AUC {auc_knn:.3f} | 라벨전파 AUC {roc_auc_score(y, pr):.3f}')

idx = [i for i, s in enumerate(seeds) if s['price'] is not None]
yp = np.array([seeds[i]['price'] for i in idx]); Xp = X[idx]
Sp = Xp @ Xp.T; np.fill_diagonal(Sp, -1); nnp = np.argsort(-Sp, 1)[:, :10]
votes = np.array([np.bincount(yp[r], minlength=3).argmax() for r in nnp])
print(f'  가격대 3단계 n={len(yp)}: kNN 정확도 {np.mean(votes == yp):.1%} | 최빈값 기준선 {np.bincount(yp).max() / len(yp):.1%}')
