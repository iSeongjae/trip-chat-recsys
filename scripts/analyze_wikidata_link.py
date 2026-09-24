# OSM 관광지 ↔ Wikidata 연결 품질 점검 + 인기도(log 스케일) 계산
import json,os,math,collections,urllib.request,urllib.parse
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data')
UA=f"japan-traveler-research/0.1 ({os.environ['CONTACT']})"
A=json.load(open(f'{R}/interim/osm_attractions_jp.json'))
W={}
for l in open(f'{R}/raw/wikidata/entities.jsonl'):
    e=json.loads(l); W[e.get('requested',e['qid'])]=e
def dist(a,b,c,d):
    p1,p2=math.radians(a),math.radians(c)
    return 2*6371000*math.asin(math.sqrt(math.sin((p2-p1)/2)**2+math.cos(p1)*math.cos(p2)*math.sin(math.radians(d-b)/2)**2))
links=[(a,q.strip()) for a in A if 'wikidata' in a for q in a['wikidata'].split(';') if q.strip().startswith('Q')]
print(f'OSM 관광지 {len(A)} | wikidata 태그 {sum("wikidata" in a for a in A)} | 연결 {len(links)} | 고유 QID {len({q for _,q in links})}')
miss=sum(1 for _,q in links if W.get(q,{}).get('missing')); redir=sum(1 for _,q in links if q in W and not W[q].get('missing') and W[q]['qid']!=q)
print(f'삭제된 QID {miss} | 다른 항목으로 합쳐진(redirect) QID {redir}')
# 1) 한 QID에 OSM 여러 개
byq=collections.defaultdict(list)
for a,q in links: byq[q].append(a)
multi={q:v for q,v in byq.items() if len(v)>1}
print(f'\n[1] OSM 2곳 이상이 붙은 QID: {len(multi)} (OSM {sum(len(v) for v in multi.values())}곳)')
dist_n=collections.Counter(min(len(v),10) for v in multi.values()); print('   붙은 개수 분포(10+=10):',sorted(dist_n.items()))
top=sorted(multi.items(),key=lambda x:-len(x[1]))[:12]
# 2) 좌표 차이
ds=[]
for a,q in links:
    e=W.get(q)
    if e and 'coord' in e and isinstance(e['coord'],dict): ds.append((dist(a['lat'],a['lon'],e['coord']['lat'],e['coord']['lon']),a,e))
b=[0,100,500,1000,5000,10**9]; lab=['<100m','100-500m','500m-1km','1-5km','5km+']
cnt=collections.Counter(lab[next(i for i in range(5) if d<b[i+1])] for d,_,_ in ds)
print(f'\n[2] 좌표 비교 가능 {len(ds)} :',{k:f'{cnt[k]} ({cnt[k]/len(ds):.1%})' for k in lab})
# P31 라벨 조회 (상위 클래스만)
p31=collections.Counter(c for e in W.values() for c in e.get('instance_of',[]) if isinstance(c,str))
far_p31=collections.Counter(c for d,a,e in ds if d>=1000 for c in e.get('instance_of',[]) if isinstance(c,str))
multi_p31=collections.Counter(c for q in multi for c in W.get(q,{}).get('instance_of',[]) if isinstance(c,str))
need=list({q for q,_ in p31.most_common(40)}|{q for q,_ in far_p31.most_common(12)}|{q for q,_ in multi_p31.most_common(12)})
L={}
for i in range(0,len(need),50):
    qs=urllib.parse.urlencode({'action':'wbgetentities','ids':'|'.join(need[i:i+50]),'props':'labels','languages':'ko|en','format':'json'})
    for k,v in json.load(urllib.request.urlopen(urllib.request.Request('https://www.wikidata.org/w/api.php?'+qs,headers={'User-Agent':UA})))['entities'].items():
        L[k]=v.get('labels',{}).get('ko',v.get('labels',{}).get('en',{})).get('value',k)
