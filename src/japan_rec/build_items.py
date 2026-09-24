"""아이템 DB (최소 속성) 생성: 식당(OSM + 라벨 파이프라인 all_labels_fsq.jsonl) + 관광지(OSM + Wikidata 인기도).

사용: (src/ 에서) python3 -m japan_rec.build_items            → data/processed/items_japan.json (일본 전역)
      REGION=fukuoka python3 -m japan_rec.build_items         → data/processed/items_fukuoka.json
식당: 폐업(Foursquare date_closed) 제외. cuisine=상위 26코드, fine=세부 카테고리(Foursquare·이름 키워드), broad=넓은 분류,
      sub=상위 코드의 한국어 이름(취향 학습·표시용).
"""
import collections, json, math, os, statistics

from .geo import haversine_km
from .textnorm import same_name, name_keys
from .categories import KO, name_fine, PARENT, _C as _CATS
from .translit import to_korean, JA, HANGUL

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
DATA = os.path.join(ROOT, 'data')
REGIONS = {'fukuoka': (33.45, 33.72, 130.25, 130.60)}  # 후쿠오카시 + 다자이후 일대
REGION = os.environ.get('REGION')
BOX = REGIONS[REGION] if REGION else (20.0, 46.0, 122.0, 154.0)  # 기본: 일본 전역

OSM_AMENITY = {'restaurant': 'meal', 'fast_food': 'meal', 'food_court': 'meal', 'cafe': 'cafe', 'ice_cream': 'cafe', 'pub': 'bar', 'bar': 'bar'}
ATTR_CAT = {'구경': 'sight', '신사·사찰': 'sight', '산책·자연': 'walk', '휴식': 'rest', '쇼핑': 'shop'}
ATTR_SUB = {'tourism=museum': '박물관', 'tourism=gallery': '미술관', 'tourism=attraction': '명소', 'tourism=viewpoint': '전망대', 'tourism=zoo': '동물원',
            'tourism=aquarium': '수족관', 'tourism=theme_park': '테마파크', 'historic=castle': '성', 'historic=archaeological_site': '유적지',
            'leisure=park': '공원', 'leisure=garden': '정원', 'natural=beach': '해변', 'natural=peak': '산', 'waterway=waterfall': '폭포',
            'amenity=public_bath': '온천·목욕탕', 'leisure=sauna': '사우나', 'shop=mall': '쇼핑몰', 'shop=department_store': '백화점', 'shop=gift': '기념품점',
            'shop=variety_store': '잡화 할인점', 'shop=supermarket': '잡화 할인점', 'shop=chemist': '드럭스토어', 'shop=electronics': '전자제품',
            'shop=anime': '애니·취미', 'shop=hobby': '애니·취미', 'shop=games': '애니·취미', 'shop=video_games': '애니·취미'}
SKIP_ATTR = {'historic=memorial', 'historic=wayside_shrine', 'tourism=artwork', 'historic=boundary_stone', 'historic=milestone'}  # 관광 성격 약함


def in_box(lat, lon):
    return BOX[0] <= lat <= BOX[1] and BOX[2] <= lon <= BOX[3]


CAT_OF = {'cafe': 'cafe', 'sweets': 'cafe', 'bakery': 'cafe', 'izakaya': 'bar', 'bar': 'bar'}  # 그 외 상위 코드는 meal
AMENITY_SUB = {'meal': '식당', 'cafe': '카페·디저트', 'bar': '술집'}
_KIDS = collections.defaultdict(list)
for _f in _CATS['fine']:
    if not _f.get('rule_only'): _KIDS[_f['parent']].append(_f['id'])
ONLY_CHILD = {c: k[0] for c, k in _KIDS.items() if len(k) == 1}  # 상위 코드 = 세부 하나 (ramen, sushi, curry→japanese_curry 등)


