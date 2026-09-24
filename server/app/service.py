"""대화 한 턴 처리: 파서 결과 → 프로필 병합 → 후보 생성(반경 자동 확대) → 랭킹 8곳 → 카드. 기존 japan_rec 을 그대로 쓴다."""
import json, os, sys, time, unicodedata, re, datetime
from . import config

sys.path.insert(0, os.path.join(config.ROOT, 'src'))
from japan_rec import recommender as rec, candidates as cg, profile as pf
from japan_rec.categories import KO
from japan_rec.geo import haversine_km
from japan_rec.textnorm import norm

CAT_KO = {'meal': '식사', 'cafe': '카페', 'bar': '술', 'sight': '구경', 'walk': '산책·자연', 'shop': '쇼핑', 'rest': '휴식'}
THEME_KO = {'famous': '유명 명소', 'local': '현지인 인기', 'known': '한국인 인기', 'hidden': '숨은 명소', 'season': '{m}월 명소'}
RADII = (1.0, 2.0, 5.0, 15.0)   # 후보가 N_SHOW 보다 적으면 넓혀 감
_stations = None


def items():
    return rec.items()


_B32 = '0123456789bcdefghjkmnpqrstuvwxyz'


def geohash(lat, lon, n=6):
    """좌표 → geohash (6자리 ≈ 1.2km × 0.6km). 로그·세션에 저장하는 위치는 이것만."""
    la, lo, out, bit, ch, even = [-90.0, 90.0], [-180.0, 180.0], '', 0, 0, True
    while len(out) < n:
        rng, v = (lo, lon) if even else (la, lat)
        mid = (rng[0] + rng[1]) / 2
        if v >= mid: ch |= 1 << (4 - bit); rng[0] = mid
        else: rng[1] = mid
        even = not even
        if bit < 4: bit += 1
        else: out += _B32[ch]; bit, ch = 0, 0
    return out


_geoip = False


def country(ip):
    """접속 IP → 국가 두 글자 (KR, JP …). IP 는 저장하지 않고 국가만 로그에 남긴다. 데이터 파일이 없으면 None."""
    global _geoip
    if _geoip is False:
        try:
            import maxminddb
            _geoip = maxminddb.open_database(config.GEOIP_PATH) if os.path.exists(config.GEOIP_PATH) else None
        except Exception:
            _geoip = None
    if not _geoip or not ip:
        return None
    try:
        return ((_geoip.get(ip) or {}).get('country') or {}).get('iso_code')
    except ValueError:      # 'testclient' 같은 IP 가 아닌 값
        return None


def versions():
    ip = rec.ITEMS_PATH
    return {'ranker': f'n{rec.N_SHOW}-k{rec.K}-d{rec.DIST_WEIGHT}', 'items': os.environ.get('ITEMS_VERSION') or
            (datetime.date.fromtimestamp(os.path.getmtime(ip)).isoformat() if os.path.exists(ip) else None), 'env': config.APP_ENV}


JST = datetime.timezone(datetime.timedelta(hours=9))


def today():
    return datetime.datetime.now(JST).date()   # 여행지(일본) 날짜 기준


def month():
    return today().month


def season_months(d=None):
    """월별 명소 칩에 보여 줄 달: 1~7일은 지난달+이번 달, 8~23일은 이번 달, 24일 이후는 이번 달+다음 달."""
    d = d or today()
    prev, nxt = (d.month - 2) % 12 + 1, d.month % 12 + 1
    return [prev, d.month] if d.day <= 7 else [d.month] if d.day <= 23 else [d.month, nxt]


_st_index = None
_name_index = None


def stations():
    """역 목록 + 이름 키 인덱스 {정규화 이름: [역]} (요청마다 9천 개 이름을 정규화하지 않게)."""
    global _stations, _st_index
    if _stations is None:
        p = os.path.join(config.ROOT, 'data', 'interim', 'osm_stations_jp.json')
        _stations = json.load(open(p)) if os.path.exists(p) else []
        _st_index = {}
        for s in _stations:
            for v in set(_k(v) for v in s['name'].values()):
                _st_index.setdefault(v, []).append(s)
    return _stations


