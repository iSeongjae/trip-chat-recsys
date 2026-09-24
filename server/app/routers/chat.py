"""여행챗: 대화·칩 추천·위치·여행 종료. 대화(추천) 한 번마다 turn_logs 한 줄."""
import json, time, datetime, re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from .. import db, llm, service as sv, config
from ..auth import current_user

router = APIRouter(prefix='/api')
THEME_WORDS = re.compile(r'명소|유명|현지인|로컬|한국인|숨은|외국인|이번 ?달|요즘|계절|제철|\d+월')
STOP = {'말고', '밥', '식사', '음식', '먹을 거', '먹을것', '산책', '구경', '쇼핑', '휴식', '술', '맛집', '근처', '가게', '장소', '곳'}  # 종류가 아닌 말
OUTSIDE = '지금 위치가 일본이 아니라서 GPS 는 쓰지 않았어요. 위 위치 칩에서 역 이름(예: 교토역)을 알려주세요.'


class Loc(BaseModel):
    lat: Optional[float] = None
    lon: Optional[float] = None
    name: Optional[str] = None     # 목록·검색에서 고른 곳이면 이름 (GPS 가 아님)
    kind: Optional[str] = None     # 공항 | 역 | 장소 (시작 위치 방식 기록용)


class ChatIn(Loc):
    message: str


class ChipIn(Loc):
    category: Optional[str] = None   # meal|cafe|bar|sight|walk|shop|rest
    theme: Optional[str] = None      # famous|local|known|hidden|season
    month: Optional[int] = None      # season 일 때 달 (없으면 이번 달)


def _limit(uid):
    n = db.run('insert into usage_daily(user_id, day, chats) values (%s, current_date, 1) '
               'on conflict (user_id, day) do update set chats = usage_daily.chats + 1 returning chats', uid)
    if n > config.DAILY_CHAT_LIMIT:
        raise HTTPException(429, f'오늘은 {config.DAILY_CHAT_LIMIT}번까지 쓸 수 있어요')


def _msg(uid, trip, role, text, payload=None, turn_id=None):
    db.run('insert into messages(user_id, trip_id, role, text, payload, turn_id) values (%s, %s, %s, %s, %s, %s)',
           uid, trip, role, text, payload, turn_id)


def _loc(p, body):
    """브라우저 GPS. 일본 밖(서비스 지역 밖)이면 무시하고 False."""
    if body.lat is None or body.lon is None:
        return True
    if not sv.in_service_area(body.lat, body.lon):
        return False
    sv.set_location(p, body.lat, body.lon)
    return True


def _save(p):
    db.save_profile(sv.stored(p), geo=sv.current_geo(p))


def _answer(uid, p, intent, reply, source, query, t0, llm_meta=None, outside=False, country=None):
    """추천(가능하면) → 응답 dict. 대화 한 번마다 turn_logs 한 줄."""
    trip, s = p['_trip'], p['session']
    r = None
    if not s['current']:
        out = dict(reply=OUTSIDE if outside else (reply or '지금 어디 계세요? 위치를 켜거나 역 이름을 알려주세요.'), need_location=True, cards=[])
    elif not intent.get('next_category') and not intent.get('theme'):
        out = dict(reply=reply or '뭐 하고 싶으세요?', cards=[])
    else:
        r = sv.recommend(p, intent)
        out = dict(reply=reply, summary=sv.summary(s['intent'], r['cards'], r['radius']), cards=r['cards'], radius_km=r['radius'],
                   notes=r['notes'], intent={k: v for k, v in s['intent'].items() if v not in (None, [], False)})
    # 대화 한 번 = turn_logs 한 줄 (추천이 없었던 턴도 남김: candidates 가 빈 목록)
    s['turn'] = s.get('turn', 0) + 1
    turn_id = db.log_turn(uid, trip, turn_no=s['turn'], source=source, query=query, intent=s['intent'] if r else intent,
                          context=dict(area_geo=sv.current_geo(p), location_method=(s['current'] or {}).get('src'), outside_gps=outside, country=country,
                                       **(dict(radius_km_asked=r['radius_asked'], radius_km_used=r['radius'], n_candidates=r['n_candidates'],
                                               trace=r['trace'], notes=r['notes'], personalization_w=r['w']) if r else {})),
                          candidates=r['logged'] if r else [], answer=' / '.join(x for x in (out['reply'], out.get('summary')) if x),
                          llm=llm_meta, versions=sv.versions(), latency_ms=round((time.time() - t0) * 1000))
    s['last_turn'] = out['turn_id'] = turn_id
    out['current'] = sv.public_current(p)
    if outside and s['current']:
        out.setdefault('notes', []).append('GPS 가 일본 밖이라 마지막으로 정한 위치를 썼어요')
    _save(p)
    _msg(uid, trip, 'assistant', out['reply'] or '', {k: v for k, v in out.items() if k != 'reply'}, turn_id)
    return out


