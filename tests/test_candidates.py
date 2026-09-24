import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from japan_rec import candidates as cg

CUR = {'lat': 33.59, 'lon': 130.41}


def _it(i, **kw):
    return dict(id=f'x{i}', name=f'가게{i}', category='bar', sub='이자카야', lat=33.59, lon=130.41, popularity=0.3, **kw)


def _q(**c):
    return {'constraints': dict(next_category='bar', max_distance_km=1.0, **c), 'context': {'current': CUR, 'visited': []}}


def _eat(i, cuisine, fine=(), cat='meal', **kw):
    return dict(id=i, name=f'가게{i}', category=cat, cuisine=cuisine, fine=list(fine), sub=cuisine, lat=33.59, lon=130.41, popularity=0.3, **kw)


def test_include_sub_uses_fine_and_also_match():
    items = {k: v for k, v in (('iz', _eat('iz', 'izakaya', ['izakaya'], 'bar')), ('yk', _eat('yk', 'yakitori', ['yakitori'], 'bar')),
                               ('unk', _eat('unk', 'unknown', cat='bar')), ('bar', _eat('bar', 'bar', ['cocktail_bar'], 'bar')))}
    cands, _, _ = cg.generate(_q(include_sub=['이자카야']), items)
    assert {c[0] for c in cands} == {'iz', 'yk'}          # 야키토리도 이자카야 조건에 걸림, unknown 은 빠짐
    cands, _, _ = cg.generate(_q(), items)
    assert 'unk' in {c[0] for c in cands}                 # 종류 조건 없으면 unknown 포함


def test_exclude_and_unresolved_term():
    items = {'r': _eat('r', 'ramen', ['ramen']), 'u': _eat('u', 'udon_soba', ['udon'])}
    q = _q(exclude_sub=['라멘']); q['constraints']['next_category'] = 'meal'
    cands, _, _ = cg.generate(q, items)
    assert {c[0] for c in cands} == {'u'}
    q = _q(include_sub=['가게r']); q['constraints']['next_category'] = 'meal'
    cands, _, notes = cg.generate(q, items)
    assert {c[0] for c in cands} == {'r'} and notes


def test_visited_never_recommended_even_with_stale_candidates():
    from japan_rec import recommender as rec
    rec._items = {'a': _eat('a', 'ramen', ['ramen']), 'b': _eat('b', 'ramen', ['ramen']),
                  'a2': dict(_eat('a2', 'ramen', ['ramen']), name='가게a')}  # a 와 같은 가게(이름 같고 같은 좌표, DB 중복)
    try:
        u = rec.new_user()
        stale = [('a', 0.1, []), ('b', 0.2, []), ('a2', 0.1, [])]
        assert {x['id'] for x in rec.recommend(stale, u, 1.0)} == {'a', 'b', 'a2'}
        rec.log_feedback(u, 'a', 'select')
        assert {x['id'] for x in rec.recommend(stale, u, 1.0)} == {'b'}   # 후보를 다시 만들지 않아도 빠짐
        q = {'constraints': dict(next_category='meal', max_distance_km=1.0), 'context': {'current': CUR, 'visited': u['context']['visited']}}
        cands, _, _ = cg.generate(q, rec._items)
        assert {c[0] for c in cands} == {'b'}
    finally:
        rec._items = None
