"""추천 핵심 함수: 랭킹·피드백 학습. 웹 API(server/)는 이 함수들을 얇게 감싸기만 한다."""
import json, os, random

from .geo import haversine_km
from .candidates import visited_same

ITEMS_PATH = os.environ.get('ITEMS_PATH') or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'processed', 'items_japan.json')
PREF_ATTRS = ('sub',)  # 취향을 학습하는 속성 (값 없는 아이템은 건너뜀)
K = 5                  # 개인화 전환 속도: w = 반응 수 / (반응 수 + K)
DIST_WEIGHT = 0.1      # 가까울수록 약간 가산 (동점 많은 식당용)
EVENT_UPDATE = {'select': ('a', 1.0), 'save': ('a', 0.7), 'detail': ('a', 0.3), 'skip': ('b', 0.3),
                'say_like': ('a', 3.0), 'say_dislike': ('b', 3.0)}

_items = None


def items():
    global _items
    if _items is None:
        _items = {i['id']: i for i in json.load(open(ITEMS_PATH))}
    return _items


def new_user():
    return {'preferences': {a: {} for a in PREF_ATTRS}, 'n_reactions': 0,
            'context': {'current': None, 'visited': []}}


def _content(user, it):
    scores = []
    for a in PREF_ATTRS:
        if it.get(a) is None:
            continue
        c = user['preferences'].setdefault(a, {}).get(str(it[a]), {'a': 1.0, 'b': 1.0})  # 처음 보는 값은 a=b=1 (모름)
        scores.append(c['a'] / (c['a'] + c['b']))
    return sum(scores) / len(scores) if scores else 0.5


N_SHOW = 8  # 추천 목록 길이: 5→8 에서 성공률 +4.1%p, 8→10 은 +0.7%p (sim_rec, 2026-09-24)


def recommend(candidates, user, radius_km, n=N_SHOW, seed=0, pop_fn=None):
    """④ 랭킹: (1-w)·인기도 + w·콘텐츠 - 거리 페널티. 마지막 1개는 탐색용.
    방문한 곳은 후보가 오래됐어도(선택 후 후보를 다시 만들지 않고 호출) 여기서 한 번 더 뺀다 — 절대 다시 추천하지 않음."""
    w = user['n_reactions'] / (user['n_reactions'] + K)
    vids = set(user.get('context', {}).get('visited') or [])
    vitems = [items()[i] for i in vids if i in items()]
    scored = []
    for cand in candidates:
        iid, d, flags = (list(cand) + [[]])[:3]
        it = items()[iid]
        if vids and visited_same(it, vids, vitems):
            continue
        pop, cont = (pop_fn(it) if pop_fn else it['popularity']), _content(user, it)
        s = (1 - w) * pop + w * cont - DIST_WEIGHT * d / radius_km
        scored.append(dict(id=iid, name=it['name'], sub=it['sub'], dist_km=round(d, 2), score=round(s, 3), flags=flags,
                           popularity=pop, content=round(cont, 2), w=round(w, 2), slot='top'))
    scored.sort(key=lambda x: -x['score'])
    top = scored[:n - 1]
    # 탐색: 상위에 없는 하위분류 중 취향 점수(샘플링)가 높은 곳 — 인기도는 보지 않음
    rest = [x for x in scored[n - 1:] if x['sub'] not in {t['sub'] for t in top}] or scored[n - 1:]
    if rest:
        rng = random.Random(seed)
        pick = max(rest, key=lambda x: x['content'] + rng.random() * 0.3)
        top.append(dict(pick, slot='explore'))
    return top


def log_feedback(user, item_id, event, position=None):
    """⑥ 갱신: 반응 → 하위분류 a/b 카운트. 선택하면 새 현재 위치 + 방문 목록."""
    it = items()[item_id]
    side, amt = EVENT_UPDATE[event]
    if event == 'skip' and position is not None:
        amt *= 1 / (1 + position)  # 아래 노출일수록 넘김의 의미가 작음
    for a in PREF_ATTRS:
        if it.get(a) is None:
            continue
        c = user['preferences'].setdefault(a, {}).setdefault(str(it[a]), {'a': 1.0, 'b': 1.0})
        c[side] += amt
    if not event.startswith('say_'):
        user['n_reactions'] += 1
    if event == 'select':
        user['context']['current'] = {'lat': it['lat'], 'lon': it['lon'], 'name': it['name']}
        user['context']['visited'].append(item_id)


def say_preference(user, sub, like=True):
    """발화로 말한 취향 ("라멘 좋아해") — 아이템 없이 하위분류에 직접 반영."""
    c = user['preferences']['sub'].setdefault(sub, {'a': 1.0, 'b': 1.0})
    c['a' if like else 'b'] += 3.0


def preference_summary(user, top=5):
    rows = sorted(((k, v['a'] / (v['a'] + v['b']), v['a'] + v['b'])
                   for a, p in user['preferences'].items() for k, v in p.items()), key=lambda x: (-x[1], -x[2]))
    return [f'{k} {s:.0%} (확신 {c:.1f})' for k, s, c in rows[:top]]
