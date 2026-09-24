"""few-shot 예시 36개 생성 (실제 OSM 가게). 라벨은 Claude 가 골라 붙인 것 — 출처는 reason/verified_source 컬럼.
출력: data/interim/gold/fewshot_examples.jsonl, fewshot_exclude_ids.json, prompts/fewshot_examples.txt, prompts/fewshot.jsonl(classify.py 형식)"""
import json, os
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
O = {o['osm_id']: o for o in json.load(open(os.path.join(ROOT, 'data/interim/osm_eateries_jp.json')))}
T = lambda o: ' '.join(f'{k}={v}' for k, v in o['tags'].items())
K = 'Claude knowledge 2026-09-24'
EX = [  # (osm_id, label, 보여주는 규칙·이유, 검증 출처)
    ('n12644645729', 'ramen', '규칙 2: 中華そば는 cuisine=chinese여도 라멘', K),
    ('n4639803674', 'ramen', '규칙 2: 中華飯店이 있어도 ラーメン이 이름에 있으면 라멘', K),
    ('n9840208817', 'ramen', '이름에 단서가 없으면 구체적인 cuisine 태그를 따름', 'https://ramendb.supleks.jp/s/3755.html'),
    ('n1398310084', 'chinese', '중화요리 (라멘집 아님)', K),
    ('n8440790446', 'udon_soba', '手打ちそば', K),
    ('n6330260394', 'sushi', '回転寿司. 水産이 있어도 寿司가 우선', K),
    ('n3279826380', 'katsu_tempura', '天ぷら', K),
    ('n11056013972', 'yakitori', '규칙 4·6: amenity=pub이어도 やきとり → yakitori', K),
    ('n5564436192', 'izakaya', '규칙 6 예외: amenity=pub + 大衆酒場 → izakaya', K),
    ('n2188574641', 'bar', 'amenity=bar + 이름의 BAR', K),
    ('n5761244627', 'okonomi', 'お好み焼', K),
    ('n3789244404', 'teishoku_don', '食堂', K),
    ('n289347509', 'teishoku_don', '규칙 8: 체인(吉野家)이 amenity=fast_food보다 우선', K),
    ('n1196313861', 'curry', '규칙 8: CoCo壱番屋 → curry (cuisine=japanese보다 우선)', K),
    ('n6355864913', 'asian', 'インドカレー는 일본식 카레가 아니라 asian', K),
    ('n3124852844', 'kaiseki', '割烹', K),
    ('n11412513791', 'nabe', 'もつ鍋', K),
    ('n2234647332', 'jp_other', 'うなぎ (구체 코드 없는 일본 음식)', K),
    ('n3645512793', 'yakiniku', '규칙 1: 이름의 焼肉가 cuisine=korean보다 우선', K),
    ('n6795909294', 'steak_hamburg', 'ステーキ＆ハンバーグ', K),
    ('n13312514835', 'korean', '체인 韓丼 = 카루비동·순두부 한국요리 전문점 (cuisine=japanese는 틀린 태그)', 'https://kandon.jp/'),
    ('n7487254925', 'western', 'トラットリア (이탈리안)', K),
    ('n6364185532', 'western', '洋食', K),
    ('n11237273894', 'foreign_other', 'ケバブ는 튀르키예·중동 요리 → 이름에 アジアン이 있어도 foreign_other', K),
    ('n6550771007', 'cafe', '喫茶', K),
    ('n1879252650', 'cafe', '규칙 7: 단서가 amenity=cafe뿐 (실제로 스가모의 ロン珈琲)', 'https://gourmet.aumo.jp/gourmets/504163'),
    ('n6435754585', 'sweets', '규칙 5: 甘味処는 amenity=cafe여도 sweets', K),
    ('n11387121806', 'sweets', '규칙 1: パンケーキ 이름이 cuisine=burger보다 우선', K),
    ('n6697991858', 'bakery', 'ベーカリー', K),
    ('n287771323', 'fastfood', '버거 체인', K),
    ('n10899506687', 'other', 'フードホール: 종류는 분명하지만 목록에 없음', K),
    ('n6843825886', 'unknown', '규칙 9: 고유명사 + amenity=restaurant뿐', K),
    ('n4039393443', 'chinese', '결정 3: 짬뽕·사라우동은 chinese (皿うどん이 있어도 udon_soba 아님)', K),
    ('n9659915273', 'unknown', '결정 1: amenity=pub + 단서 없는 고유명사 → unknown', K),
    ('n2127007291', 'unknown', '결정 1: amenity=fast_food + 단서 없는 고유명사 → unknown (실제로는 오뎅·야키토리 가게)', 'https://www.omekanko.gr.jp/spot/33201/'),
    ('n9196700555', 'unknown', '결정 2: 고유명사 + cuisine=japanese뿐 → unknown', K),
    # 1배치 테스트(llm_test) 결과로 보강 (2026-09-24)
    ('n2382395378', 'bar', '규칙 8: 체인 HUB(영국식 펍)는 amenity=pub 규칙보다 우선', K),
    ('n884991050', 'yakiniku', 'cuisine=barbecue 는 일본에서 야키니쿠 (이름에 단서 없음)', K),
    ('n584605952', 'unknown', '규칙 6: amenity=pub 만으로는 izakaya 아님 → unknown', K),
]
rows = []
for i, (oid, lab, why, src) in enumerate(EX, 1):
    o = O[oid]
    rows.append(dict(example_id=f'e{i}', osm_id=oid, name=o['name']['name'], tags=T(o), label=lab, reason=why, verified_source=src))
G = os.path.join(ROOT, 'data/interim/gold')
with open(f'{G}/fewshot_examples.jsonl', 'w') as f:
    for r in rows: f.write(json.dumps(r, ensure_ascii=False) + '\n')
json.dump([r['osm_id'] for r in rows], open(f'{G}/fewshot_exclude_ids.json', 'w'))
with open(os.path.join(ROOT, 'prompts/fewshot_examples.txt'), 'w') as f:
    for r in rows: f.write(json.dumps({'id': r['example_id'], 'name': r['name'], 'tags': r['tags']}, ensure_ascii=False) + f" -> {r['label']}\n")
with open(os.path.join(ROOT, 'prompts/fewshot.jsonl'), 'w') as f:
    for r in rows: f.write(json.dumps({'id': r['example_id'], 'name': r['name'], 'tags': r['tags'], 'cat': r['label']}, ensure_ascii=False) + '\n')
print(f'few-shot {len(rows)}개 저장')