def restaurants_osm():
    """OSM 음식점 + 라벨(all_labels_fsq.jsonl: 규칙 > Foursquare > LLM > BERT, 이름 보정). 폐업 제외."""
    lab = {json.loads(l)['id']: json.loads(l) for l in open(f'{DATA}/interim/gold/all_labels_fsq.jsonl')}
    items, closed = [], 0
    for o in json.load(open(f'{DATA}/interim/osm_eateries_jp.json')):
        a = lab.get(o['osm_id'])
        if not a or o['lat'] is None or not in_box(o['lat'], o['lon']):
            continue
        if a['closed']:
            closed += 1; continue
        c = a['label']
        cat = CAT_OF.get(c, 'meal') if c != 'unknown' else OSM_AMENITY[o['amenity']]
        fine = list(dict.fromkeys(a['fine'] + (name_fine(a['name'], c) if c != 'unknown' else [])))
        if not fine and c in ONLY_CHILD:
            fine = [ONLY_CHILD[c]]
        it = dict(id=f"osm_{o['osm_id']}", name=o['name'].get('name:ko') or a['name'], name_ja=a['name'], brand=o['tags'].get('brand'),
                  category=cat, cuisine=c, sub=KO.get(c) or AMENITY_SUB[cat], fine=fine, broad=a['broad'],
                  label_source=a['method'], lat=o['lat'], lon=o['lon'], popularity=0.3, sources=['osm'] + (['foursquare'] if a['fsq_place_id'] else []))
        items.append({k: v for k, v in it.items() if v not in (None, [])})
    return items, closed


def theme_signals():
    """테마 칩용 (관광지, 위키 문서 있는 곳만): 언어 지수 12개월 평균(local·known·hidden), 월별 계절성(ja 12개월 조회수 / 월평균)."""
    import csv
    acc = collections.defaultdict(lambda: collections.defaultdict(list))
    for r in csv.DictReader(open(f'{DATA}/interim/lang_indices_monthly.csv')):
        for k in ('local', 'known', 'hidden'):
            if r[k]: acc[r['qid']][k].append(float(r[k]))
    sig = {q: {k: round(statistics.mean(v), 3) for k, v in d.items() if v} for q, d in acc.items()}
    for l in open(f'{DATA}/raw/wikidata/pageviews_ja.jsonl'):
        x = json.loads(l)
        m = x.get('monthly') or {}
        if len(m) >= 12 and sum(m.values()) >= 1200:  # 월 100회 미만은 계절성이 잡음
            avg = sum(m.values()) / len(m)
            by_month = collections.defaultdict(list)
            for ym, v in m.items(): by_month[int(ym[4:])].append(v / avg)
            sig.setdefault(x['qid'], {})['season'] = [round(statistics.mean(by_month[i]), 2) if by_month[i] else 1.0 for i in range(1, 13)]
    return sig