@router.post('/chat')
def chat(body: ChatIn, request: Request, uid: str = Depends(current_user)):
    t0 = time.time()
    _limit(uid)
    p = db.load_profile(uid, sv.pf.new_profile)
    trip = p['_trip']
    outside = not _loc(p, body)
    hist = [(m['role'], m['text']) for m in db.rows('select role, text from messages where trip_id = %s order by created_at desc limit 6', trip)][::-1]
    _msg(uid, trip, 'user', body.message)
    t = llm.parse(body.message, hist)
    if t.get('location_query'):
        g = sv.geocode(t['location_query'], near=p['session']['current'])
        if g: sv.set_location(p, g['lat'], g['lon'], g['name'], src='search')
    for v in t.get('visited_mention') or []:
        hit = sv.mark_visited(p, v)
        if hit: db.log_reaction(uid, trip, 'mark_visited', place_id=hit['id'], props={'said': v})
    intent = {k: [x.strip() for x in t[k] if x.strip() and x.strip() not in STOP] for k in ('include_sub', 'exclude_sub', 'include_brand') if t.get(k)}
    intent = {k: v for k, v in intent.items() if v}
    if t['next_category'] != 'none': intent['next_category'] = t['next_category']
    if t.get('max_distance_km'): intent['max_distance_km'] = t['max_distance_km']
    if t.get('local') is not None: intent['local'] = t['local']
    stable = {k: t[f'stable_{k}'] for k in ('local', 'max_distance_km') if t.get(f'stable_{k}') is not None}
    intent, filled = sv.pf.apply_turn(p, {'intent': intent, 'stable': stable})
    if t.get('theme') not in (None, 'none') and THEME_WORDS.search(body.message):  # 파서가 테마를 지어내는 경우가 있어 말에 단서가 있을 때만
        intent['theme'] = t['theme']
        if t['theme'] == 'season':
            intent['month'] = t.get('month') if t.get('month') in range(1, 13) else sv.month()
    return _answer(uid, p, intent, t['reply'], 'chat', body.message, t0, t.get('_meta'), outside, sv.country(request.client.host if request.client else None))


@router.post('/recommend')
def chip(body: ChipIn, request: Request, uid: str = Depends(current_user)):
    """칩(종류·테마)을 눌렀을 때 — LLM 없이 바로 추천."""
    t0 = time.time()
    p = db.load_profile(uid, sv.pf.new_profile)
    outside = not _loc(p, body)
    intent, _ = sv.pf.apply_turn(p, {'intent': {'next_category': body.category} if body.category else {}})
    if not body.category: intent.pop('next_category', None)
    if body.theme: intent['theme'] = body.theme
    if body.theme == 'season':
        intent['month'] = body.month if body.month in range(1, 13) else sv.month()
    label = sv.CAT_KO.get(body.category) or sv.THEME_KO.get(body.theme or '', '').format(m=intent.get('month') or sv.month())
    _msg(uid, p['_trip'], 'user', label)
    return _answer(uid, p, intent, None, 'chip', label, t0, None, outside, sv.country(request.client.host if request.client else None))


@router.post('/location')
def location(body: Loc, query: Optional[str] = None, uid: str = Depends(current_user)):
    p = db.load_profile(uid, sv.pf.new_profile)
    if query:
        g = sv.geocode(query, near=p['session']['current'])
        if not g: raise HTTPException(404, f"'{query}' 을(를) 찾지 못했어요")
        sv.set_location(p, g['lat'], g['lon'], g['name'], src='search')
    elif body.name and body.lat is not None:
        if not sv.in_service_area(body.lat, body.lon): raise HTTPException(400, '일본 안의 장소를 골라주세요')
        sv.set_location(p, body.lat, body.lon, body.name[:60], src='airport' if body.kind == '공항' else 'search')
    elif not _loc(p, body):
        raise HTTPException(400, '지금 위치가 일본이 아니에요. 역 이름으로 찾아주세요')
    cur = p['session']['current']
    db.run('update trips set start_method = coalesce(start_method, %s), start_label = coalesce(start_label, %s) where id = %s',
           {'search': 'search', 'airport': 'airport', 'gps': 'gps'}.get(cur.get('src'), 'place'), cur.get('name') if cur.get('src') != 'gps' else None, p['_trip'])
    _save(p)
    return {'current': sv.public_current(p)}


@router.get('/season-months')
def season_months(uid: str = Depends(current_user)):
    """월별 명소 칩에 보여 줄 달 (일본 날짜 기준)."""
    return {'today': sv.today().isoformat(), 'months': sv.season_months()}


@router.get('/geo/starts')
def starts(uid: str = Depends(current_user)):
    """여행 시작 위치 기본 목록 (주요 공항, rules/start_points.json)."""
    return sv.start_points()


@router.get('/geo/search')
def geo_search(q: str, uid: str = Depends(current_user)):
    """시작 위치 검색: 공항·역·장소 이름. 고르면 POST /api/location {lat, lon, name}."""
    return sv.geo_search(q)


@router.get('/messages')
def messages(uid: str = Depends(current_user)):
    trip = db.current_trip(uid)
    return [dict(role=m['role'], text=m['text'], at=m['created_at'].timestamp(), **(m['payload'] or {}))
            for m in db.rows('select role, text, payload, created_at from messages where trip_id = %s order by created_at', trip)]


@router.post('/trips/end')
def end_trip(uid: str = Depends(current_user)):
    """여행 종료: 방문 목록·세션을 비우고 새 여행 (취향·안정 특성은 유지)."""
    p = db.load_profile(uid, sv.pf.new_profile)
    db.end_trip(uid)
    p['session'] = sv.pf.new_profile(uid)['session']
    p['_trip'] = db.current_trip(uid)
    _save(p)
    return {'ok': True}
