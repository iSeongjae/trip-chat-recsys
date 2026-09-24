# OSM 관광지의 wikidata 태그 → Wikidata API(wbgetentities)로 필요한 필드만 저장 (이어받기 지원)
import json,os,time,urllib.request,urllib.parse,urllib.error
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data')
OUT=f'{R}/raw/wikidata/entities.jsonl'
UA=f"japan-traveler-research/0.1 ({os.environ['CONTACT']})"
PROPS={'P31':'instance_of','P1435':'heritage','P625':'coord','P18':'image','P856':'website','P3134':'tripadvisor_id'}
A=json.load(open(f'{R}/interim/osm_attractions_jp.json'))
qids=sorted({q.strip() for a in A if 'wikidata' in a for q in a['wikidata'].split(';') if q.strip().startswith('Q')})
done=set()
if os.path.exists(OUT):
    for l in open(OUT): done.add(json.loads(l)['qid'])
todo=[q for q in qids if q not in done]
print('QID',len(qids),'남음',len(todo),flush=True)
def val(c):
    v=c['mainsnak'].get('datavalue',{}).get('value')
    if isinstance(v,dict): return v.get('id') or ({'lat':v['latitude'],'lon':v['longitude']} if 'latitude' in v else v)
    return v
with open(OUT,'a') as f:
    for i in range(0,len(todo),50):
        ids='|'.join(todo[i:i+50])
        q=urllib.parse.urlencode({'action':'wbgetentities','ids':ids,'props':'labels|descriptions|claims|sitelinks','languages':'ko|ja|en','format':'json'})
        for t in range(5):
            try:
                req=urllib.request.Request('https://www.wikidata.org/w/api.php?'+q,headers={'User-Agent':UA})
                ents=json.load(urllib.request.urlopen(req,timeout=60))['entities']; break
            except urllib.error.HTTPError as e:
                w=int(e.headers.get('Retry-After') or 30*(t+1)); print('retry',e.code,'wait',w,flush=True); time.sleep(w)
            except Exception as e: print('retry',e,flush=True); time.sleep(10*(t+1))
        else: raise SystemExit('failed')
        for qid,e in ents.items():
            if 'missing' in e: f.write(json.dumps({'qid':qid,'missing':True})+'\n'); continue
            sl=e.get('sitelinks',{})
            rec={'qid':e['id'],'requested':qid,
                 'label':{k:v['value'] for k,v in e.get('labels',{}).items()},
                 'desc':{k:v['value'] for k,v in e.get('descriptions',{}).items()},
                 'wiki_count':sum(1 for k in sl if k.endswith('wiki') and k not in ('commonswiki','specieswiki','metawiki','wikidatawiki')),
                 'wiki_titles':{k:sl[k]['title'] for k in ('kowiki','jawiki','enwiki') if k in sl},
                 'wikivoyage':{k:sl[k]['title'] for k in ('jawikivoyage','enwikivoyage') if k in sl}}
            for p,n in PROPS.items():
                vs=[val(c) for c in e.get('claims',{}).get(p,[])]
                if vs: rec[n]=vs if p in ('P31','P1435') else vs[0]
            f.write(json.dumps(rec,ensure_ascii=False)+'\n')
        f.flush(); time.sleep(3)
        if (i//50)%50==0: print(i+50,'/',len(todo),flush=True)
print('완료',flush=True)
