"""세부 카테고리 체계 (rules/categories.json): 상위 코드, 조건 확장(also_match), 이름 보정(fine_overrides),
이름 키워드 → 세부 카테고리(fine_keywords), 조건 자유 텍스트 → 카테고리(category_names)."""
import re, unicodedata
from .rules import load

_C = load('categories.json')
PARENT = {f['id']: f['parent'] for f in _C['fine']}
ALSO = _C['also_match']['map']
_REGION = load('regions.json')
_OVR = [(re.compile(o['pattern'], re.I), o) for o in load('fine_overrides.json')]
_KW = [(re.compile(k['pattern'], re.I), k['fine']) for k in load('fine_keywords.json')]
_N = load('category_names.json')
KO = {**{c: v[0] for c, v in _N['coarse'].items()}, **{f'fine:{f}': v[0] for f, v in _N['fine'].items()}}


def _key(s):
    return re.sub(r'[\s·・/()（）]', '', unicodedata.normalize('NFKC', s or '').lower())


_TERM = {}
for c, names in _N['coarse'].items():
    for n in names: _TERM.setdefault(_key(n), {'coarse': set(), 'fine': set(), 'broad': set()})['coarse'].add(c)
for f, names in _N['fine'].items():
    for n in names: _TERM.setdefault(_key(n), {'coarse': set(), 'fine': set(), 'broad': set()})['fine'].add(f)
for t, v in _N['terms'].items():
    e = _TERM.setdefault(_key(t), {'coarse': set(), 'fine': set(), 'broad': set()})
    for k in ('coarse', 'fine', 'broad'): e[k].update(v.get(k, []))


def expand(fine_ids):
    """요청한 세부 카테고리 → 조건에 걸리는 세부 카테고리 집합 (예: izakaya → izakaya·yakitori·kushikatsu·tebasaki)."""
    out = set(fine_ids)
    for f in fine_ids:
        out.update(ALSO.get(f, []))
    return out


def in_region(region, lat, lon):
    r = _REGION[region]
    return r['lat'][0] <= lat <= r['lat'][1] and r['lon'][0] <= lon <= r['lon'][1]


def override(name, lat=None, lon=None):
    """이름(·지역) 규칙으로 정해지는 세부 카테고리 (fine, parent, note) 또는 None."""
    n = unicodedata.normalize('NFKC', name or '')
    for rx, o in _OVR:
        if 'region' in o and (lat is None or not in_region(o['region'], lat, lon)):
            continue
        if rx.search(n):
            return o['fine'], o['parent'], o['note']
    return None


def name_fine(name, coarse):
    """이름 키워드로 정해지는 세부 카테고리 중 상위 코드가 coarse 와 맞는 것들."""
    n = unicodedata.normalize('NFKC', name or '')
    return list(dict.fromkeys(f for rx, f in _KW if PARENT[f] == coarse and rx.search(n)))


ATTR_SUBS = {'신사', '사찰', '명소', '박물관', '전망대', '유적지', '성', '미술관', '테마파크', '동물원', '수족관', '공원', '산', '정원', '폭포',
             '해변', '잡화 할인점', '전자제품', '드럭스토어', '기념품점', '쇼핑몰', '애니·취미', '백화점', '온천·목욕탕', '사우나'}  # build_items.ATTR_SUB 값
_SUB_ALIAS = {'절': '사찰', '온천': '온천·목욕탕', '목욕탕': '온천·목욕탕', '바다': '해변', '해수욕장': '해변', '돈키호테': None, '드럭': '드럭스토어',
              '약국': '드럭스토어', '백화점': '백화점', '애니': '애니·취미', '피규어': '애니·취미', '성곽': '성', '뮤지엄': '박물관'}
_SUB_KEY = {_key(s): s for s in ATTR_SUBS} | {_key(a): s for a, s in _SUB_ALIAS.items() if s}


def resolve(terms):
    """조건 자유 텍스트 목록 → {'coarse','fine','broad','sub'} 집합과 사전에 없는 말(unresolved). sub 는 관광지 하위분류."""
    out = {'coarse': set(), 'fine': set(), 'broad': set(), 'sub': set(), 'unresolved': []}
    for t in terms or []:
        e = _TERM.get(_key(t))
        if e:
            for k in ('coarse', 'fine', 'broad'): out[k] |= e[k]
        elif _key(t) in _SUB_KEY:
            out['sub'].add(_SUB_KEY[_key(t)])
        else:
            out['unresolved'].append(t)
    out['fine'] = expand(out['fine'])
    return out


def matches(it, r):
    """아이템이 resolve 결과에 걸리는지. 음식점은 cuisine(상위)·fine·broad, 사전에 없는 말은 이름·하위분류 포함."""
    if it.get('cuisine') in r['coarse'] or set(it.get('fine') or ()) & r['fine'] or (it.get('broad') and it['broad'] in r['broad']) \
            or ('cuisine' not in it and it['sub'] in r.get('sub', ())):
        return True
    return any(_key(t) in _key(it['name']) or _key(t) == _key(it.get('sub')) for t in r['unresolved'])
