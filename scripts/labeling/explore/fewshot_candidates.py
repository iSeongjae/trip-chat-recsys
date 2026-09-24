"""few-shot 예시 후보 추출 (규칙별 실제 OSM 가게 샘플). build_fewshot.py 의 예시는 여기 후보에서 골랐다."""
import json, os, random, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
O = [o for o in json.load(open(os.path.join(ROOT, 'data/interim/osm_eateries_jp.json'))) if o['name'].get('name')]
T = lambda o: ' '.join(f'{k}={v}' for k, v in o['tags'].items())
N = lambda o: o['name']['name']
def pick(cond, k=4, seed=0):
    xs = [o for o in O if cond(o)]; random.seed(seed)
    return [(o['osm_id'], N(o), T(o)) for o in random.sample(xs, min(k, len(xs)))], len(xs)
bad = re.compile('酒|居酒屋|焼|バー|BAR|Bar|パブ|カフェ|珈琲|食|丼|寿|鮨|蕎麦|そば|うどん|麺|ラーメン|カレー|鍋|屋台|亭|庵|屋')
C = {
    '中華そば+cuisine=chinese': lambda o: '中華そば' in N(o) and o['cuisine'] == 'chinese',
    '餃子/中華料理+chinese': lambda o: re.search('餃子|中華料理', N(o)) and o['cuisine'] == 'chinese' and 'ラーメン' not in N(o),
    '焼鳥+pub': lambda o: re.search('焼鳥|焼き鳥|やきとり', N(o)) and o['amenity'] == 'pub',
    '酒場+pub/bar': lambda o: re.search('居酒屋|酒場', N(o)) and o['amenity'] in ('pub', 'bar'),
    '甘味+cafe': lambda o: '甘味' in N(o) and o['amenity'] == 'cafe',
    '喫茶+cafe': lambda o: '喫茶' in N(o) and o['amenity'] == 'cafe',
    'cafe 고유명사': lambda o: o['amenity'] == 'cafe' and len(o['tags']) == 1 and not re.search('カフェ|珈琲|コーヒー|喫茶|cafe|coffee|ケーキ|甘味', N(o), re.I),
    'fast_food 고유명사': lambda o: o['amenity'] == 'fast_food' and len(o['tags']) == 1 and not re.search('バーガー|うどん|そば|ラーメン|寿司|弁当|丼', N(o)),
    '고유명사+cuisine=ramen': lambda o: o['cuisine'] == 'ramen' and not re.search('ラーメン|らーめん|拉麺|中華そば|麺|そば|ramen', N(o), re.I),
    'pub 고유명사': lambda o: o['amenity'] == 'pub' and len(o['tags']) == 1 and not bad.search(N(o)) and len(N(o)) <= 6,
    'japanese 고유명사': lambda o: o['tags'] == {'amenity': 'restaurant', 'cuisine': 'japanese'} and not bad.search(N(o)) and len(N(o)) <= 5,
    'インドカレー': lambda o: 'インドカレー' in N(o),
    '韓丼': lambda o: N(o).startswith('韓丼'),
    'ちゃんぽん': lambda o: 'ちゃんぽん' in N(o) and 'ラーメン' not in N(o),
    'food_court': lambda o: o['amenity'] == 'food_court',
    '焼肉+korean': lambda o: '焼肉' in N(o) and o['cuisine'] == 'korean' and '韓国' not in N(o),
}
for k, f in C.items():
    xs, n = pick(f); print(f'[{k}] {n}곳:', xs)
