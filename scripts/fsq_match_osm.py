"""OSM 음식점 ↔ Foursquare OS Places(일본) 매칭.

같은 가게 = 거리 100m 이내 + 이름 같음(textnorm.same_name). 가장 가까운 것 하나만.
입력: data/interim/gold/all_labels.jsonl (OSM 이름·좌표·라벨), data/raw/fsq/places_jp_<release>.parquet
출력: data/interim/fsq/osm_fsq_match.jsonl

실행: python3 scripts/fsq_match_osm.py [release]
"""
import os, sys, json, math
from collections import defaultdict, Counter
import duckdb

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))
from japan_rec.textnorm import same_name

RELEASE = sys.argv[1] if len(sys.argv) > 1 else '2026-09-15'
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
FSQ = os.path.join(ROOT, f'data/raw/fsq/places_jp_{RELEASE}.parquet')
OUT = os.path.join(ROOT, 'data/interim/fsq')
MAX_M = 100
CELL = 0.001  # 약 100m 격자


def dist_m(a, b, c, d):
    x = math.radians(d - b) * math.cos(math.radians((a + c) / 2))
    return 6371000 * math.hypot(x, math.radians(c - a))


rows = duckdb.sql(f"""
    SELECT fsq_place_id, name, latitude, longitude, date_closed, date_refreshed,
           fsq_category_labels, unresolved_flags
    FROM '{FSQ}'
    WHERE latitude IS NOT NULL AND list_filter(fsq_category_labels, x -> x LIKE 'Dining and Drinking%') <> []
    ORDER BY fsq_place_id          -- 같은 거리일 때 고르는 가게가 실행마다 바뀌지 않게 (재현성)
""").fetchall()
grid = defaultdict(list)
for r in rows:
    grid[(int(r[2] / CELL), int(r[3] / CELL))].append(r)
print(f'FSQ 일본 음식점 {len(rows):,}', flush=True)

os.makedirs(OUT, exist_ok=True)
n = 0
with open(os.path.join(OUT, 'osm_fsq_match.jsonl'), 'w') as f:
    for line in open(os.path.join(ROOT, 'data/interim/gold/all_labels.jsonl')):
        o = json.loads(line)
        gi, gj = int(o['lat'] / CELL), int(o['lon'] / CELL)
        best = None
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for r in grid.get((gi + di, gj + dj), ()):
                    d = dist_m(o['lat'], o['lon'], r[2], r[3])
                    if d <= MAX_M and (best is None or d < best[0]) and same_name(o['name'], r[1]):
                        best = (d, r)
        if best:
            d, r = best
            n += 1
            f.write(json.dumps({'osm_id': o['id'], 'osm_name': o['name'], 'label': o['label'], 'method': o['method'],
                                'fsq_place_id': r[0], 'fsq_name': r[1], 'dist_m': round(d),
                                'fsq_categories': r[6], 'date_closed': r[4], 'date_refreshed': str(r[5]),
                                'unresolved_flags': r[7]}, ensure_ascii=False) + '\n')
print(f'매칭 {n:,}', flush=True)
