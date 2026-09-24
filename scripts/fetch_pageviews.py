# 유효 Wikidata 연결의 위키백과 문서 → 최근 36개월 월별 조회수(사람, 전체 기기) 수집 (이어받기 지원)
# 사용: python3 fetch_pageviews.py [ja|ko|en] [36m|12m]  (기본 ja 36m)
#   12m: 최근 12개월 → pageviews_<lang>.jsonl (views_12m). 아이템 인기도(build_items)가 쓰는 ja 12개월 파일
#   36m: 최근 36개월 → pageviews_<lang>_36m.jsonl (views_36m). 계절성·언어 지수용
# Wikimedia 익명 한도 분당 200회 → 전역 초당 3회 이하로 제한
import json,os,sys,time,urllib.request,urllib.parse,urllib.error,threading
from concurrent.futures import ThreadPoolExecutor
R=os.path.join(os.path.dirname(os.path.abspath(__file__)),'..','data')
UA=f"japan-traveler-research/0.1 ({os.environ['CONTACT']})"
# 계절성은 여러 해의 월별 중간값으로 봐야 일회성 급증과 구분됨 → 36개월
LANG=sys.argv[1] if len(sys.argv)>1 else 'ja'
SPAN=sys.argv[2] if len(sys.argv)>2 else '36m'
OUT=f'{R}/raw/wikidata/pageviews_{LANG}_36m.jsonl' if SPAN=='36m' else f'{R}/raw/wikidata/pageviews_{LANG}.jsonl'
START,END=('2023090100','2026083100') if SPAN=='36m' else ('2025090100','2026083100')
P=json.load(open(f'{R}/interim/wikidata_popularity.json'))
T={}
for l in open(f'{R}/raw/wikidata/entities.jsonl'):
    e=json.loads(l)
    if e.get('qid') in P and f'{LANG}wiki' in e.get('wiki_titles',{}): T[e['qid']]=e['wiki_titles'][f'{LANG}wiki']
done=set()
if os.path.exists(OUT): done={r['qid'] for r in map(json.loads,open(OUT)) if 'monthly' in r}  # 합계만 있는 옛 기록은 다시 받음
todo=[(q,t) for q,t in T.items() if q not in done]
print(LANG,'| 유효 QID',len(P),f'| {LANG}wiki 문서',len(T),'| 남음',len(todo),flush=True)
lock=threading.Lock(); f=open(OUT,'a'); n=[0]
rl=threading.Lock(); last=[0.0]
def throttle():
    with rl:
        w=last[0]+1/3-time.time()
        if w>0: time.sleep(w)
        last[0]=time.time()
def get(item):
    q,t=item
    url=f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{LANG}.wikipedia/all-access/user/{urllib.parse.quote(t.replace(' ','_'),safe='')}/monthly/{START}/{END}"
    for k in range(5):
        throttle()
        try:
            d=json.load(urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':UA}),timeout=30))
            m={x['timestamp'][:6]:x['views'] for x in d.get('items',[])}; v=sum(m.values()); break
        except urllib.error.HTTPError as e:
            if e.code==404: m={}; v=0; break  # 기간 내 조회 기록 없음
            time.sleep(int(e.headers.get('Retry-After') or 5*(k+1)))
        except Exception: time.sleep(5*(k+1))
    else: m=None; v=None
    with lock:
        f.write(json.dumps({'qid':q,'title':t,f'views_{SPAN}':v,'monthly':m},ensure_ascii=False)+'\n'); n[0]+=1
        if n[0]%1000==0: f.flush(); print(n[0],'/',len(todo),flush=True)
with ThreadPoolExecutor(5) as ex: list(ex.map(get,todo))
f.close(); print('완료',flush=True)
