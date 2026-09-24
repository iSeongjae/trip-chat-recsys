"""sample_50.csv 판정 (Claude judgment 2026-09-24, 이름·태그만 보고 판단) → validation/judgments.csv + 요약.
verdict: correct / policy_violation(규칙과 다르지만 실제로 그럴듯) / wrong / unsure"""
import collections, csv, os
V = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data', 'interim', 'gold', 'validation')
J = {  # 순번: (verdict, 올바른 라벨, 메모)
    1: ('correct', 'unknown', '고유명사+restaurant'), 2: ('wrong', 'teishoku_don', 'トラック飯=트럭기사 식당(정식)'),
    3: ('correct', 'unknown', 'pub+고유명사'), 4: ('wrong', 'ramen', '麺屋 는 대개 라멘집'), 5: ('correct', 'unknown', ''),
    6: ('correct', 'unknown', ''), 7: ('correct', 'unknown', 'キッチン 만으로는 불명'), 8: ('unsure', '', '三日月軒: 라멘·중화 가능성, 확신 없음'),
    9: ('correct', 'asian', ''), 10: ('correct', 'nabe', ''), 11: ('correct', 'korean', ''), 12: ('correct', 'udon_soba', ''),
    13: ('policy_violation', 'unknown', 'amenity=bar+고유명사: 규칙상 unknown, 실제로는 스낵바일 가능성'),
    14: ('policy_violation', 'unknown', '위와 같음'), 15: ('correct', 'western', ''), 16: ('policy_violation', 'unknown', '위와 같음'),
    17: ('wrong', 'unknown', '肉ダイニング: 야키니쿠·스테이크 계열, teishoku 아님'), 18: ('correct', 'sweets', ''),
    19: ('wrong', 'unknown', '魚売街: 해산물 이자카야 계열, bar 아님'), 20: ('correct', 'western', ''),
    21: ('policy_violation', 'unknown', 'pub+고유명사'), 22: ('correct', 'western', ''), 23: ('wrong', 'unknown', '炊い処: 요리집, bar 아님'),
    24: ('correct', 'chinese', ''), 25: ('correct', 'cafe', '규칙 7'), 26: ('correct', 'cafe', ''),
    27: ('policy_violation', 'unknown', 'pub+고유명사, 실제 이자카야일 가능성'), 28: ('correct', 'chinese', ''),
    29: ('policy_violation', 'unknown', 'bar+고유명사'), 30: ('policy_violation', 'unknown', 'bar+고유명사'), 31: ('correct', 'udon_soba', ''),
    32: ('correct', 'yakiniku', 'barbecue 대응'), 33: ('correct', 'cafe', ''), 34: ('correct', 'cafe', ''), 35: ('correct', 'ramen', ''),
    36: ('correct', 'ramen', 'cuisine=ramen'), 37: ('wrong', 'unknown', '炭や: 숯불구이 계열, bar 아님'), 38: ('correct', 'teishoku_don', 'めし'),
    39: ('correct', 'cafe', ''), 40: ('policy_violation', 'unknown', 'bar+고유명사'),
    **{i: ('correct', None, '') for i in range(41, 51)},
}
rows = list(csv.DictReader(open(os.path.join(V, 'sample_50.csv'), encoding='utf-8')))
with open(os.path.join(V, 'judgments.csv'), 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0]) + ['verdict', 'correct_label', 'note', 'source']); w.writeheader()
    for i, r in enumerate(rows, 1):
        v, lab, note = J[i]
        w.writerow(dict(r, verdict=v, correct_label=lab or r['label'], note=note, source='Claude judgment 2026-09-24'))
by = collections.defaultdict(collections.Counter)
for i, r in enumerate(rows, 1): by[r['stratum']][J[i][0]] += 1
for k, c in by.items(): print(f"{k:<12} {sum(c.values()):>2}곳 | " + ' '.join(f'{v} {c[v]}' for v in ('correct', 'policy_violation', 'wrong', 'unsure')))