lb=lambda c:[(L.get(q,q),n) for q,n in c]
print('   1km+ 떨어진 항목의 종류:',lb(far_p31.most_common(12)))
print('   예시:',[(a['name'].get('name'),e['label'].get('ja') or e['label'].get('en'),f'{d/1000:.1f}km') for d,a,e in sorted(ds,key=lambda x:-x[0])[:8]])
print('   복수 연결 QID의 종류:',lb(multi_p31.most_common(12)))
print('   복수 연결 상위:',[(W.get(q,{}).get('label',{}).get('ja',q),len(v)) for q,v in top])
print('\n[참고] 연결된 Wikidata 종류(P31) 상위 40:',lb(p31.most_common(40)))
# 3) 인기도: log1p(위키백과 언어판 수) → 0~1 min-max
E=[e for e in W.values() if not e.get('missing')]
raw=[e['wiki_count'] for e in E]; lg=[math.log1p(x) for x in raw]; mx=max(lg)
for e,v in zip(E,lg): e['popularity']=round(v/mx,4)
json.dump({e['qid']:e['popularity'] for e in E},open(f'{R}/interim/wikidata_popularity.json','w'))
print(f'\n[3] 인기도 (log1p(언어판 수)/max, max 언어판 수={max(raw)})')
h=collections.Counter(min(x,20) for x in raw); print('   언어판 수 분포(20+=20):',sorted(h.items()))
qs=sorted(e['popularity'] for e in E); n=len(qs)
print('   인기도 분위수:',{p:qs[int(n*p/100)-1 if p else 0] for p in (0,25,50,75,90,99,100)})
print('   상위 15:',[(e['label'].get('ko') or e['label'].get('ja'),e['wiki_count'],e['popularity']) for e in sorted(E,key=lambda e:-e['wiki_count'])[:15]])
print(f'\n한국어 라벨 {sum("ko" in e["label"] for e in E)} / {len(E)} | 한국어 위키 {sum("kowiki" in e["wiki_titles"] for e in E)} | 문화재 지정 {sum("heritage" in e for e in E)} | 이미지 {sum("image" in e for e in E)} | 트립어드바이저 ID {sum("tripadvisor_id" in e for e in E)} | Wikivoyage {sum(bool(e["wikivoyage"]) for e in E)}')
# 4) 유효 연결만으로 인기도 재계산: Wikidata에 좌표가 있고 OSM과 1km 이내 (인물·개념·사건·다른 곳 항목 제거)
valid={}
for d,a,e in ds:
    if d<1000: valid[e['qid']]=e
nocoord=len({q for _,q in links if q in W and not W[q].get('missing') and 'coord' not in W[q]})
print(f'\n[4] 유효 연결 QID {len(valid)} / {len(E)} (좌표 없음 {nocoord}, 1km+ {sum(1 for d,_,_ in ds if d>=1000)})')
V=list(valid.values()); raw=[e['wiki_count'] for e in V]; lg=[math.log1p(x) for x in raw]; mx=max(lg)
for e,v in zip(V,lg): e['popularity']=round(v/mx,4)
json.dump({e['qid']:{'wiki_count':e['wiki_count'],'popularity':e['popularity']} for e in V},open(f'{R}/interim/wikidata_popularity.json','w'))
qs=sorted(e['popularity'] for e in V); n=len(qs)
print(f'   max 언어판 수={max(raw)} | 인기도 분위수:',{p:qs[max(int(n*p/100)-1,0)] for p in (0,25,50,75,90,99,100)})
print('   상위 20:',[(e['label'].get('ko') or e['label'].get('ja'),e['wiki_count'],e['popularity']) for e in sorted(V,key=lambda e:-e['wiki_count'])[:20]])
fk=lambda e:33.50<=e['coord']['lat']<=33.68 and 130.28<=e['coord']['lon']<=130.50
print('   후쿠오카 중심부 상위 15:',[(e['label'].get('ko') or e['label'].get('ja'),e['wiki_count'],e['popularity']) for e in sorted([e for e in V if fk(e)],key=lambda e:-e['wiki_count'])[:15]])
