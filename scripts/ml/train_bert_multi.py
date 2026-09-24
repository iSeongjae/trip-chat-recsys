"""일본어 BERT 다중 라벨 미세조정: 가게 이름 → 세부 카테고리 여러 개 (sigmoid + BCE).
데이터: data/interim/cuisine_ds_fsq_ml (make_fsq_dataset.py 에 OUT_DS=cuisine_ds_fsq_ml), 각 행의 'labels'
검증: top-1 이 정답 라벨 중 하나인 비율(hit@1) 과 macro-F1(임계값 THRESH) 로 최적 에폭 선택. 테스트는 마지막 1회.
실행: (scripts/ml 에서) DS=cuisine_ds_fsq_ml RUN=cuisine_bert_fsq_ml python3 train_bert_multi.py
"""
import json, os, random, time, numpy as np, torch
from torch.utils.data import DataLoader
from transformers import AutoTokenizer, AutoModelForSequenceClassification, get_linear_schedule_with_warmup
from sklearn.metrics import f1_score
from eval_utils import load, D

MODEL = os.environ.get('MODEL', 'tohoku-nlp/bert-base-japanese-v3')
EPOCHS, BS, LR, MAXLEN, SEED = int(os.environ.get('EPOCHS', 3)), 64, 3e-5, 32, 42
THRESH = float(os.environ.get('THRESH', 0.5))
OUT = os.path.join(D, '..', '..', 'models', os.environ.get('RUN', 'cuisine_bert_fsq_ml'))
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
dev = 'mps' if torch.backends.mps.is_available() else 'cpu'
labels = json.load(open(f'{D}/labels.json')); l2i = {l: i for i, l in enumerate(labels)}
tr, va, te = load('train'), load('val'), load('test')
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForSequenceClassification.from_pretrained(
    MODEL, num_labels=len(labels), problem_type='multi_label_classification').to(dev)


def target(rows):
    y = np.zeros((len(rows), len(labels)), np.float32)
    for i, r in enumerate(rows):
        for l in r['labels']: y[i, l2i[l]] = 1
    return y


def batches(rows, shuffle):
    def collate(b):
        enc = tok([r['name'] for r in b], padding=True, truncation=True, max_length=MAXLEN, return_tensors='pt')
        enc['labels'] = torch.tensor(target(b)); return enc
    return DataLoader(rows, batch_size=BS, shuffle=shuffle, collate_fn=collate)


@torch.no_grad()
def predict(rows):
    model.eval(); P = []
    for b in batches(rows, False):
        b = {k: v.to(dev) for k, v in b.items() if k != 'labels'}
        P.append(torch.sigmoid(model(**b).logits).float().cpu().numpy())
    return np.concatenate(P)


def scores(rows, P):
    Y = target(rows)
    hit1 = Y[np.arange(len(rows)), P.argmax(1)].mean()
    return hit1, f1_score(Y, P >= THRESH, average='macro', zero_division=0), f1_score(Y, P >= THRESH, average='micro', zero_division=0)


# 양성 가중치: 드문 라벨일수록 (빈도^-0.5, 평균 1로 정규화)
freq = target(tr).sum(0) + 1
pw = (freq.mean() / freq) ** 0.5
lossf = torch.nn.BCEWithLogitsLoss(pos_weight=torch.tensor(pw / pw.mean(), dtype=torch.float32).to(dev))
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
steps = EPOCHS * len(batches(tr, True)); sch = get_linear_schedule_with_warmup(opt, int(0.06 * steps), steps)
best = -1; t0 = time.time()
for ep in range(1, EPOCHS + 1):
    model.train(); tot = 0
    for i, b in enumerate(batches(tr, True)):
        b = {k: v.to(dev) for k, v in b.items()}
        y = b.pop('labels'); loss = lossf(model(**b).logits, y); loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step(); sch.step(); opt.zero_grad(); tot += loss.item()
        if i % 200 == 0: print(f'  ep{ep} step {i} loss {loss.item():.4f} ({time.time()-t0:.0f}s)', flush=True)
    h1, maf, mif = scores(va, predict(va))
    print(f'[epoch {ep}] train loss {tot/(i+1):.4f} | val hit@1 {h1:.1%} macro-F1 {maf:.3f} micro-F1 {mif:.3f} ({time.time()-t0:.0f}s)', flush=True)
    if maf > best:
        best = maf; model.save_pretrained(OUT); tok.save_pretrained(OUT); print('   → best 저장', flush=True)

model = AutoModelForSequenceClassification.from_pretrained(OUT).to(dev)
P = predict(te)
h1, maf, mif = scores(te, P)
print(f'[test] hit@1 {h1:.1%} macro-F1 {maf:.3f} micro-F1 {mif:.3f}')
np.save(f'{OUT}/test_prob.npy', P.astype(np.float16))
json.dump(labels, open(f'{OUT}/labels.json', 'w'))
