"""Wikidata 브랜드 항목에 음식 종류 정보가 얼마나 비어 있는지 집계 (brands.json 기준)."""
import json, os, re
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..')
B = json.load(open(os.path.join(ROOT, 'data/raw/wikidata/brands.json'))); n = len(B)
food = re.compile(r'ラーメン|うどん|そば|寿司|すし|鮨|焼き?鳥|とんかつ|天ぷら|天丼|お好み|たこ焼|焼肉|しゃぶ|カレー|牛丼|丼|ステーキ|ハンバーグ|ハンバーガー|中華|餃子|韓国|イタリア|ピザ|パスタ|居酒屋|コーヒー|珈琲|喫茶|カフェ|ドーナツ|菓子|パン|ramen|udon|soba|sushi|yakitori|tempura|curry|burger|pizza|pasta|coffee|café|cafe|donut|bakery|steak|izakaya|pub|italian|chinese|korean|seafood|ice cream|doughnut|tea', re.I)
txt = lambda v, *f: ' '.join(v[k] for k in f)
print(f'브랜드 {n}')
print('  P2012 있음', sum(1 for v in B.values() if v['cuisine']))
print('  P31 에 음식 종류', sum(1 for v in B.values() if food.search(v['p31'])))
print('  설명 있음', sum(1 for v in B.values() if v['desc_ja'] or v['desc_en']),
      '→ 음식 종류 드러남', sum(1 for v in B.values() if food.search(txt(v, 'desc_ja', 'desc_en'))))
anyf = sum(1 for v in B.values() if food.search(txt(v, 'cuisine', 'desc_ja', 'desc_en', 'p31')))
print(f'  어디서든 음식 종류 드러남 {anyf} | 전혀 안 드러남 {n - anyf}')
print('  운영 회사 항목으로 보임', sum(1 for v in B.values() if re.search(r'株式会社|ホールディングス|商事|企業|会社|company|corporation|holdings|business|public company', txt(v, 'ja', 'desc_ja', 'desc_en', 'p31'), re.I) and not food.search(txt(v, 'desc_ja', 'desc_en', 'p31'))))
