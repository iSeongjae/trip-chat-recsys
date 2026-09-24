# 언어별 전체 조회수 중 각 장소의 점유율(연도별) → 점유율 변화로 뜨고 지는 곳 판단. 전 장소 CSV 저장.
# 사용: WIKI=ko|en|ja  MIN=3년 합계 최소 조회수(기본 600)  python3 share_trend.py
import json,os,csv,math,numpy as np
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
LANG=os.environ.get('WIKI','en'); MIN=int(os.environ.get('MIN','600'))
P=json.load(open(f'{R}/interim/wikidata_popularity.json'))
E={}
for l in open(f'{R}/raw/wikidata/entities.jsonl'):
    e=json.loads(l)
    if e.get('qid') in P: E.setdefault(e['qid'],e)
def ym(y,m): return f'{y}{m:02d}'
YEARS=[[ym(y+(m<9),m) for m in (9,10,11,12,1,2,3,4,5,6,7,8)] for y in (2023,2024,2025)]  # 9월 시작 12개월
ALL=[k for Y in YEARS for k in Y]
X={}
for x in map(json.loads,open(f'{R}/raw/wikidata/pageviews_{LANG}_36m.jsonl')):
    m=x.get('monthly') or {}
    if x['qid'] in E and all(k in m for k in ALL): X[x['qid']]=m
tot=[sum(sum(m[k] for k in Y) for m in X.values()) for Y in YEARS]
rows=[]
for q,m in X.items():
    v=[sum(m[k] for k in Y) for Y in YEARS]
    if sum(v)<MIN: continue
    s=[v[i]/tot[i] for i in range(3)]
    pk=[max(m[k] for k in Y)/max(sum(m[k] for k in Y),1) for Y in YEARS]  # 연도별 한 달 최대 비중
    ch=lambda a,b:(b+1e-7)/(a+1e-7)
    r1,r2=ch(s[0],s[1]),ch(s[1],s[2])
    kind=('화제성 급증' if max(pk)>=0.3 else
          '꾸준히 상승' if r1>1.15 and r2>1.15 else '꾸준히 하락' if r1<1/1.15 and r2<1/1.15 else
          '최근 상승' if r2>1.3 else '최근 하락' if r2<1/1.3 else '유지')
    e=E[q]; rows.append(dict(qid=q,name_ko=e['label'].get('ko',''),name_ja=e['label'].get('ja',''),name_en=e['label'].get('en',''),
        views_y1=v[0],views_y2=v[1],views_y3=v[2],share_y1=s[0],share_y2=s[1],share_y3=s[2],ratio_y2y1=r1,ratio_y3y2=r2,
        max_month_share=max(pk),kind=kind,lat=e.get('coord',{}).get('lat'),lon=e.get('coord',{}).get('lon')))
out=f'{R}/interim/share_trend_{LANG}.csv'
with open(out,'w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(sorted(rows,key=lambda r:-r['ratio_y3y2']))
import collections
print(f'[{LANG}] 3년 모두 있는 문서 {len(X)} | 대상(3년 합 {MIN}+) {len(rows)} | 연도별 전체 조회수 {[f"{t:,}" for t in tot]} ({tot[2]/tot[0]-1:+.0%})')
print('분류:',dict(collections.Counter(r['kind'] for r in rows).most_common()))
r2=np.array([r['ratio_y3y2'] for r in rows]); print('최근 1년 점유율 배율 분위수:',{p:round(float(np.percentile(r2,p)),2) for p in (5,25,50,75,95)})
nm=lambda r:(r['name_ko'] or r['name_en'] or r['name_ja'])[:20]
f=lambda r:f"  {nm(r):<22} 점유율 {r['share_y1']*1e4:6.2f} → {r['share_y2']*1e4:6.2f} → {r['share_y3']*1e4:6.2f} (‱)  최근 ×{r['ratio_y3y2']:.2f}"
N=int(os.environ.get('TOP','10'))
for k in ('꾸준히 상승','최근 상승','꾸준히 하락','최근 하락'):
    xs=[r for r in rows if r['kind']==k]; xs.sort(key=lambda r:-r['ratio_y3y2'] if '상승' in k else r['ratio_y3y2'])
    print(f'\n[{k}] {len(xs)}곳'); [print(f(r)) for r in xs[:N]]
print('\n저장:',out)
