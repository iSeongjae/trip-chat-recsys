"""Geofabrik pbf → 역(railway=station, 노드) 이름·좌표. 위치 검색("교토역")용.
출력: data/interim/osm_stations_jp.json   실행: python3 scripts/extract_stations.py
"""
import osmium, json, os, glob
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data')
out = {}
for path in sorted(glob.glob(f'{R}/raw/osm_pbf/*.osm.pbf')):
    for o in osmium.FileProcessor(path).with_filter(osmium.filter.KeyFilter('railway')):
        if o.is_node() and o.tags.get('railway') == 'station' and 'name' in o.tags:
            out[o.id] = dict(name={t.k: t.v for t in o.tags if t.k.startswith('name')}, lat=o.location.lat, lon=o.location.lon,
                             operator=o.tags.get('operator'), station=o.tags.get('station'))
    print(path, len(out), flush=True)
json.dump(list(out.values()), open(f'{R}/interim/osm_stations_jp.json', 'w'), ensure_ascii=False)
print('역', len(out))
