"""사용자 프로필 JSON: session(쉽게 변함) + stable(잘 안 변함, 근거가 쌓일 때까지 공란).

stable 채우기 규칙
- 사용자가 말하면(explicit) 즉시 채움.
- 말하지 않으면 근거가 MIN_OBS 번 쌓이기 전까지 null.
- 쌓이면 최빈값 비중이 DOMINANCE 이상일 때만 기본값(inferred), 아니면 계속 null(취향이 일정하지 않음).
- 기본값으로 채워진 의도는 근거로 세지 않음(자기 강화 방지).
- 말한 값은 '대기(pending)' 로 두고 사용자가 실제로 고를 때(select) 한 턴에 한 번만 확정.
  같은 턴에 다시 뽑으면 대기 근거를 덮어씀 → 마음을 바꾸면 마지막 의도만 근거가 된다.
"""
import collections, statistics

MIN_OBS = 3
DOMINANCE = 0.6
TRAITS = ('local', 'max_distance_km', 'cuisine')  # + after_<category> 는 동적으로 생김
CUISINE_CATS = ('meal', 'bar')


def new_profile(user_id):
    return {'user_id': user_id,
            'session': {'current': None, 'companion': None, 'weather': None, 'visited': [], 'intent': {}, 'last_category': None, 'turn': 0},
            'stable': {t: _empty() for t in TRAITS},
            'taste': {'sub': {}}, 'n_reactions': 0}


def _empty():
    return {'value': None, 'source': 'unset', 'evidence': {}}


def _trait(p, name):
    return p['stable'].setdefault(name, _empty())


def _add(p, name, value):
    t = _trait(p, name)
    if name == 'max_distance_km':
        t['evidence'] = (t['evidence'] if isinstance(t['evidence'], list) else []) + [float(value)]
    else:
        ev = t['evidence'] if isinstance(t['evidence'], dict) else {}
        ev[str(value)] = ev.get(str(value), 0) + 1
        t['evidence'] = ev
    _infer(t, name)


def _infer(t, name):
    if t['source'] == 'explicit':
        return
    ev = t['evidence']
    if name == 'max_distance_km':
        if len(ev) >= MIN_OBS:
            t['value'], t['source'] = statistics.median(ev), 'inferred'
        return
    n = sum(ev.values())
    if n < MIN_OBS:
        t['value'], t['source'] = None, 'unset'
        return
    top, c = max(ev.items(), key=lambda x: x[1])
    if c / n >= DOMINANCE:
        t['value'] = {'true': True, 'false': False}.get(top, top); t['source'] = 'inferred'
    else:
        t['value'], t['source'] = None, 'unset'   # 일정하지 않으면 공란 유지


def set_explicit(p, name, value):
    """사용자가 직접 말한 안정 특성 ("나 원래 로컬 맛집 좋아해")."""
    t = _trait(p, name)
    t['value'], t['source'] = value, 'explicit'
    if name != 'max_distance_km':
        _add(p, name, value); t['value'], t['source'] = value, 'explicit'


def apply_turn(p, turn):
    """LLM 이 뽑은 이번 턴 JSON 을 프로필에 병합하고, 빈 의도는 stable 기본값으로 채움.
    turn = {"session": {current/companion/weather 중 바뀐 것}, "intent": {...}, "stable": {명시적 특성}}
    반환: (채워진 intent, 프로필에서 채운 필드 목록)"""
    s = p['session']
    for k, v in (turn.get('session') or {}).items():
        if k in ('current', 'companion', 'weather') and v is not None:
            s[k] = v
    for k, v in (turn.get('stable') or {}).items():
        set_explicit(p, k, v)
    said = dict(turn.get('intent') or {})
    intent, filled = dict(said), []
    # 말한 값만 근거 후보로 — select 때 확정 (같은 턴 재조회는 덮어씀)
    pending = []
    if 'local' in said:
        pending.append(('local', 'true' if said['local'] else 'false'))
    if 'max_distance_km' in said:
        pending.append(('max_distance_km', said['max_distance_km']))
    if 'next_category' in said and s['last_category']:
        pending.append((f"after_{s['last_category']}", said['next_category']))
    s['pending_evidence'] = pending
    # 빈 의도 채우기
    if 'next_category' not in intent and s['last_category']:
        v = _trait(p, f"after_{s['last_category']}")['value']
        if v:
            intent['next_category'] = v; filled.append('next_category')
    for k in ('max_distance_km', 'local'):
        if k not in intent and p['stable'][k]['value'] is not None:
            intent[k] = p['stable'][k]['value']; filled.append(k)
    intent.setdefault('max_distance_km', 1.0)
    s['intent'] = intent
    return intent, filled


def on_select(p, item):
    """실제로 고른 곳 → 이번 턴 대기 근거 확정 + 식사·술이면 메뉴 근거, 카테고리 전환 기준 갱신. 턴 종료."""
    for name, value in p['session'].pop('pending_evidence', []):
        _add(p, name, value)
    p['session']['turn'] += 1
    if item['category'] in CUISINE_CATS:
        _add(p, 'cuisine', item['sub'])
    p['session']['last_category'] = item['category']


def summary(p):
    return {k: (f"{v['value']} ({v['source']})" if v['value'] is not None else
                f"공란 (근거 {sum(v['evidence'].values()) if isinstance(v['evidence'], dict) else len(v['evidence'])}/{MIN_OBS})")
            for k, v in p['stable'].items()}
