"""다중 라벨 BERT(cuisine_bert_fsq_ml) 테스트셋 평가 (README 'BERT' 숫자를 다시 계산).
학습 때 저장한 test_prob.npy 를 쓰므로 다시 추론하지 않는다.

- hit@1: 1순위가 정답 라벨(가게의 Foursquare 세부 카테고리들) 중 하나 / 상위 코드 기준
- 이름에 음식 키워드가 있는 가게 / 없는 가게
- 확신도 기준값별: 적용 비율, 정확도, 전체 대비 정답(TP)·오답(FP) 비율
- 0.8 기준 정확도: 겹치는 카테고리(rules/categories.json also_match)를 정답으로 인정하면
출력: 화면 + data/reports/bert_eval.json
실행: python3 scripts/ml/eval_bert.py [run 이름=cuisine_bert_fsq_ml] [데이터셋=cuisine_ds_fsq_ml]
"""
import os, sys, json
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec.categories import PARENT, expand

RUN = sys.argv[1] if len(sys.argv) > 1 else 'cuisine_bert_fsq_ml'
DS = sys.argv[2] if len(sys.argv) > 2 else 'cuisine_ds_fsq_ml'
M = os.path.join(ROOT, 'data', 'models', RUN)
te = [json.loads(l) for l in open(os.path.join(ROOT, 'data', 'interim', DS, 'test.jsonl'))]
labels = json.load(open(os.path.join(M, 'labels.json')))
P = np.load(os.path.join(M, 'test_prob.npy')).astype(float)
top, conf = P.argmax(1), P.max(1)
pred = [labels[k] for k in top]
hit = np.array([p in r['labels'] for p, r in zip(pred, te)])
phit = np.array([PARENT[p] in {PARENT[l] for l in r['labels']} for p, r in zip(pred, te)])
hit_rel = np.array([p in r['labels'] or any(p in expand([l]) or l in expand([p]) for l in r['labels']) for p, r in zip(pred, te)])
kw = np.array([r['has_keyword'] for r in te])

rep = dict(n_test=len(te), n_classes=len(labels), hit1=round(hit.mean(), 4), parent_hit1=round(phit.mean(), 4),
           keyword=dict(n=int(kw.sum()), hit1=round(hit[kw].mean(), 4)), no_keyword=dict(n=int((~kw).sum()), hit1=round(hit[~kw].mean(), 4)),
           thresholds={})
for th in (0.5, 0.6, 0.7, 0.8, 0.9):
    m = conf >= th
    rep['thresholds'][str(th)] = dict(coverage=round(m.mean(), 4), precision=round(hit[m].mean(), 4),
                                      tp_share=round((m & hit).mean(), 4), fp_share=round((m & ~hit).mean(), 4))
m8 = conf >= 0.8
rep['precision_at_0.8_with_overlap'] = round(hit_rel[m8].mean(), 4)
print(json.dumps(rep, ensure_ascii=False, indent=1))
os.makedirs(os.path.join(ROOT, 'data', 'reports'), exist_ok=True)
json.dump(rep, open(os.path.join(ROOT, 'data', 'reports', 'bert_eval.json'), 'w'), ensure_ascii=False, indent=1)
