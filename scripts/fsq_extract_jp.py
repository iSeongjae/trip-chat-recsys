"""Foursquare OS Places (Apache 2.0) 에서 일본(country='JP')만 추출.

출처: https://huggingface.co/datasets/foursquare/fsq-os-places (gated, .env 의 HF_TOKEN 필요.
fine-grained 토큰이면 'public gated repos 읽기' 권한을 켜야 함)
출력: data/raw/fsq/places_jp_<release>.parquet, data/raw/fsq/categories_<release>.parquet

실행: set -a && . ./.env && set +a && python3 scripts/fsq_extract_jp.py [release]
"""
import os, sys, time
import duckdb

RELEASE = sys.argv[1] if len(sys.argv) > 1 else '2026-09-15'
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
OUT = os.path.join(ROOT, 'data/raw/fsq')
BASE = f'hf://datasets/foursquare/fsq-os-places/release/dt={RELEASE}'
COLS = ('fsq_place_id, name, latitude, longitude, address, locality, region, postcode, admin_region, '
        'country, date_created, date_refreshed, date_closed, tel, website, '
        'fsq_category_ids, fsq_category_labels, unresolved_flags')

os.makedirs(OUT, exist_ok=True)
con = duckdb.connect()
con.execute('INSTALL httpfs; LOAD httpfs;')
con.execute(f"CREATE SECRET hf (TYPE huggingface, TOKEN '{os.environ['HF_TOKEN']}')")

t = time.time()
cat_out = os.path.join(OUT, f'categories_{RELEASE}.parquet')
con.execute(f"COPY (SELECT * FROM '{BASE}/categories/parquet/*.parquet') TO '{cat_out}' (FORMAT parquet)")
print('categories', con.execute(f"SELECT count(*) FROM '{cat_out}'").fetchone()[0], f'{time.time()-t:.0f}s', flush=True)

t = time.time()
jp_out = os.path.join(OUT, f'places_jp_{RELEASE}.parquet')
con.execute(f"COPY (SELECT {COLS} FROM '{BASE}/places/parquet/*.parquet' WHERE country = 'JP') "
            f"TO '{jp_out}' (FORMAT parquet, COMPRESSION zstd)")
print('places JP', con.execute(f"SELECT count(*) FROM '{jp_out}'").fetchone()[0], f'{time.time()-t:.0f}s', flush=True)