def name_index():
    """장소 이름 검색용: (정규화 한글 이름 + 일본어 원문, 아이템) 목록. 한 번만 만든다."""
    global _name_index
    if _name_index is None:
        _name_index = [(norm(it['name']) + '|' + norm(it.get('name_ja') or ''), it) for it in items().values()]
    return _name_index


def _k(s):
    return re.sub(r'(역|駅|station)$', '', norm(unicodedata.normalize('NFKC', s or '')))


def geocode(query, near=None):
    """역 이름 → 없으면 장소 이름. 여러 개면 현재 위치에서 가까운 것, 없으면 인기 높은 것."""
    q = _k(query)
    if not q:
        return None
    stations()
    hits = [dict(name=s['name'].get('name:ko') or s['name'].get('name'), lat=s['lat'], lon=s['lon'], pop=1.0) for s in _st_index.get(q, ())]
    if not hits:
        hits = [dict(name=it['name'], lat=it['lat'], lon=it['lon'], pop=it.get('popularity', 0))
                for key, it in name_index() if q in key][:2000]
    if not hits:
        return None
    if near:
        return min(hits, key=lambda h: haversine_km(near['lat'], near['lon'], h['lat'], h['lon']))
    return max(hits, key=lambda h: h['pop'])


_starts = None


def start_points():
    global _starts
    if _starts is None:
        _starts = json.load(open(os.path.join(config.ROOT, 'rules', 'start_points.json')))['airports']
    return [dict(a, kind='공항', sub=a['city']) for a in _starts]


def geo_search(q, limit=12):
    """공항 → 역 → 장소 순으로 이름이 들어간 곳. 장소는 인기도 높은 순."""
    k = _k(q)
    if not k:
        return []
    out = [a for a in start_points() if k in _k(a['name']) or k in _k(a['city']) or k == a['code'].lower()]
    stations()
    seen = {}
    keys = sorted((key for key in _st_index if k in key), key=lambda key: (key != k, not key.startswith(k), len(key)))  # 정확히 같은 이름 먼저
    for key in keys:
        for st in _st_index[key]:
            nm = st['name'].get('name:ko') or st['name'].get('name')
            if any(haversine_km(st['lat'], st['lon'], a, b) < 2 for a, b in seen.get(nm, ())): continue   # JR·지하철 등 같은 역 중복
            seen.setdefault(nm, []).append((st['lat'], st['lon']))
            out.append(dict(name=nm, sub=st['name'].get('name') if st['name'].get('name:ko') else (st.get('operator') or ''), kind='역',
                            lat=st['lat'], lon=st['lon']))
        if len(out) >= limit: break
    if len(out) < limit:
        hits = sorted((it for key, it in name_index() if k in key), key=lambda it: -it.get('popularity', 0))
        out += [dict(name=it['name'], sub=it.get('name_ja') or '', kind=it['sub'], lat=it['lat'], lon=it['lon']) for it in hits[:limit - len(out)]]
    return out[:limit]


def tags(it, m=None):   # m: 'N월 명소' 태그를 붙일 달 (기본 이번 달)
    m = m or month()
    t = []
    if it.get('popularity', 0) >= 0.6 and it['category'] in cg.ATTRACTION_CATS: t.append('유명 명소')
    if it.get('local', -9) > 0: t.append('현지인 인기')
    if it.get('known', -9) > 0: t.append('한국인 인기')
    if it.get('hidden', -9) > 0: t.append('숨은 명소')
    if 'season' in it and it['season'][m - 1] >= 1.3: t.append(f'{m}월 명소')
    return t


def kind(it):
    f = (it.get('fine') or [None])[0]
    return KO.get(f'fine:{f}') if f else it['sub']


def card(it, cur, m=None):
    d = haversine_km(cur['lat'], cur['lon'], it['lat'], it['lon']) if cur else None
    return dict(id=it['id'], name=it['name'], name_ja=it.get('name_ja') if it.get('name_ja') != it['name'] else None,
                category=it['category'], kind=kind(it), distance_m=round(d * 1000) if d is not None else None,
                lat=it['lat'], lon=it['lon'], tags=tags(it, m))


def view(p):
    return {'preferences': p['taste'], 'n_reactions': p['n_reactions'],
            'context': {'current': p['session']['current'], 'visited': p['session']['visited']}}


