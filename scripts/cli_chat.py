"""로컬 테스트 CLI: 서버를 띄우지 않고 같은 프로세스에서 실제 API(server/app)를 호출해 대화한다.

DB 는 .env 의 Supabase 를 쓰고, 로그는 versions.env='dev' 로 남는다. 끝나면 테스트 사용자와 그 로그를 지운다(--keep 이면 남김).

사용
  python3 scripts/cli_chat.py --start 교토역                         # 대화형
  python3 scripts/cli_chat.py --start 교토역 --script "라멘 먹고 싶어" "/go 1" "/chip cafe" "이번 달 명소"
  python3 scripts/cli_chat.py --rules ...                             # OpenAI 대신 키워드 규칙 파서 (비용 0)

대화형 명령
  /go N      N번째 카드로 가기 (방문 처리, 현재 위치 이동)     /save N   저장      /skip N   여기 말고
  /chip X    칩 추천 (meal cafe bar sight walk shop rest / famous local known hidden season)
  /where Q   위치를 역·장소 이름으로 다시 정하기             /list     저장목록      /quit
"""
import os, sys, argparse, time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'server'))
os.environ.setdefault('APP_ENV', 'dev')
ap = argparse.ArgumentParser()
ap.add_argument('--start', default='교토역', help='시작 위치 (역·공항·장소 이름)')
ap.add_argument('--script', nargs='*', help='대화형 대신 이 입력들을 순서대로')
ap.add_argument('--rules', action='store_true', help='LLM 대신 규칙 파서')
ap.add_argument('--keep', action='store_true', help='테스트 사용자·로그를 지우지 않음')
args = ap.parse_args()

from app import config, db
if args.rules:
    config.OPENAI_API_KEY = None
from fastapi.testclient import TestClient
from app.main import app

CATS = {'meal', 'cafe', 'bar', 'sight', 'walk', 'shop', 'rest'}
last = []


def show(r):
    global last
    if r.get('reply'): print(f"  🤖 {r['reply']}")
    if r.get('summary'): print(f"  📍 {r['summary']}" + (f"  ({'; '.join(n for n in r.get('notes') or [] if '넓혔' in n)})" if r.get('notes') else ''))
    last = r.get('cards') or last
    for i, c in enumerate(r.get('cards') or [], 1):
        ja = f" / {c['name_ja']}" if c.get('name_ja') else ''
        tags = f"  [{', '.join(c['tags'])}]" if c.get('tags') else ''
        print(f"   {i}. {c['name']}{ja} · {c['kind']} · {c['distance_m']}m{tags}")


def step(c, line):
    t = time.time()
    if line.startswith('/go ') or line.startswith('/save ') or line.startswith('/skip '):
        cmd, n = line[1:].split()
        card = last[int(n) - 1]
        ev = {'go': 'select', 'save': 'save', 'skip': 'skip'}[cmd]
        r = c.post(f"/api/places/{card['id']}/feedback", json={'event': ev}).json()
        print(f"  ✔ {card['name']} → {ev}" + (f" (현재 위치: {r['current']['name']})" if ev == 'select' else ''))
    elif line.startswith('/chip '):
        x = line.split()[1]
        show(c.post('/api/recommend', json={'category': x} if x in CATS else {'theme': x}).json())
    elif line.startswith('/where '):
        r = c.post('/api/location', params={'query': line[7:]}, json={})
        print(f"  📍 위치: {r.json().get('current', {}).get('name') if r.is_success else r.json().get('detail')}")
    elif line == '/list':
        L = c.get('/api/me/lists').json()
        print(f"  간 곳 {[v['name'] for v in L['visited']]} | 저장 {[v['name'] for v in L['saved']]}")
    else:
        show(c.post('/api/chat', json={'message': line}).json())
    print(f"  ({time.time() - t:.1f}초)")


with TestClient(app) as c:
    uid = c.post('/api/auth/guest').json()['user_id']
    actor = db.actor(uid)
    r = c.post('/api/location', params={'query': args.start}, json={})
    print(f"게스트 {uid[:8]} | 시작 위치: {r.json()['current']['name'] if r.is_success else '못 찾음 — /where 로 다시'} | 파서: {'규칙' if args.rules or not config.OPENAI_API_KEY else config.OPENAI_MODEL}")
    try:
        lines = args.script if args.script is not None else iter(lambda: input('\n🙋 '), '/quit')
        for line in lines:
            line = line.strip()
            if not line: continue
            if args.script is not None: print(f'\n🙋 {line}')
            step(c, line)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        if not args.keep:
            c.delete('/api/me')                                     # 개인 데이터 삭제 (행동 로그는 익명화)
            for t in ('reaction_logs', 'turn_logs', 'trips'):          # dev 테스트 로그까지 정리
                db.run(f'delete from {t} where actor = %s', actor)
            print('\n(테스트 사용자·로그 삭제)')
