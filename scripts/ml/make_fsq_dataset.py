"""Foursquare OS Places(일본) 이름 → 세부 카테고리(rules/categories.json) 학습 데이터.

- 학습·검증: Foursquare 음식점 중 OSM 과 매칭되지 않은 곳 (영업중, unresolved_flags 없음)
- 테스트: OSM 음식점 중 Foursquare 와 매칭된 곳 (scripts/fsq_match_osm.py), 정답은 Foursquare 카테고리
- 라벨: 가게의 Foursquare 카테고리 중 세부 카테고리로 대응되는 첫 번째 (exclude 만 있으면 제외)
- 같은 이름(정규화)은 한 번만, 라벨은 다수결. 클래스당 최대 CAP 개
- 다중 라벨(labels): 가게의 Foursquare 카테고리 전부. 같은 이름 여러 곳이면 그 이름 가게의 MIN_SHARE 이상이 붙인 라벨
출력: data/interim/<OUT_DS, 기본 cuisine_ds_fsq>/{train,val,test}.jsonl, labels.json
"""
import os, sys, json, random
from collections import Counter, defaultdict
import duckdb

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src')); sys.path.insert(0, os.path.join(ROOT, 'scripts', 'labeling'))
from japan_rec.textnorm import norm
from japan_rec.rules import load as load_rule
from name_rules import label as name_label

RELEASE = os.environ.get('RELEASE', '2026-09-15')
CAP, VAL, SEED = int(os.environ.get('CAP', 6000)), 0.05, 42
OUT = os.path.join(ROOT, 'data/interim', os.environ.get('OUT_DS', 'cuisine_ds_fsq'))
MIN_SHARE = 0.2
random.seed(SEED)

cats = load_rule('categories.json')
LEAF = {l: f['id'] for f in cats['fine'] for l in f['fsq']}
PARENT = {f['id']: f['parent'] for f in cats['fine']}


def fines(labels):
    out = []
    for c in labels or []:
        f = LEAF.get(c.split(' > ')[-1])
        if f and f not in out: out.append(f)
    return out


def fine(labels):
    fs = fines(labels)
    return fs[0] if fs else None


def multi(primary, place_sets):
    """같은 이름 가게들의 라벨 집합 → MIN_SHARE 이상 붙은 라벨 (대표 라벨 맨 앞)"""
    c = Counter(f for fs in place_sets for f in fs)
    return [primary] + sorted(f for f, k in c.items() if f != primary and k / len(place_sets) >= MIN_SHARE)


def has_kw(name):
    return name_label(name, use_brands=False)[0] is not None


matched = [json.loads(l) for l in open(os.path.join(ROOT, 'data/interim/fsq/osm_fsq_match.jsonl'))]
matched_ids = {m['fsq_place_id'] for m in matched}

rows = duckdb.sql(f"""
    SELECT fsq_place_id, name, fsq_category_labels FROM 'data/raw/fsq/places_jp_{RELEASE}.parquet'
    WHERE date_closed IS NULL AND len(coalesce(unresolved_flags, [])) = 0
      AND list_filter(fsq_category_labels, x -> x LIKE 'Dining and Drinking%') <> []
    ORDER BY fsq_place_id                  -- 병렬 스캔이라 순서가 매번 달라질 수 있음 → 고정 (재현성)
""").fetchall()
by_name, sets = defaultdict(Counter), defaultdict(list)
for pid, name, labels in rows:
    fs = fines(labels)
    if fs and pid not in matched_ids and len(norm(name)) >= 1:
        by_name[name.strip()][fs[0]] += 1
        sets[name.strip()].append(fs)
per_class = defaultdict(list)
for name, c in by_name.items():
    per_class[c.most_common(1)[0][0]].append(name)

train, val = [], []
for f in sorted(per_class):
    names = sorted(per_class[f])          # 순서 고정 뒤 섞기 (seed 42)
    random.shuffle(names)
    names = names[:CAP]
    k = max(1, int(len(names) * VAL))
    val += [{'name': n, 'label': f, 'labels': multi(f, sets[n])} for n in names[:k]]
    train += [{'name': n, 'label': f, 'labels': multi(f, sets[n])} for n in names[k:]]

test_by, test_sets = defaultdict(Counter), defaultdict(list)
for m in matched:
    fs = fines(m['fsq_categories'])
    if fs:
        test_by[m['osm_name'].strip()][fs[0]] += 1
        test_sets[m['osm_name'].strip()].append(fs)
test = [{'name': n, 'label': c.most_common(1)[0][0], 'labels': multi(c.most_common(1)[0][0], test_sets[n]), 'orig_label': None}
        for n, c in test_by.items()]
orig = {}
for m in matched: orig.setdefault(m['osm_name'].strip(), m['label'])
train_names = {norm(r['name']) for r in train}
for r in test:
    r['orig_label'] = orig[r['name']]
    r['seen_in_train'] = norm(r['name']) in train_names
for r in train + val + test:
    r['has_keyword'] = has_kw(r['name'])
    r['parent'] = PARENT[r['label']]

os.makedirs(OUT, exist_ok=True)
labels = sorted(f['id'] for f in cats['fine'] if not f.get('rule_only'))  # rule_only(okinawa_soba 등)는 학습 클래스 아님
json.dump(labels, open(f'{OUT}/labels.json', 'w'))
for split, rs in (('train', train), ('val', val), ('test', test)):
    random.shuffle(rs)
    with open(f'{OUT}/{split}.jsonl', 'w') as fo:
        for r in rs: fo.write(json.dumps(r, ensure_ascii=False) + '\n')
print(f'클래스 {len(labels)} | train {len(train):,} val {len(val):,} test {len(test):,} '
      f'(test 중 학습에 같은 이름 있음 {sum(r["seen_in_train"] for r in test):,})')
cnt = Counter(r['label'] for r in train)
print('train 클래스별 최소/최대:', cnt.most_common()[-5:], cnt.most_common(3))
