import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from japan_rec import profile as pf

MEAL = {'category': 'meal', 'sub': '라멘'}
WALK = {'category': 'walk', 'sub': '공원'}


def test_requery_in_same_turn_counts_once():
    p = pf.new_profile('t')
    pf.on_select(p, WALK)                                  # 직전 카테고리 = walk
    pf.apply_turn(p, {'intent': {'next_category': 'meal', 'include_sub': ['양식']}})
    pf.apply_turn(p, {'intent': {'next_category': 'meal', 'include_sub': ['라멘']}})  # 같은 턴 재조회
    pf.on_select(p, MEAL)
    assert p['stable']['after_walk']['evidence'] == {'meal': 1}


def test_no_evidence_without_select():
    p = pf.new_profile('t')
    pf.apply_turn(p, {'intent': {'next_category': 'meal', 'max_distance_km': 0.5}})
    assert p['stable']['max_distance_km']['evidence'] == {}


def test_changed_mind_keeps_last_intent_only():
    p = pf.new_profile('t')
    pf.apply_turn(p, {'intent': {'next_category': 'meal', 'max_distance_km': 2.0}})
    pf.apply_turn(p, {'intent': {'next_category': 'meal', 'max_distance_km': 0.5}})
    pf.on_select(p, MEAL)
    assert p['stable']['max_distance_km']['evidence'] == [0.5]


def test_blank_until_three_then_dominant():
    p = pf.new_profile('t')
    for _ in range(2):
        pf.apply_turn(p, {'intent': {'next_category': 'sight', 'local': True}}); pf.on_select(p, WALK)
    assert p['stable']['local']['value'] is None
    pf.apply_turn(p, {'intent': {'next_category': 'sight', 'local': True}}); pf.on_select(p, WALK)
    assert p['stable']['local']['value'] is True and p['stable']['local']['source'] == 'inferred'