def in_service_area(lat, lon, km=30):
    """주변(약 30km)에 장소가 하나라도 있으면 서비스 지역(일본). 한국 등에서 켠 GPS 를 걸러낸다."""
    return bool(cg.nearby(items(), lat, lon, km))


def set_location(p, lat, lon, name='현재 위치', src='gps'):
    p['session']['current'] = {'name': name, 'lat': lat, 'lon': lon, 'src': src}


def public_current(p):
    """응답·대화 기록용 현재 위치: GPS 는 동네 단위로만."""
    cur = p['session'].get('current')
    if not cur: return None
    out = {k: cur[k] for k in ('name', 'lat', 'lon')}
    if cur.get('src') == 'gps':
        out['lat'], out['lon'] = round(cur['lat'], config.LOCATION_DECIMALS), round(cur['lon'], config.LOCATION_DECIMALS)
    return out


def stored(p):
    """저장용 사본: GPS 좌표는 동네 단위(소수 2자리)로만 남긴다 (개인정보 처리방침)."""
    q = json.loads(json.dumps(p))
    cur = q['session'].get('current')
    if cur and cur.get('src') == 'gps':
        cur['lat'], cur['lon'] = round(cur['lat'], config.LOCATION_DECIMALS), round(cur['lon'], config.LOCATION_DECIMALS)
    q['session'].pop('candidates', None)
    q['session'].pop('pending_evidence_tmp', None)
    return q


def current_geo(p):
    cur = p['session'].get('current')
    return geohash(cur['lat'], cur['lon']) if cur else None


def mark_visited(p, name):
    q = norm(name)
    cur = p['session']['current']
    hits = [it for key, it in name_index() if q and q in key]
    if not hits:
        return None
    hit = min(hits, key=lambda it: haversine_km(cur['lat'], cur['lon'], it['lat'], it['lon'])) if cur else hits[0]
    if hit['id'] not in p['session']['visited']:
        p['session']['visited'].append(hit['id'])
    return hit


def recommend(p, intent):
    """intent → dict(cards, radius, notes, trace, n_candidates, logged, w).
    logged 는 turn_logs.candidates 에 남길 보여준 목록(점수 분해). 방문한 곳은 후보 생성·랭킹 두 단계에서 뺀다."""
    s = p['session']
    cur = s['current']
    theme = intent.get('theme') if intent.get('theme') in cg.THEMES else None
    if theme and intent.get('next_category') in ('meal', 'cafe', 'bar'):
        theme = None
    m = intent.get('month') if theme == 'season' and intent.get('month') in range(1, 13) else month()
    c = dict(intent, month=m, theme=theme)
    base = float(c.get('max_distance_km') or 1.0)
    radii = [r for r in (base,) + RADII if r >= (5.0 if theme else base)]
    for r in radii:
        c['max_distance_km'] = r
        cands, trace, notes = cg.generate({'constraints': c, 'context': {'current': cur, 'visited': s['visited']}}, items())
        if len(cands) >= rec.N_SHOW:
            break
    if r > base and cands:
        notes.append(f'가까운 곳이 적어서 {r:g}km 까지 넓혔어요')
    picks = rec.recommend(cands, view(p), r, pop_fn=cg.theme_score(theme, m))
    s['last_shown'] = [x['id'] for x in picks]
    s['intent'] = {k: v for k, v in c.items() if k != 'month' or theme == 'season'}
    logged = [dict(rank=i + 1, place_id=x['id'], slot=x['slot'], score=x['score'], pop=x['popularity'], taste=x['content'],
                   dist_m=round(x['dist_km'] * 1000), flags=x['flags']) for i, x in enumerate(picks)]
    return dict(cards=[card(items()[x['id']], cur, m) for x in picks], radius=r, radius_asked=base, notes=notes, trace=trace,
                n_candidates=len(cands), logged=logged, w=picks[0]['w'] if picks else None)


def summary(intent, cards, r):
    what = ', '.join(intent.get('include_sub') or []) or (THEME_KO.get(intent.get('theme') or '', '').format(m=intent.get('month') or month())) \
        or CAT_KO.get(intent.get('next_category'), '')
    return f'{what} {len(cards)}곳 찾았어요' if cards else f'{r:g}km 안에 조건에 맞는 곳이 없어요'
