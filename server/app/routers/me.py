"""저장목록: 내가 간 곳(방문·직접 등록) / 가고 싶은 곳(저장), 별점·메모."""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from .. import db, service as sv
from ..auth import current_user

router = APIRouter(prefix='/api/me')


@router.get('/lists')
def lists(uid: str = Depends(current_user)):
    visited = []
    for v in db.rows('select v.*, t.started_at, s.name as spot_name, s.lat as spot_lat, s.lon as spot_lon from visits v '
                     'left join trips t on t.id = v.trip_id left join spots s on s.id = v.spot_id '
                     'where v.user_id = %s order by v.visited_at desc', uid):
        if v['place_id']:
            it = sv.items().get(v['place_id'])
            if not it: continue
            base = dict(id=it['id'], name=it['name'], kind=sv.kind(it), tags=sv.tags(it), lat=it['lat'], lon=it['lon'], footprint=False)
        else:
            base = dict(id=None, name=v['spot_name'], kind='나만의 스팟', tags=[], lat=v['spot_lat'], lon=v['spot_lon'], footprint=True)
        day = (v['visited_at'] - v['started_at']).days + 1 if v['started_at'] else None
        visited.append(dict(base, visit_id=str(v['id']), visited_at=v['visited_at'].timestamp(),
                            rating=float(v['rating']) if v['rating'] is not None else None, memo=v['memo'],
                            trip_id=str(v['trip_id']) if v['trip_id'] else None, trip_day=day))
    saved = [dict(sv.card(sv.items()[r['place_id']], None), saved_at=r['saved_at'].timestamp())
             for r in db.rows('select * from saved where user_id = %s order by saved_at desc', uid) if r['place_id'] in sv.items()]
    return {'visited': visited, 'saved': saved}


class VisitPatch(BaseModel):
    rating: Optional[float] = None
    memo: Optional[str] = Field(None, max_length=500)


@router.patch('/visits/{visit_id}')
def patch_visit(visit_id: UUID, body: VisitPatch, uid: str = Depends(current_user)):
    v = db.one('select place_id, turn_id, trip_id from visits where id = %s and user_id = %s', visit_id, uid)
    if not v: raise HTTPException(404)
    if body.rating is not None:
        if not 0 <= body.rating <= 5: raise HTTPException(400, '별점은 0~5')
        db.run('update visits set rating = %s where id = %s', body.rating, visit_id)
        db.log_reaction(uid, v['trip_id'], 'rate', place_id=v['place_id'], turn_id=v['turn_id'], props={'rating': body.rating})
    if body.memo is not None:
        db.run('update visits set memo = %s where id = %s', body.memo, visit_id)
    return {'ok': True}


@router.delete('/visits/{visit_id}')
def delete_visit(visit_id: UUID, uid: str = Depends(current_user)):
    db.run('delete from visits where id = %s and user_id = %s', visit_id, uid)
    return {'ok': True}


class SpotIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    memo: Optional[str] = Field(None, max_length=500)


@router.post('/spots')
def add_spot(body: SpotIn, uid: str = Depends(current_user)):
    """직접 등록(발자국): 사용자가 만든 장소. 추천 DB 에는 넣지 않는다."""
    sid = db.run('insert into spots(user_id, name, lat, lon, memo) values (%s, %s, %s, %s, %s) returning id',
                 uid, body.name, body.lat, body.lon, body.memo)
    vid = db.run('insert into visits(user_id, trip_id, spot_id, source, memo) values (%s, %s, %s, %s, %s) returning id',
                 uid, db.current_trip(uid), sid, 'manual', body.memo)
    return {'ok': True, 'visit_id': str(vid)}
