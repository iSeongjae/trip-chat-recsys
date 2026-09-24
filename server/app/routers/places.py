"""장소 상세·반응(가기/저장/여기 말고)·화면 이벤트. 반응 한 번마다 reaction_logs 한 줄 (직전 추천 turn_id·순위와 연결)."""
import urllib.parse
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from .. import db, service as sv
from ..auth import current_user

router = APIRouter(prefix='/api')
UI_EVENTS = {'map_open', 'pin_click', 'directions_open', 'share', 'wiki_open'}   # 프론트가 보내는 반응


def _item(item_id):
    it = sv.items().get(item_id)
    if not it: raise HTTPException(404, '없는 장소')
    return it


def _rank(p, item_id):
    shown = p['session'].get('last_shown') or []
    return shown.index(item_id) + 1 if item_id in shown else None


@router.get('/places/search')
def search(q: str, uid: str = Depends(current_user)):
    k = sv.norm(q)
    if len(k) < 2: return []
    cur = db.load_profile(uid, sv.pf.new_profile)['session']['current']
    hits = [it for key, it in sv.name_index() if k in key]
    hits.sort(key=lambda it: sv.haversine_km(cur['lat'], cur['lon'], it['lat'], it['lon']) if cur else -it.get('popularity', 0))
    return [sv.card(it, cur) for it in hits[:20]]


@router.get('/places/{item_id}')
def detail(item_id: str, lat: float = None, lon: float = None, uid: str = Depends(current_user)):
    """lat/lon: 브라우저의 현재 위치(저장하지 않음, 거리 계산에만). 없으면 저장된 위치."""
    it = _item(item_id)
    p = db.load_profile(uid, sv.pf.new_profile)
    out = sv.card(it, {'lat': lat, 'lon': lon} if lat is not None and lon is not None else p['session']['current'])
    desc, wiki = it.get('desc') or {}, it.get('wiki') or {}
    w = next(((l, wiki[f'{l}wiki']) for l in ('ko', 'ja', 'en') if f'{l}wiki' in wiki), None)
    out.update(
        description=next((desc[l] for l in ('ko', 'ja', 'en') if l in desc), None),
        description_source='Wikidata (CC0)' if desc else None,
        wiki_url=f'https://{w[0]}.wikipedia.org/wiki/{urllib.parse.quote(w[1])}' if w else None,
        image=f"https://commons.wikimedia.org/wiki/Special:FilePath/{urllib.parse.quote(it['image'])}?width=640" if it.get('image') else None,
        directions=f"https://www.google.com/maps/dir/?api=1&destination={it['lat']},{it['lon']}&travelmode=walking",
        saved=db.one('select 1 as x from saved where user_id = %s and place_id = %s', uid, item_id) is not None,
        visited=item_id in p['session']['visited'],
        sources=['OpenStreetMap (ODbL)'] + (['Foursquare OS Places (Apache 2.0)'] if 'foursquare' in it.get('sources', []) else [])
                + (['Wikidata (CC0)'] if it.get('wikidata') else []))
    db.log_reaction(uid, p['_trip'], 'card_open', place_id=item_id, turn_id=p['session'].get('last_turn'), rank=_rank(p, item_id))
    return out


class FeedbackIn(BaseModel):
    event: str   # select | save | unsave | skip


@router.post('/places/{item_id}/feedback')
def feedback(item_id: str, body: FeedbackIn, uid: str = Depends(current_user)):
    it = _item(item_id)
    p = db.load_profile(uid, sv.pf.new_profile)
    trip, turn, rank = p['_trip'], p['session'].get('last_turn'), _rank(p, item_id)
    if body.event not in ('select', 'save', 'unsave', 'skip'):
        raise HTTPException(400, 'event: select|save|unsave|skip')
    if body.event in ('select', 'save', 'skip'):
        v = sv.view(p)
        sv.rec.log_feedback(v, item_id, body.event, position=rank - 1 if rank else None)
        p['n_reactions'] = v['n_reactions']
        p['session']['current'], p['session']['visited'] = v['context']['current'], v['context']['visited']
    if body.event == 'select':
        p['session']['current'] = dict(p['session']['current'], src='place', place_id=item_id)
        sv.pf.on_select(p, it)
        db.run('insert into visits(user_id, trip_id, place_id, source, turn_id) values (%s, %s, %s, %s, %s)',
               uid, trip, item_id, 'recommendation' if rank else 'manual', turn)
    elif body.event == 'save':
        db.run('insert into saved(user_id, place_id, turn_id) values (%s, %s, %s) on conflict do nothing', uid, item_id, turn)
    elif body.event == 'unsave':
        db.run('delete from saved where user_id = %s and place_id = %s', uid, item_id)
    elif body.event == 'skip':
        p['session']['last_shown'] = [x for x in p['session'].get('last_shown') or [] if x != item_id]
    db.log_reaction(uid, trip, body.event, place_id=item_id, turn_id=turn, rank=rank)
    db.save_profile(sv.stored(p), geo=sv.current_geo(p))
    return {'ok': True, 'current': sv.public_current(p)}


class LogIn(BaseModel):
    type: str
    place_id: Optional[str] = None
    props: Optional[dict] = None


@router.post('/log')
def ui_log(body: LogIn, uid: str = Depends(current_user)):
    """화면에서 생기는 반응(지도 열기·핀·길찾기·공유·위키) → reaction_logs."""
    if body.type not in UI_EVENTS:
        raise HTTPException(400, f'type: {sorted(UI_EVENTS)}')
    p = db.load_profile(uid, sv.pf.new_profile)
    db.log_reaction(uid, p['_trip'], body.type, place_id=body.place_id, turn_id=p['session'].get('last_turn'),
                    rank=_rank(p, body.place_id) if body.place_id else None, props=body.props)
    return {'ok': True}
