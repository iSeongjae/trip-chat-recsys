"""간단 부하 테스트 (httpx asyncio). 가상 사용자: 게스트 로그인 → 역으로 위치 설정 → [칩 추천 → 장소 상세 → 저장 → 대화] 반복.
사용: python3 tools/loadtest.py http://localhost:8766 <동시 사용자> <초>
LLM 비용이 들지 않게 서버는 OPENAI_API_KEY 없이(규칙 파서) 띄워서 서버 자체 처리량만 잰다."""
import asyncio, random, sys, time, statistics
import httpx

BASE, USERS, SECS = sys.argv[1], int(sys.argv[2]), float(sys.argv[3])
STATIONS = ['교토역', '하카타역', '도쿄역', '신주쿠역', '난바역', '삿포로역', '나고야역', '나하']
CHIPS = [{'category': 'meal'}, {'category': 'cafe'}, {'category': 'sight'}, {'theme': 'famous'}, {'theme': 'season'}, {'category': 'bar'}]
MSGS = ['라멘 먹고 싶어', '카페 가고 싶어', '근처 공원 산책', '이자카야 추천해줘']
lat = {}; err = {}


def rec(name, t0, r=None, e=None):
    lat.setdefault(name, []).append(time.perf_counter() - t0)
    if e or (r is not None and r.status_code >= 400): err[name] = err.get(name, 0) + 1


async def call(c, name, method, url, **kw):
    t0 = time.perf_counter()
    try:
        r = await c.request(method, url, **kw); rec(name, t0, r); return r
    except Exception as e:
        rec(name, t0, e=e); return None


async def user(i, stop):
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
        await call(c, 'guest', 'POST', '/api/auth/guest')
        await call(c, 'location', 'POST', '/api/location', params={'query': random.choice(STATIONS)}, json={})
        while time.time() < stop:
            r = await call(c, 'recommend', 'POST', '/api/recommend', json=random.choice(CHIPS))
            cards = (r.json().get('cards') if r is not None and r.status_code == 200 else None) or []
            if cards:
                iid = random.choice(cards)['id']
                await call(c, 'place', 'GET', f'/api/places/{iid}')
                await call(c, 'save', 'POST', f'/api/places/{iid}/feedback', json={'event': 'save'})
            await call(c, 'chat', 'POST', '/api/chat', json={'message': random.choice(MSGS)})
            await call(c, 'lists', 'GET', '/api/me/lists')
            await asyncio.sleep(random.uniform(0.2, 0.8))   # 사람처럼 약간 쉼


async def main():
    stop = time.time() + SECS
    t = time.time()
    await asyncio.gather(*(user(i, stop) for i in range(USERS)))
    dt = time.time() - t
    n = sum(len(v) for v in lat.values())
    print(f'동시 {USERS}명 {dt:.0f}초: 요청 {n} ({n / dt:.1f}/s), 오류 {sum(err.values())}')
    for k, v in lat.items():
        v = sorted(v); p = lambda q: v[min(len(v) - 1, int(q * len(v)))] * 1000
        print(f'  {k:9} n={len(v):5}  p50 {p(.5):6.0f}ms  p95 {p(.95):6.0f}ms  p99 {p(.99):6.0f}ms  오류 {err.get(k, 0)}')

asyncio.run(main())
