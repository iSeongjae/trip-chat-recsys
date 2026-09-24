import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from japan_rec.categories import expand, override, PARENT


def test_expand_izakaya_includes_yakitori():
    assert {'izakaya', 'yakitori', 'kushikatsu'} <= expand(['izakaya'])
    assert expand(['ramen']) == {'ramen'}


def test_override_soba():
    assert override('中華そば 一心')[0] == 'ramen'
    assert override('三角そば', 26.2, 127.7)[0] == 'okinawa_soba'   # 오키나와
    assert override('三角そば', 35.0, 139.0) is None                # 본토
    assert override('焼きそば屋', 26.2, 127.7) is None
    assert PARENT['okinawa_soba'] == 'udon_soba'