def attractions():
    pop = json.load(open(f'{DATA}/interim/wikidata_popularity.json'))
    sig = theme_signals()
    ja = {x['qid']: x['views_12m'] for x in map(json.loads, open(f'{DATA}/raw/wikidata/pageviews_ja.jsonl'))
          if 'monthly' in x and x['views_12m'] is not None and x['qid'] in pop}
    v = sorted(ja.values()); n = len(v)
    lo, hi = math.log1p(v[int(n * .01)]), math.log1p(v[int(n * .99)])
    scaled = lambda x: min(max((math.log1p(x) - lo) / (hi - lo), 0), 1)  # log, 1~99% 자르기
    labels, info = {}, {}
    for l in open(f'{DATA}/raw/wikidata/entities.jsonl'):
        e = json.loads(l)
        if e.get('qid') in pop:
            labels[e['qid']] = e['label']
            wt = e.get('wiki_titles') or {}
            info[e['qid']] = {k: v for k, v in dict(desc=e.get('desc') or None, wiki={w: wt[w] for w in ('kowiki', 'jawiki', 'enwiki') if w in wt} or None,
                                                      image=e.get('image')).items() if v}
    items = []
    for a in json.load(open(f'{DATA}/interim/osm_attractions_jp.json')):
        if not a['name'].get('name') or not a['category'] or not in_box(a['lat'], a['lon']):
            continue
        key = next((f'{k}={a[k]}' for k in ('tourism', 'historic', 'amenity', 'leisure', 'natural', 'waterway', 'shop') if k in a), '')
        if key in SKIP_ATTR:
            continue
        sub = {'shinto': '신사', 'buddhist': '사찰'}.get(a.get('religion')) if key == 'amenity=place_of_worship' else ATTR_SUB.get(key, '기타 명소')
        if key == 'amenity=place_of_worship' and not sub:
            continue  # 교회 등은 이번 범위에서 제외
        qid = next((q.strip() for q in a.get('wikidata', '').split(';') if q.strip() in pop), None)
        if qid and qid in ja:
            p, tier = 0.2 + 0.8 * scaled(ja[qid]), 1
        elif qid:
            p, tier = 0.1, 2
        else:
            p, tier = 0.05, 3
        name = (labels.get(qid, {}).get('ko') if qid else None) or a['name'].get('name:ko') or a['name']['name']
        it = dict(id=f"osm_{a['osm_id']}", name=name, name_ja=a['name'].get('name'), brand=a.get('brand'), category=ATTR_CAT[a['category']], sub=sub,
                  lat=a['lat'], lon=a['lon'], popularity=round(p, 3), pop_tier=tier, wikidata=qid, sources=['osm'] + (['wikidata'] if qid else []))
        if qid:
            it.update(sig.get(qid, {})); it.update(info.get(qid, {}))
        items.append(it)
    return items


def dedupe_nearby(items, km=0.1):
    """같은 카테고리에서 이름이 같고 km 안이면 하나로 (예: 돈키호테가 점·건물로 두 번 등록). 정보가 많은 쪽을 남김."""
    rich = lambda it: (it.get('popularity', 0), len(it))
    keep, dropped = [], []
    kept_grid = collections.defaultdict(list)
    for it in sorted(items, key=rich, reverse=True):
        gx, gy = int(it['lat'] / 0.002), int(it['lon'] / 0.002)
        dup = next((k for dx in (-1, 0, 1) for dy in (-1, 0, 1) for k in kept_grid[(it['category'], gx + dx, gy + dy)]
                    if haversine_km(k['lat'], k['lon'], it['lat'], it['lon']) <= km and same_name(k['name'], it['name'])), None)
        if dup:
            dup['sources'] = sorted(set(dup['sources']) | set(it['sources'])); dropped.append((dup['name'], it['name']))
            continue
        keep.append(it); kept_grid[(it['category'], gx, gy)].append(it)
    return keep, dropped


def main():
    r, closed = restaurants_osm()
    a = attractions()
    items, dropped = dedupe_nearby(r + a)
    print(f'근접 중복 합침: {len(dropped)}  예: {dropped[:8]}')
    n_tr = 0
    for it in items:  # 화면 표시: 한글 이름(없으면 소리대로 한글 표기) + 일본어 원문 (translit.py)
        orig = it.get('name_ja') or it['name']
        if not HANGUL.search(it['name']) and JA.search(orig):
            it['name_ja'], it['name'], it['name_translit'] = orig, to_korean(orig), True
            n_tr += 1
    print(f'한글 표기로 바꾼 이름 {n_tr:,}')
    out = f"{DATA}/processed/items_{REGION or 'japan'}.json"
    json.dump(items, open(out, 'w'), ensure_ascii=False)
    print(f'식당 {len(r):,} (폐업 제외 {closed:,}) | 관광지 {len(a):,} | 합계 {len(items):,} → {out}')
    print('카테고리:', dict(collections.Counter(i['category'] for i in items)))
    print('식당 상위 코드:', collections.Counter(i['cuisine'] for i in r).most_common(12))
    print(f"세부 카테고리 있음 {sum(1 for i in r if i.get('fine')):,} / {len(r):,}")
    print('라벨 출처:', dict(collections.Counter(i['label_source'] for i in r)))
    print('관광지 인기도 단계:', dict(collections.Counter(i['pop_tier'] for i in a)))


if __name__ == '__main__':
    main()
