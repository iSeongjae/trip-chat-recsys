# 언어별 위키백과 월간 조회수(36개월) → OSM 세부 종류별 계절 곡선 → 곡선 모양이 비슷한 종류끼리 군집
# 사용: LANGS=ko | en | ko+en | ja   K=군집 수(기본 4)   MIN=곡선에 필요한 최소 문서 수(기본 25)
#       NORM=1 (여러 언어일 때) 언어별로 월별 비중을 먼저 구해 같은 비중으로 평균 — 조회수 큰 언어가 좌우하지 않게
#       MIN_VIEWS=곡선에 넣을 문서의 연평균 최소 조회수(기본 600)
import json,os,math,collections,numpy as np
from scipy.cluster.hierarchy import linkage,fcluster
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
LANGS=os.environ.get('LANGS','ko').split('+'); NORM=os.environ.get('NORM')=='1' and len(LANGS)>1
TAG='+'.join(LANGS)+('_norm' if NORM else '')
K=int(os.environ.get('K','4')); MIN=int(os.environ.get('MIN','25')); MIN_VIEWS=int(os.environ.get('MIN_VIEWS','600'))
MON=['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월']
DAYS=np.array([31,28.25,31,30,31,30,31,31,30,31,30,31])  # 2월은 윤년 평균

# ── 언어별 조회수를 장소(QID) 단위로 합침: {qid: {YYYYMM: views}} ──
VL={lang:{} for lang in LANGS}  # 언어별 {qid: {YYYYMM: views}}
for lang in LANGS:
    for l in open(f'{R}/raw/wikidata/pageviews_{lang}_36m.jsonl'):
        x=json.loads(l)
        if x.get('monthly'): VL[lang][x['qid']]=x['monthly']
V=collections.defaultdict(lambda:collections.Counter())  # 언어 합산 (수준 계산과 NORM=0 곡선용)
for lang in LANGS:
    for q,m in VL[lang].items(): V[q].update(m)

def month_of_year(m):
    """월별 조회수 → 달마다 (일평균의) 여러 해 중간값, 합이 1이 되게 정규화. 한 해만 튄 달은 중간값에서 걸러짐."""
    by=collections.defaultdict(list)
    for ym,v in m.items(): by[int(ym[4:6])-1].append(v)
    if len(by)<12: return None
    x=np.array([np.median(by[i]) for i in range(12)])/DAYS
    return x/x.sum() if x.sum()>0 else None

def annual(m):  # 연평균 조회수 (여러 해 중간값 기준)
    by=collections.defaultdict(list)
    for ym,v in m.items(): by[int(ym[4:6])-1].append(v)
    return float(sum(np.median(v) for v in by.values())*12/max(len(by),1))

# ── OSM 세부 종류 ──
A=json.load(open(f'{R}/interim/osm_attractions_jp.json'))
KO={'tourism=museum':'박물관','tourism=gallery':'미술관·갤러리','tourism=attraction':'명소','tourism=viewpoint':'전망대','tourism=zoo':'동물원','tourism=aquarium':'수족관',
'tourism=theme_park':'테마파크','tourism=artwork':'조형물','historic=castle':'성','historic=memorial':'기념비','historic=wayside_shrine':'길가 사당','historic=monument':'기념물',
'historic=archaeological_site':'유적지','historic=tomb':'고분·묘','historic=ruins':'폐허·터','historic=building':'역사 건축물','historic=yes':'역사(기타)','historic=heritage':'문화재',
'leisure=park':'공원','leisure=garden':'정원','leisure=nature_reserve':'자연보호구역','natural=peak':'산','natural=beach':'해변','natural=hot_spring':'온천(자연)',
'waterway=waterfall':'폭포','amenity=public_bath':'공중목욕탕·온천','leisure=sauna':'사우나','shop=mall':'쇼핑몰','shop=department_store':'백화점','shop=gift':'기념품점'}
def sub(a):
    if a.get('amenity')=='place_of_worship':
        return {'shinto':'신사','buddhist':'사찰','christian':'교회'}.get(a.get('religion'),'기타 종교시설')
    for k in ('tourism','historic','leisure','natural','waterway','shop','amenity'):
        if k in a: s=f'{k}={a[k]}'; return KO.get(s,s)

seen=set(); prof=collections.defaultdict(list); lvl=collections.defaultdict(list); cnt_all=collections.Counter()
for a in A:
    c=sub(a); cnt_all[c]+=1
    for q in [x.strip() for x in a.get('wikidata','').split(';') if x.strip()]:
        if q in V and q not in seen:
            seen.add(q); m=V[q]; t=annual(m); lvl[c].append(t)
            if NORM:  # 언어마다 기준을 넘는 곡선만 골라 같은 비중으로 평균
                ps=[month_of_year(VL[lg][q]) for lg in LANGS if q in VL[lg] and annual(VL[lg][q])>=MIN_VIEWS]
                ps=[x for x in ps if x is not None]
                if ps: prof[c].append(np.mean(ps,axis=0))
            else:
                p=month_of_year(m)
                if p is not None and t>=MIN_VIEWS: prof[c].append(p)
cats=[c for c in prof if len(prof[c])>=MIN]

# ── 공통 곡선(전 문서 중간값)으로 나눠 카테고리 고유의 계절성만 남김 ──
allp=np.array([p for c in prof for p in prof[c]]); BASE=np.median(allp,axis=0); BASE=BASE/BASE.sum()
def rel(ps): m=np.median(np.array(ps),axis=0); m=m/m.sum(); return m/BASE
P=np.array([rel(prof[c]) for c in cats]) if cats else np.zeros((0,12))
if len(cats)>=2:
    Z=(P-P.mean(axis=1,keepdims=True))/P.std(axis=1,keepdims=True)
    lab=fcluster(linkage(Z,method='average',metric='correlation'),t=min(K,len(cats)),criterion='maxclust')
else: lab=np.ones(len(cats),dtype=int)

if __name__=='__main__':
    bars='▁▂▃▄▅▆▇█'
    spark=lambda p:''.join(bars[min(int((x-p.min())/(p.max()-p.min()+1e-12)*7.999),7)] for x in p)
    print(f'[{TAG}] 조회수 있는 장소 {len(V)} | 곡선 문서 {sum(len(v) for v in prof.values())} | 군집 대상 카테고리 {len(cats)} (문서 {MIN}개 이상)')
    print('월 순서: 1~12월 | 공통 곡선:',spark(BASE),'\n')
    groups=collections.defaultdict(list)
    for c,g,p in zip(cats,lab,P): groups[g].append((c,p))
    for g,items in sorted(groups.items(),key=lambda x:-np.median([v for c,_ in x[1] for v in lvl[c]])):
        gp=np.mean([p for _,p in items],axis=0)
        print(f'[군집 {g}] {spark(gp)} 최고 {MON[int(np.argmax(gp))]} x{gp.max():.2f}')
        for c,p in sorted(items,key=lambda x:-(x[1].max()-x[1].min())):
            print(f'     {c:<14} {spark(p)} 최고 {MON[int(np.argmax(p))]:>3} x{p.max():.2f} | 곡선 문서 {len(prof[c]):>4} | 연 조회 중간 {int(np.median(lvl[c])):>6}')
    print('\n문서 부족으로 제외:',{c:len(prof[c]) for c in sorted(lvl,key=lambda c:-len(lvl[c])) if c not in cats and len(lvl[c])>=5})
