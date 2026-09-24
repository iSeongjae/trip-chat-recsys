"""OSM brand:wikidata QID 의 Wikidata 정보(라벨·설명·P31·P2012·P452) 수집 → data/raw/wikidata/brands.json
사용: set -a && . ./.env && set +a && python3 scripts/labeling/fetch_brands_wikidata.py   (CONTACT 필요)"""
import json, os, urllib.parse, urllib.request
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
UA = f"japan-traveler-research/0.1 ({os.environ['CONTACT']})"
O = json.load(open(os.path.join(ROOT, 'data/interim/osm_eateries_jp.json')))
Q = sorted({q.strip() for o in O if o['name'].get('name') for q in (o['tags'].get('brand:wikidata') or '').split(';') if q.strip().startswith('Q')})
S = '''SELECT ?item ?ja ?en ?dja ?den
 (GROUP_CONCAT(DISTINCT ?p31l;separator="|") AS ?p31) (GROUP_CONCAT(DISTINCT ?cuil;separator="|") AS ?cuisine) (GROUP_CONCAT(DISTINCT ?indl;separator="|") AS ?industry)
WHERE { VALUES ?item { %s }
 OPTIONAL{?item rdfs:label ?ja FILTER(LANG(?ja)="ja")} OPTIONAL{?item rdfs:label ?en FILTER(LANG(?en)="en")}
 OPTIONAL{?item schema:description ?dja FILTER(LANG(?dja)="ja")} OPTIONAL{?item schema:description ?den FILTER(LANG(?den)="en")}
 OPTIONAL{?item wdt:P31 ?p; OPTIONAL{?p rdfs:label ?p31l FILTER(LANG(?p31l)="en")}}
 OPTIONAL{?item wdt:P2012 ?c; OPTIONAL{?c rdfs:label ?cuil FILTER(LANG(?cuil)="en")}}
 OPTIONAL{?item wdt:P452 ?i; OPTIONAL{?i rdfs:label ?indl FILTER(LANG(?indl)="en")}}
} GROUP BY ?item ?ja ?en ?dja ?den'''
out = {}
for i in range(0, len(Q), 150):
    q = S % ' '.join('wd:' + x for x in Q[i:i + 150])
    req = urllib.request.Request('https://query.wikidata.org/sparql', data=urllib.parse.urlencode({'query': q}).encode(),
                                 headers={'User-Agent': UA, 'Accept': 'application/sparql-results+json'})
    for b in json.load(urllib.request.urlopen(req, timeout=120))['results']['bindings']:
        k = b['item']['value'].rsplit('/', 1)[1]; g = lambda n: b[n]['value'] if n in b else ''
        out.setdefault(k, {'ja': g('ja'), 'en': g('en'), 'desc_ja': g('dja'), 'desc_en': g('den'),
                           'p31': g('p31'), 'cuisine': g('cuisine'), 'industry': g('industry')})
json.dump(out, open(os.path.join(ROOT, 'data/raw/wikidata/brands.json'), 'w'), ensure_ascii=False, indent=0)
print(f'브랜드 {len(out)} / {len(Q)} | P2012 있음 {sum(1 for v in out.values() if v["cuisine"])} | 설명 있음 {sum(1 for v in out.values() if v["desc_ja"] or v["desc_en"])}')
