# 최근 12개월 vs 직전 12개월 조회수 변화 (언어 전체 추세 보정) → 뜬 곳 / 식은 곳
# 사용: LANG=ko|en|ja MIN=직전·최근 합계 최소 조회수(기본 1200)  python3 trend.py [lat_min lat_max lon_min lon_max]
import json,os,sys,math,numpy as np
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','..','data')
LANG=os.environ.get('LANG_','en') if 'LANG_' in os.environ else os.environ.get('WIKI','en'); MIN=int(os.environ.get('MIN','1200'))
BOX=list(map(float,sys.argv[1:5])) if len(sys.argv)>=5 else None
P=json.load(open(f'{R}/interim/wikidata_popularity.json'))
E={}
for l in open(f'{R}/raw/wikidata/entities.jsonl'):
    e=json.loads(l)
    if e.get('qid') in P: E.setdefault(e['qid'],e)
PREV=[f'{y}{m:02d}' for y,m in [(2024,9),(2024,10),(2024,11),(2024,12)]+[(2025,m) for m in range(1,9)]]
LAST=[f'{y}{m:02d}' for y,m in [(2025,9),(2025,10),(2025,11),(2025,12)]+[(2026,m) for m in range(1,9)]]
rows=[]
for x in map(json.loads,open(f'{R}/raw/wikidata/pageviews_{LANG}_36m.jsonl')):
    m=x.get('monthly') or {}; q=x['qid']
    if q not in E or not all(k in m for k in PREV+LAST): continue
    a=sum(m[k] for k in PREV); b=sum(m[k] for k in LAST)
    if a+b<MIN: continue
    peak=max(m[k] for k in LAST)/max(b,1)  # 최근 12개월 중 한 달 비중 → 일회성 급증 판별
    rows.append(dict(q=q,name=E[q]['label'].get('ko') or E[q]['label'].get('en') or E[q]['label'].get('ja'),a=a,b=b,g=math.log2((b+50)/(a+50)),peak=peak,coord=E[q].get('coord')))
base=float(np.median([r['g'] for r in rows]))
for r in rows: r['rel']=r['g']-base
sel=[r for r in rows if not BOX or (r['coord'] and BOX[0]<=r['coord']['lat']<=BOX[1] and BOX[2]<=r['coord']['lon']<=BOX[3])]
print(f"[{LANG}] 비교 가능 {len(rows)}곳 | 언어 전체 증감 중간값 {2**base-1:+.0%} (이만큼은 보정) | 대상 {len(sel)}곳"+(f' 범위 {BOX}' if BOX else ' 전국'))
fmt=lambda r:f"  {r['name'][:22]:<24}{int(r['a']):>8,} → {int(r['b']):>8,}   보정 후 {2**r['rel']-1:+6.0%}  {'(한 달 급증 '+format(r['peak'],'.0%')+')' if r['peak']>=0.3 else ''}"
N=int(os.environ.get('TOP','15'))
print('\n▲ 뜬 곳'); [print(fmt(r)) for r in sorted(sel,key=lambda r:-r['rel'])[:N]]
print('\n▼ 식은 곳'); [print(fmt(r)) for r in sorted(sel,key=lambda r:r['rel'])[:N]]
