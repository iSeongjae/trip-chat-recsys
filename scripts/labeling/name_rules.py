"""few-shot 프롬프트의 25개 카테고리 기준, 가게 이름만으로 붙이는 규칙 라벨 (정답 라벨 1단계).
우선순위: 체인 목록(규칙 8) → 구체적 음식 → 술집 계열 → 카페·디저트 → 넓은 분류. 라멘은 중식보다(규칙 2), 야키토리는 이자카야보다(규칙 4) 먼저.
여러 규칙이 걸리면 matched 에 모두 남겨 검토 대상으로 표시.
출력: data/interim/gold/name_rule_labels.jsonl (라벨 붙은 곳), unlabeled.jsonl (남은 곳)"""
import collections, json, os, re, unicodedata
R = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'data')

# 목록은 rules/*.json 에서 관리 (체인: rules/chains.json, 키워드: rules/keyword_rules.json)
import sys as _sys
_sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src'))
from japan_rec.rules import load as _load, patterns as _patterns
CHAINS, START_ONLY = {}, set()
for _r in _load('chains.json'):
    CHAINS.setdefault(_r['category'], []).append(_r['name'])
    if _r['start_only'] == '1': START_ONLY.add(_r['name'])
CHAIN_SOURCE = 'rules/chains.json (Claude knowledge 2026-09-24)'  # 체인 규칙 라벨의 출처
KEYWORDS = _patterns('keyword_rules.json')  # (카테고리, 정규식), priority 순
RX = [(c, re.compile(p, re.I)) for c, p in KEYWORDS]

def _chain_rx(w):
    """체인 이름은 이름 시작이나 공백·・ 뒤에 있고, 뒤는 끝·공백·괄호 또는 '…店' 으로 끝날 때만 (小松屋·松屋食堂 제외)."""
    head = r'^' if unicodedata.normalize('NFKC', w) in START_ONLY or w in START_ONLY else r'(?:^|[\s・])'
    return re.compile(rf'{head}{re.escape(unicodedata.normalize("NFKC", w))}(?=$|[\s(（]|\S*店$)', re.I)
CHAIN_RX = [(c, _chain_rx(w), unicodedata.normalize('NFKC', w)) for c, ws in CHAINS.items() for w in ws]


# 체인 목록 (build_chain_list.py 출력). QID → (카테고리, 출처), 브랜드 이름 → 카테고리
CHAIN_CSV = os.path.join(R, 'interim/gold/chains_wikidata.csv')
BRAND_QID, BRAND_NAME_RX = {}, []
if os.path.exists(CHAIN_CSV):
    import csv
    for r in csv.DictReader(open(CHAIN_CSV, encoding='utf-8')):
        if r['cat'] and r['conf'] in ('high', 'majority', 'single', 'manual'):
            BRAND_QID[r['qid']] = (r['cat'], r['source'] or 'code: A/B/C vote')
            nm = unicodedata.normalize('NFKC', r['brand_tag']).strip()
            if len(nm) >= 2:  # 브랜드 이름은 이름 맨 앞에 올 때만 (흔한 이름 오탐 방지)
                BRAND_NAME_RX.append((r['cat'], re.compile(rf'^{re.escape(nm)}(?=$|[\s(（]|\S*店$)', re.I), r['qid']))


def label_brand(tags, name):
    """brand:wikidata QID → 카테고리, 없으면 브랜드 이름 매칭. (label, rule, source) 또는 None."""
    for q in (tags.get('brand:wikidata') or '').split(';'):
        if q.strip() in BRAND_QID:
            c, src = BRAND_QID[q.strip()]; return c, 'brand_qid', src
    n = unicodedata.normalize('NFKC', name or '')
    for c, rx, q in BRAND_NAME_RX:
        m = rx.search(n)
        if m:
            rest = n[:m.start()] + ' ' + n[m.end():]
            kw = [k for k, x in RX if x.search(rest)]
            if kw and c not in kw:
                return None  # 브랜드 이름 밖에 다른 음식 키워드 → 키워드 우선 (예: '松屋そば店')
            return c, 'brand_name', f'{BRAND_QID[q][1]} via {q}'
    return None


def label(name, use_brands=True):
    n = unicodedata.normalize('NFKC', name or '')
    hits = [(c, w) for c, rx, w in CHAIN_RX if rx.search(n)]
    chain = list(dict.fromkeys(c for c, _ in hits))
    kw = [c for c, rx in RX if rx.search(n)]
    rest = n
    for _, w in hits:
        rest = rest.replace(w, ' ')
    kw_rest = [c for c, rx in RX if rx.search(rest)]  # 체인 이름을 뺀 나머지에 있는 키워드
    if chain and kw_rest and not set(chain) & set(kw_rest):
        chain = []  # 체인 이름 밖에 다른 음식 키워드가 있으면 키워드 우선 (예: 'すし処 天狗', 'ウエスト カフェ'). '韓丼' 의 丼 은 체인 이름 안이라 무시
    matched = list(dict.fromkeys(chain + kw))
    if not matched:
        return None, [], None
    return matched[0], matched, 'chain' if chain else 'keyword'

def tag_str(t):
    return ' '.join(f'{k}={v}' for k, v in t.items())

if __name__ == '__main__':
    FUK = (33.45, 33.72, 130.25, 130.60)
    O = [o for o in json.load(open(f'{R}/interim/osm_eateries_jp.json')) if o['name'].get('name')]
    lab = open(f'{R}/interim/gold/name_rule_labels.jsonl', 'w'); rest = open(f'{R}/interim/gold/unlabeled.jsonl', 'w')
    cnt, src, fuk = collections.Counter(), collections.Counter(), collections.Counter()
    multi = 0
    for o in O:
        b = label_brand(o['tags'], o['name']['name'])
        if b:
            l, how, bsrc = b; m = [l]
        else:
            l, m, how = label(o['name']['name']); bsrc = None
        rec = dict(id=o['osm_id'], name=o['name']['name'], tags=tag_str(o['tags']), lat=o['lat'], lon=o['lon'])
        infk = FUK[0] <= o['lat'] <= FUK[1] and FUK[2] <= o['lon'] <= FUK[3]
        if l:
            rec.update(label=l, matched=m, rule=how, source=bsrc or (CHAIN_SOURCE if how == 'chain' else 'code: keyword rule')); lab.write(json.dumps(rec, ensure_ascii=False) + '\n')
            cnt[l] += 1; src[how] += 1; multi += len(m) > 1; fuk['labeled'] += infk
        else:
            rest.write(json.dumps(rec, ensure_ascii=False) + '\n'); fuk['rest'] += infk
    n = len(O); L = sum(cnt.values())
    print(f'[전국] 이름 있는 음식점 {n:,} | 규칙 라벨 {L:,} ({L/n:.1%}) — 브랜드QID {src["brand_qid"]:,}, 브랜드이름 {src["brand_name"]:,}, 체인 {src["chain"]:,}, 키워드 {src["keyword"]:,} | 여러 규칙 걸림 {multi:,} | 남음 {n-L:,} ({(n-L)/n:.1%})')
    print(f'[후쿠오카] 규칙 라벨 {fuk["labeled"]:,} | 남음 {fuk["rest"]:,}')
    print('카테고리별:', cnt.most_common())
