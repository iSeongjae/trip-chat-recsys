"""후보 생성기: LLM 이 뽑은 조건 JSON(constraints/context) → 규칙 필터를 순서대로 적용 → 후보 목록.

규칙은 (이름, 적용 조건, 통과 판정) 목록. 데이터가 생기면(영업시간·예산 등) 같은 형식으로 추가한다.
"""
import math
from .geo import haversine_km
from .textnorm import norm, same_name
from .categories import resolve, matches

SAME_PLACE_KM = 0.1  # 이름이 같고 이 거리 안이면 같은 가게로 봄

LOCAL_APPLIES = ('sight', 'walk', 'shop', 'rest')
ATTRACTION_CATS = LOCAL_APPLIES

# 테마 칩 (관광지만, 위키 문서 있는 곳): 통과 조건과 랭킹 점수(0~1). season 은 이번 달 조회수 / 월평균
THEMES = {
    'famous': (lambda it, m: it.get('popularity', 0) >= 0.6, lambda it, m: it['popularity']),
    'local':  (lambda it, m: it.get('local', -9) > 0,       lambda it, m: min(1.0, 0.5 + it['local'] / 4)),
    'known':  (lambda it, m: it.get('known', -9) > 0,       lambda it, m: min(1.0, 0.5 + it['known'] / 4)),
    'hidden': (lambda it, m: it.get('hidden', -9) > 0,      lambda it, m: min(1.0, 0.5 + it['hidden'] / 4)),
    'season': (lambda it, m: 'season' in it and it['season'][m - 1] >= 1.3, lambda it, m: min(1.0, 0.3 + (it['season'][m - 1] - 1) / 2)),
}


def theme_score(theme, month):
    """랭킹에서 인기도 대신 쓸 점수 함수 (theme 없으면 None)."""
    return (lambda it: THEMES[theme][1](it, month)) if theme in THEMES else None


def visited_same(it, visited_ids, visited_items):
    """방문한 곳이거나, 방문한 곳과 이름이 같고 100m 안(DB 중복 등록)이면 True. 카테고리와 무관하게 본다."""
    if it['id'] in visited_ids:
        return True
    return any(haversine_km(v['lat'], v['lon'], it['lat'], it['lon']) <= SAME_PLACE_KM and same_name(v['name'], it['name'])
               for v in visited_items)


def _visited_same(it, ctx):
    return visited_same(it, ctx['_visited_ids'], ctx['_visited_items'])


def _rules(c, ctx):
    cur = ctx.get('current')
    return [
        # next_category 가 없으면(테마 칩만 누름) 관광지 전체
        ('카테고리',   True,                          lambda it: it['category'] == c['next_category'] if c.get('next_category')
                                                               else it['category'] in ATTRACTION_CATS),
        ('테마',       c.get('theme') in THEMES,       lambda it: THEMES[c['theme']][0](it, c.get('month', 1))),
        # 종류 조건: 자유 텍스트 → 상위 코드·세부 카테고리(겹침 관계 포함)·넓은 분류 (rules/category_names.json).
        # 종류를 모르는 곳(unknown)은 포함 조건이 있으면 빠지고, 없으면 그대로 후보
        ('포함 종류',    bool(c.get('include_sub')),   lambda it: matches(it, ctx['_inc'])),
        ('제외 종류',    bool(c.get('exclude_sub')),   lambda it: not matches(it, ctx['_exc'])),
        # 브랜드 요청("돈키호테 가고 싶어"): 이름·brand 태그에 포함 (가운뎃점 등 표기 차이는 정규화로 흡수)
        ('브랜드',      bool(c.get('include_brand')),  lambda it: any(norm(b) in norm(it['name'] + (it.get('brand') or '')) for b in c['include_brand'])),
        ('방문지 제외',  bool(ctx.get('visited')),      lambda it: not _visited_same(it, ctx)),
        # 로컬: 관광지는 유명 관광지(인기도 0.6+) 제외. 식당은 로컬 여부 데이터가 없어 미적용
        ('로컬(유명 관광지 제외)', bool(c.get('local')) and c.get('next_category') in LOCAL_APPLIES,
                                               lambda it: it['popularity'] < 0.6),
        ('거리',       cur is not None,               lambda it: haversine_km(cur['lat'], cur['lon'], it['lat'], it['lon']) <= c['max_distance_km']),
    ]


CELL = 0.05   # 공간 격자 (위도 약 5.5km). 전국 37만 곳을 매번 훑지 않고 주변 칸만 본다
_grid = {}


def grid(items):
    """items dict 마다 한 번 만드는 격자 인덱스 {(i, j): [item, ...]}."""
    key = id(items)
    if key not in _grid:
        g = {}
        for it in items.values():
            g.setdefault((int(it['lat'] // CELL), int(it['lon'] // CELL)), []).append(it)
        _grid.clear(); _grid[key] = g
    return _grid[key]


def nearby(items, lat, lon, km):
    """위경도 상자(반경 km) 안의 아이템."""
    g = grid(items)
    dlat = km / 110.0; dlon = dlat / max(0.2, math.cos(math.radians(lat)))
    out = []
    for i in range(int((lat - dlat) // CELL), int((lat + dlat) // CELL) + 1):
        for j in range(int((lon - dlon) // CELL), int((lon + dlon) // CELL) + 1):
            for it in g.get((i, j), ()):
                if abs(it['lat'] - lat) <= dlat and abs(it['lon'] - lon) <= dlon:
                    out.append(it)
    return out


def generate(query, items):
    """query = {"constraints": {...}, "context": {...}} → (candidates[(id, dist_km, flags)], trace[(규칙, 통과 수)], notes)."""
    c, ctx = query['constraints'], dict(query['context'])
    ctx['_visited_ids'] = set(ctx.get('visited') or [])
    ctx['_visited_items'] = [items[i] for i in ctx['_visited_ids'] if i in items]
    ctx['_inc'], ctx['_exc'] = resolve(c.get('include_sub')), resolve(c.get('exclude_sub'))
    notes = [f"사전에 없는 종류 '{t}' — 이름에 포함된 곳으로 찾음" for t in ctx['_inc']['unresolved'] + ctx['_exc']['unresolved']]
    trace = [('전체', len(items))]
    cur = ctx.get('current')
    if cur is not None:  # 거리 규칙 전에 격자 인덱스로 주변만 (전국 DB)
        pool = nearby(items, cur['lat'], cur['lon'], c['max_distance_km'])
    else:
        pool = list(items.values())
    for name, active, keep in _rules(c, ctx):
        if active:
            pool = [it for it in pool if keep(it)]
            trace.append((name, len(pool)))
    cur = ctx['current']
    cands = [(it['id'], haversine_km(cur['lat'], cur['lon'], it['lat'], it['lon']), []) for it in pool]
    return cands, trace, notes
