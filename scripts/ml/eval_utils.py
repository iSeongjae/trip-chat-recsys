import json, os, numpy as np
from sklearn.metrics import accuracy_score, f1_score
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', os.environ.get('DS', 'cuisine_ds'))

def load(split):
    return [json.loads(l) for l in open(f'{D}/{split}.jsonl')]

def report(title, rows, pred, conf=None):
    y = [r['label'] for r in rows]; hk = np.array([r['has_keyword'] for r in rows])
    out = {'acc': accuracy_score(y, pred), 'macro_f1': f1_score(y, pred, average='macro')}
    nk = ~hk
    out['acc_no_keyword'] = accuracy_score(np.array(y)[nk], np.array(pred)[nk])
    print(f"[{title}] 정확도 {out['acc']:.1%} | macro-F1 {out['macro_f1']:.3f} | 키워드 없는 이름 정확도 {out['acc_no_keyword']:.1%}")
    if conf is not None:
        conf = np.array(conf)
        for th in (0.5, 0.7, 0.9):
            m = conf >= th
            print(f"   확신도≥{th}: 적용 {m.mean():.0%}, 정확도 {accuracy_score(np.array(y)[m], np.array(pred)[m]):.1%}")
    return out
