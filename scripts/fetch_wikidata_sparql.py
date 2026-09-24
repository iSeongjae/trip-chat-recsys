# 남은 QID를 Wikidata SPARQL로 필요한 필드만 받아 entities.jsonl에 이어 붙임 (fetch_wikidata.py와 같은 스키마)
import json,os,time,urllib.request,urllib.parse,urllib.error
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data')
OUT=f'{R}/raw/wikidata/entities.jsonl'
UA=f"japan-traveler-research/0.1 ({os.environ['CONTACT']})"
A=json.load(open(f'{R}/interim/osm_attractions_jp.json'))
qids=sorted({q.strip() for a in A if 'wikidata' in a for q in a['wikidata'].split(';') if q.strip().startswith('Q')})
done={json.loads(l).get('requested') for l in open(OUT)}
todo=[q for q in qids if q not in done]
print('QID',len(qids),'남음',len(todo),flush=True)
Q='''SELECT ?item ?ko ?ja ?en ?dko ?dja ?den ?wc ?kowiki ?jawiki ?enwiki ?javoy ?envoy
 (GROUP_CONCAT(DISTINCT STRAFTER(STR(?p31),"entity/");separator="|") AS ?inst)
 (GROUP_CONCAT(DISTINCT STRAFTER(STR(?her),"entity/");separator="|") AS ?heritage)
 (SAMPLE(?c) AS ?coord) (SAMPLE(?img) AS ?image) (SAMPLE(?web) AS ?website) (SAMPLE(?ta) AS ?tripadvisor)
WHERE { VALUES ?item { %s }
 OPTIONAL{?item rdfs:label ?ko FILTER(LANG(?ko)="ko")} OPTIONAL{?item rdfs:label ?ja FILTER(LANG(?ja)="ja")} OPTIONAL{?item rdfs:label ?en FILTER(LANG(?en)="en")}
 OPTIONAL{?item schema:description ?dko FILTER(LANG(?dko)="ko")} OPTIONAL{?item schema:description ?dja FILTER(LANG(?dja)="ja")} OPTIONAL{?item schema:description ?den FILTER(LANG(?den)="en")}
 OPTIONAL{ SELECT ?item (COUNT(?art) AS ?wc) WHERE { VALUES ?item { %s } ?art schema:about ?item; schema:isPartOf ?s. FILTER(STRENDS(STR(?s),".wikipedia.org/")) } GROUP BY ?item }
 OPTIONAL{?a1 schema:about ?item; schema:isPartOf <https://ko.wikipedia.org/>; schema:name ?kowiki}
 OPTIONAL{?a2 schema:about ?item; schema:isPartOf <https://ja.wikipedia.org/>; schema:name ?jawiki}
 OPTIONAL{?a3 schema:about ?item; schema:isPartOf <https://en.wikipedia.org/>; schema:name ?enwiki}
 OPTIONAL{?a4 schema:about ?item; schema:isPartOf <https://ja.wikivoyage.org/>; schema:name ?javoy}
 OPTIONAL{?a5 schema:about ?item; schema:isPartOf <https://en.wikivoyage.org/>; schema:name ?envoy}
 OPTIONAL{?item wdt:P31 ?p31} OPTIONAL{?item wdt:P1435 ?her}
 OPTIONAL{?item p:P625/psv:P625 [wikibase:geoLatitude ?lat; wikibase:geoLongitude ?lon]. BIND(CONCAT(STR(?lat),",",STR(?lon)) AS ?c)}
 OPTIONAL{?item wdt:P18 ?img} OPTIONAL{?item wdt:P856 ?web} OPTIONAL{?item wdt:P3134 ?ta}
} GROUP BY ?item ?ko ?ja ?en ?dko ?dja ?den ?wc ?kowiki ?jawiki ?enwiki ?javoy ?envoy'''
def run(q):
    for t in range(6):
        try:
            req=urllib.request.Request('https://query.wikidata.org/sparql',data=urllib.parse.urlencode({'query':q}).encode(),
                headers={'User-Agent':UA,'Accept':'application/sparql-results+json'})
            return json.load(urllib.request.urlopen(req,timeout=120))['results']['bindings']
        except urllib.error.HTTPError as e:
            w=int(e.headers.get('Retry-After') or 30*(t+1)); print('retry',e.code,'wait',w,flush=True); time.sleep(w)
        except Exception as e: print('retry',e,flush=True); time.sleep(20*(t+1))
    raise SystemExit('failed')
B=300; empty=[]
with open(OUT,'a') as f:
    for i in range(0,len(todo),B):
        ch=todo[i:i+B]; vals=' '.join('wd:'+q for q in ch)
        rows={}
        for b in run(Q%(vals,vals)):
            q=b['item']['value'].rsplit('/',1)[1]; g=lambda k:b[k]['value'] if k in b else None
            if q in rows: continue  # 라벨 중복 등으로 여러 행이면 첫 행만
            rec={'qid':q,'requested':q,'label':{l:g(l) for l in ('ko','ja','en') if g(l)},'desc':{l:g('d'+l) for l in ('ko','ja','en') if g('d'+l)},
                 'wiki_count':int(g('wc') or 0),'wiki_titles':{k:g(k) for k in ('kowiki','jawiki','enwiki') if g(k)},
                 'wikivoyage':{k+'wikivoyage':g(k+'voy') for k in ('ja','en') if g(k+'voy')}}
            if g('inst'): rec['instance_of']=g('inst').split('|')
            if g('heritage'): rec['heritage']=g('heritage').split('|')
            if g('coord'): la,lo=g('coord').split(','); rec['coord']={'lat':float(la),'lon':float(lo)}
            if g('image'): rec['image']=urllib.parse.unquote(g('image').rsplit('/',1)[1]).replace('_',' ')
            if g('website'): rec['website']=g('website')
            if g('tripadvisor'): rec['tripadvisor_id']=g('tripadvisor')
            if not rec['label'] and 'instance_of' not in rec: empty.append(q); continue  # 삭제/redirect 추정 → API로 따로
            rows[q]=rec
        for r in rows.values(): f.write(json.dumps(r,ensure_ascii=False)+'\n')
        f.flush(); print(i+len(ch),'/',len(todo),flush=True); time.sleep(2)
json.dump(empty,open(f'{R}/raw/wikidata/unresolved_qids.json','w'))
print('완료. 라벨·종류 없는 QID(삭제/redirect 추정):',len(empty),flush=True)
