# 월별 점유율 → 로컬 / 한국 인지도 / 숨은 명소 지수 (월별). 문서 없는 언어는 계산 안 함(NaN).
# 두 언어를 비교할 땐 두 언어 문서가 모두 있는 장소 집합 안에서 점유율을 다시 계산(언어별 문서 수·유명도 차이 편향 제거)
# 사용: python3 lang_indices_monthly.py [lat_min lat_max lon_min lon_max]   (기본: 후쿠오카시+다자이후 일대, 전국 CSV는 항상 저장)
import json,os,sys,csv,math,collections,numpy as np
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
BOX=list(map(float,sys.argv[1:5])) if len(sys.argv)>=5 else [33.45,33.72,130.25,130.60]
A=5  # 월 조회수 보정값 (적은 조회수 흔들림 완화)
MONTHS=[f'2025{m:02d}' for m in (9,10,11,12)]+[f'2026{m:02d}' for m in range(1,9)]
P=json.load(open(f'{R}/interim/wikidata_popularity.json'))
def load(f):
    d={}
    for x in map(json.loads,open(f'{R}/raw/wikidata/{f}')):
        m=x.get('monthly') or {}
        if x['qid'] in P and all(k in m for k in MONTHS): d[x['qid']]=m
    return d
V={'ja':load('pageviews_ja.jsonl'),'ko':load('pageviews_ko_36m.jsonl'),'en':load('pageviews_en_36m.jsonl')}
def shares(lang,qs):  # 주어진 장소 집합 안에서의 월별 점유율 × 집합 크기 (평균 장소 = 1)
    M=np.array([[V[lang][x][k] for k in MONTHS] for x in qs],float)+A
    return dict(zip(qs,M/M.sum(axis=0,keepdims=True)*len(qs)))
def pair(l1,l2):
    qs=sorted(set(V[l1])&set(V[l2])); return shares(l1,qs),shares(l2,qs)
ja_en,en_ja=pair('ja','en'); ja_ko,ko_ja=pair('ja','ko'); en_ko,ko_en=pair('en','ko')
ko_all=shares('ko',sorted(V['ko']))
E={}
for l in open(f'{R}/raw/wikidata/entities.jsonl'):
    e=json.loads(l)
    if e.get('qid') in P: E.setdefault(e['qid'],e)
NaN=np.full(12,np.nan); res={}
for q in sorted(set().union(*[set(d) for d in V.values()])):   # 순서 고정 (set 순서는 실행마다 달라짐)
    lo=[np.log2(a[q]/b[q]) for a,b in ((ja_en,en_ja),(ja_ko,ko_ja)) if q in a]
    res[q]=dict(local=np.min(lo,axis=0) if lo else NaN,  # 외국인 관심이 더 큰 쪽 기준
                known=np.log2(ko_all[q]) if q in ko_all else NaN,  # 한국어 문서 평균 대비
                hidden=np.log2(en_ko[q]/ko_en[q]) if q in en_ko else NaN)
out=f'{R}/interim/lang_indices_monthly.csv'
with open(out,'w',newline='') as f:
    w=csv.writer(f); w.writerow(['qid','name_ko','name_ja','month','local','known','hidden','lat','lon'])
    for q,r in res.items():
        e=E[q]; c=e.get('coord',{})
        for i,k in enumerate(MONTHS):
            w.writerow([q,e['label'].get('ko',''),e['label'].get('ja',''),k]+[None if np.isnan(r[x][i]) else round(float(r[x][i]),3) for x in ('local','known','hidden')]+[c.get('lat'),c.get('lon')])
cnt={x:sum(1 for r in res.values() if not np.isnan(r[x]).all()) for x in ('local','known','hidden')}
print(f'전국 장소 {len(res)} | 지수 계산 가능: 로컬 {cnt["local"]}, 한국 인지도 {cnt["known"]}, 숨은 명소 {cnt["hidden"]} | 저장 {out}')
# ── 범위 내 요약 ──
MON=['9','10','11','12','1','2','3','4','5','6','7','8']
bars='▁▂▃▄▅▆▇█'
spark=lambda p:''.join(bars[min(int((x-p.min())/(p.max()-p.min()+1e-12)*7.999),7)] for x in p)
inb=[q for q in res if 'coord' in E[q] and BOX[0]<=E[q]['coord']['lat']<=BOX[1] and BOX[2]<=E[q]['coord']['lon']<=BOX[3]]
nm=lambda q:(E[q]['label'].get('ko') or E[q]['label'].get('ja'))[:16]
LAB={'local':'로컬 (+면 외국인 대비 일본인 관심↑, 0=평균)','known':'한국 인지도 (+면 한국어 문서 평균보다↑)','hidden':'숨은 명소 (+면 한국어 대비 영어권 관심↑, 0=평균)'}
for x in ('local','known','hidden'):
    qs=[q for q in inb if not np.isnan(res[q][x]).all()]
    print(f'\n■ {LAB[x]} — 범위 내 {len(qs)}곳 (월 순서 9→8월)')
    for q in sorted(qs,key=lambda q:-np.nanmean(res[q][x])):
        a=res[q][x]; k=int(np.nanargmax(a)); j=int(np.nanargmin(a))
        print(f'  {nm(q):<18} 평균 {np.nanmean(a):+5.2f}  {spark(a)}  최고 {MON[k]:>2}월 {a[k]:+.2f} / 최저 {MON[j]:>2}월 {a[j]:+.2f}')
