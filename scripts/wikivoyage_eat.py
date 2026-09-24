"""영어 Wikivoyage(CC BY-SA) 일본 문서의 먹거리(eat)·술(drink) 항목 추출 + OSM 음식점과 매칭 (커버리지 확인용).

- 덤프: https://dumps.wikimedia.org/enwikivoyage/latest/enwikivoyage-latest-pages-articles.xml.bz2 (없으면 받음, UA 연락처는 .env CONTACT)
- 일본 문서: {{IsPartOf|...}} 를 따라 올라가 'Japan' 에 닿는 문서, 또는 (중간 문서가 없어 끊긴 경우) 항목 좌표가
  일본 OSM 음식점 근처(0.05° 격자 ±1)에 있는 문서
- 항목: {{eat|...}}, {{drink|...}}, 또는 Eat/Drink 절 안의 {{listing|...}}
- 매칭: 좌표 있는 항목 → 100m 안 OSM 음식점 중 이름(name 또는 alt 의 일본어)이 같은 곳
출력: data/raw/wikivoyage/en_japan_eat.jsonl, data/interim/wikivoyage/eat_osm_match.jsonl
실행: set -a && . ./.env && set +a && python3 scripts/wikivoyage_eat.py
"""
import os, sys, re, bz2, json, math, urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict, Counter

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec.textnorm import same_name

RAW = os.path.join(ROOT, 'data/raw/wikivoyage'); os.makedirs(RAW, exist_ok=True)
DUMP = os.path.join(RAW, 'enwikivoyage-latest-pages-articles.xml.bz2')
if not os.path.exists(DUMP):
    req = urllib.request.Request('https://dumps.wikimedia.org/enwikivoyage/latest/enwikivoyage-latest-pages-articles.xml.bz2',
                                 headers={'User-Agent': f"japan-rec-research/0.1 ({os.environ['CONTACT']})"})
    with urllib.request.urlopen(req) as r, open(DUMP, 'wb') as f:
        while chunk := r.read(1 << 20): f.write(chunk)

parent, text = {}, {}
for _, el in ET.iterparse(bz2.open(DUMP), events=('end',)):
    if el.tag.endswith('}page'):
        ns = el.find('{*}ns').text
        if ns == '0':
            title = el.find('{*}title').text
            t = el.find('{*}revision/{*}text').text or ''
            m = re.search(r'\{\{\s*IsPartOf\s*\|\s*([^}|]+)', t, re.I)
            if m: parent[title] = m.group(1).strip().replace('_', ' ')
            if re.search(r'\{\{\s*(eat|drink)\s*\|', t, re.I) or '==Eat==' in t.replace(' ', ''):
                text[title] = t
        el.clear()


def in_japan(t, seen=()):
    if t == 'Japan': return True
    p = parent.get(t)
    return bool(p) and p not in seen and len(seen) < 15 and in_japan(p, seen + (t,))


def fields(body):
    d = {}
    for part in re.split(r'\n?\s*\|(?![^\[]*\]\])', body):
        if '=' in part:
            k, v = part.split('=', 1); d[k.strip().lower()] = v.strip()
    return d


osm = json.load(open(os.path.join(ROOT, 'data/interim/osm_eateries_jp.json')))
JP_CELLS = {(int(o['lat'] / 0.05), int(o['lon'] / 0.05)) for o in osm if o['lat'] is not None}


def near_japan(lat, lon):
    i, j = int(lat / 0.05), int(lon / 0.05)
    return any((i + a, j + b) in JP_CELLS for a in (-1, 0, 1) for b in (-1, 0, 1))


def coords_in_japan(t):
    pts = [(float(a), float(b)) for a, b in re.findall(r'\|\s*lat\s*=\s*(\d+\.?\d*)\s*\|\s*long\s*=\s*(\d+\.?\d*)\s*[|}\n]', t)]
    return bool(pts) and sum(near_japan(*p) for p in pts) / len(pts) >= 0.8


rows = []
for title, t in text.items():
    if not (in_japan(title) or coords_in_japan(t)): continue
    sec = None
    for line_sec in re.split(r'(\n==[^=].*?==\s*\n)', t):
        h = re.match(r'\n==\s*([^=]+?)\s*==', line_sec)
        if h: sec = h.group(1).strip().lower(); continue
        for m in re.finditer(r'\{\{\s*(eat|drink|listing)\s*\|(.*?)\}\}', line_sec, re.S | re.I):
            kind = m.group(1).lower()
            if kind == 'listing' and sec not in ('eat', 'drink'): continue
            d = fields(m.group(2))
            if not d.get('name'): continue
            try: lat, lon = float(d.get('lat')), float(d.get('long'))
            except (TypeError, ValueError): lat = lon = None
            rows.append(dict(article=title, type=kind if kind != 'listing' else sec, name=d['name'], alt=d.get('alt', ''),
                             lat=lat, lon=lon, price=d.get('price', ''), content=d.get('content', ''), wikidata=d.get('wikidata', '')))
with open(os.path.join(RAW, 'en_japan_eat.jsonl'), 'w') as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')

# OSM 음식점과 매칭
grid = defaultdict(list)
for o in osm:
    if o['lat'] is not None: grid[(int(o['lat'] / 0.001), int(o['lon'] / 0.001))].append(o)


def dist(a, b, c, d):
    return 6371000 * math.hypot(math.radians(d - b) * math.cos(math.radians((a + c) / 2)), math.radians(c - a))


os.makedirs(os.path.join(ROOT, 'data/interim/wikivoyage'), exist_ok=True)
st = Counter()
with open(os.path.join(ROOT, 'data/interim/wikivoyage/eat_osm_match.jsonl'), 'w') as f:
    for r in rows:
        st[r['type']] += 1
        if r['lat'] is None: continue
        st['좌표 있음'] += 1
        names = [r['name']] + [x for x in re.split(r'[,;/]| or ', r['alt']) if x.strip()]
        gi, gj = int(r['lat'] / 0.001), int(r['lon'] / 0.001)
        best = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for o in grid.get((gi + di, gj + dj), ()):
                    dd = dist(r['lat'], r['lon'], o['lat'], o['lon'])
                    on = [v for k, v in o['name'].items()]
                    if dd <= 100 and any(same_name(a, b) for a in names for b in on) and (not best or dd < best[0]):
                        best = (dd, o)
        if best:
            st['OSM 매칭'] += 1
            f.write(json.dumps(dict(osm_id=best[1]['osm_id'], dist_m=round(best[0]), **r), ensure_ascii=False) + '\n')
arts = Counter(r['article'] for r in rows)
print(f"일본 문서 {len(arts):,}개 | 항목 {len(rows):,} (eat {st['eat']:,}, drink {st['drink']:,}) | 좌표 있음 {st['좌표 있음']:,} | OSM 음식점 매칭 {st['OSM 매칭']:,}")
print(f"설명 있는 항목 {sum(1 for r in rows if len(r['content']) >= 20):,} | 가격 있는 항목 {sum(1 for r in rows if r['price']):,}")
print('항목 많은 문서:', arts.most_common(8))
