"""일본어 이름 → 한글 표기 (고유명사는 소리대로, 흔한 일반 단어는 한국어로). pykakasi 로 읽기를 얻고 가나→한글 표로 바꾼다.

표기 규칙(국립국어원 일본어 표기법을 단순화):
- 단어 첫머리 か·た·ちゃ 행은 예사소리(가·다·자), 가운데·끝은 거센소리(카·타·차). 가타카나 외래어는 첫머리도 거센소리(카페, 케이크)
- つ → 쓰, ん → ㄴ 받침, っ → ㅅ 받침, 장음(ー, 오·우단 뒤 う)은 적지 않음 (とうきょう → 도쿄)
읽기는 사전 기반이라 가게 이름 한자는 틀릴 수 있음 → 화면에는 일본어 원문을 함께 보여 준다.
"""
import re, unicodedata
from functools import lru_cache

WORDS = {  # 일반 단어: 소리 대신 한국어 (가게 이름에 자주 나오는 것)
    'ラーメン': '라멘', 'らーめん': '라멘', '拉麺': '라멘', '中華そば': '추카소바', '食堂': '식당', '居酒屋': '이자카야', '寿司': '스시', '鮨': '스시',
    '本店': '본점', '支店': '지점', '駅前': '역앞', '駅': '역', '珈琲': '커피', 'コーヒー': '커피', 'カフェ': '카페', '喫茶': '킷사',
    '酒場': '사카바', '焼肉': '야키니쿠', '焼き肉': '야키니쿠', '焼鳥': '야키토리', '焼き鳥': '야키토리', 'うどん': '우동', 'そば': '소바', '蕎麦': '소바',
    '神社': '신사', '公園': '공원', '城跡': '성터', 'お食事処': '식당', '城': '성', '美術館': '미술관', '博物館': '박물관', '温泉': '온천', '市場': '시장', '商店街': '상점가',
    'スターバックス': '스타벅스', 'マクドナルド': '맥도날드', 'ファミリーマート': '패밀리마트', 'セブンイレブン': '세븐일레븐', 'ローソン': '로손',
    'ドトール': '도토루', 'ミスタードーナツ': '미스터도넛', 'ケンタッキー': '켄터키', 'サブウェイ': '서브웨이', 'タリーズ': '탈리스', 'ドン・キホーテ': '돈키호테',
    'ユニクロ': '유니클로', '無印良品': '무인양품', 'ダイソー': '다이소', 'すき家': '스키야', '吉野家': '요시노야', 'モスバーガー': '모스버거',
    'ベーカリー': '베이커리', 'パン': '빵', 'ケーキ': '케이크', 'バー': '바', 'ステーキ': '스테이크', 'カレー': '카레', '餃子': '교자', '定食': '정식',
}
V = {'a': 'ㅏ', 'i': 'ㅣ', 'u': 'ㅜ', 'e': 'ㅔ', 'o': 'ㅗ', 'ya': 'ㅑ', 'yu': 'ㅠ', 'yo': 'ㅛ', 'wa': 'ㅘ', 'we': 'ㅞ', 'wi': 'ㅟ', 'wo': 'ㅝ', 'ye': 'ㅖ'}
# 가나 → (자음 첫머리, 자음 가운데, 모음). 자음: ㅇ ㄱ ㅋ ㄷ ㅌ ㅈ ㅊ ㅅ ㅆ ㄴ ㅎ ㅂ ㅍ ㅁ ㄹ
K = {}
def _row(kana, c0, c1, vowels='aiueo'):
    for k, v in zip(kana, vowels): K[k] = (c0, c1, v)
_row('あいうえお', 'ㅇ', 'ㅇ'); _row('かきくけこ', 'ㄱ', 'ㅋ'); _row('がぎぐげご', 'ㄱ', 'ㄱ'); _row('さしすせそ', 'ㅅ', 'ㅅ'); _row('ざじずぜぞ', 'ㅈ', 'ㅈ')
_row('たてと', 'ㄷ', 'ㅌ', 'aeo'); _row('だでど', 'ㄷ', 'ㄷ', 'aeo'); K['ち'] = ('ㅈ', 'ㅊ', 'i'); K['つ'] = ('ㅆ', 'ㅆ', 'eu'); K['ぢ'] = ('ㅈ', 'ㅈ', 'i'); K['づ'] = ('ㅈ', 'ㅈ', 'eu')
_row('なにぬねの', 'ㄴ', 'ㄴ'); _row('はひふへほ', 'ㅎ', 'ㅎ'); _row('ばびぶべぼ', 'ㅂ', 'ㅂ'); _row('ぱぴぷぺぽ', 'ㅍ', 'ㅍ'); _row('まみむめも', 'ㅁ', 'ㅁ')
_row('やゆよ', 'ㅇ', 'ㅇ', ['ya', 'yu', 'yo']); _row('らりるれろ', 'ㄹ', 'ㄹ'); K['わ'] = ('ㅇ', 'ㅇ', 'wa'); K['を'] = ('ㅇ', 'ㅇ', 'o'); K['ゔ'] = ('ㅂ', 'ㅂ', 'u')
K['す'] = ('ㅅ', 'ㅅ', 'eu'); K['ず'] = ('ㅈ', 'ㅈ', 'eu')   # 스·즈
SMALL = {'ゃ': 'ya', 'ゅ': 'yu', 'ょ': 'yo', 'ぁ': 'a', 'ぃ': 'i', 'ぅ': 'u', 'ぇ': 'e', 'ぉ': 'o'}
CHO = 'ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ'; JUNG = 'ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ'; JONG = ['', 'ㄱ', 'ㄲ', 'ㄳ', 'ㄴ', 'ㄵ', 'ㄶ', 'ㄷ', 'ㄹ', 'ㄺ', 'ㄻ', 'ㄼ', 'ㄽ', 'ㄾ', 'ㄿ', 'ㅀ', 'ㅁ', 'ㅂ', 'ㅄ', 'ㅅ', 'ㅆ', 'ㅇ', 'ㅈ', 'ㅊ', 'ㅋ', 'ㅌ', 'ㅍ', 'ㅎ']


def _syl(c, v, j=''):
    v = {'eu': 'ㅡ'}.get(v, V.get(v, v))
    return chr(0xAC00 + (CHO.index(c) * 21 + JUNG.index(v)) * 28 + JONG.index(j))


def _add_final(out, j):
    if out and '가' <= out[-1] <= '힣':
        code = ord(out[-1]) - 0xAC00
        if code % 28 == 0: out[-1] = chr(ord(out[-1]) + JONG.index(j)); return
    out.append({'ㄴ': 'ㄴ', 'ㅅ': 'ㅅ'}[j])


def kana_to_hangul(hira, loan=False):
    out, i, n = [], 0, len(hira)
    prev_v = ''
    while i < n:
        ch = hira[i]
        if ch == 'ん': _add_final(out, 'ㄴ'); i += 1; continue
        if ch == 'っ': _add_final(out, 'ㅅ') if i + 1 < n else None; i += 1; continue
        if ch == 'ー': i += 1; continue
        if (ch == 'う' and prev_v in ('o', 'u', 'yo', 'yu') or ch == 'お' and prev_v in ('o', 'yo')) and i > 0: i += 1; continue   # 장음 (とう·おお)
        if ch not in K:
            out.append(ch); i += 1; prev_v = ''; continue
        c0, c1, v = K[ch]
        c = c1 if (out or loan) else c0
        nxt = hira[i + 1] if i + 1 < n else ''
        if nxt in SMALL:
            sv = SMALL[nxt]
            if sv[0] == 'y':                                   # 요음
                v = sv[1:] if ch in 'じぢち' else sv            # じゃ 자, ちゃ 차 / きゃ 캬, しゃ 샤
            elif ch == 'ふ': c, v = 'ㅍ', sv                   # ふぁ 파, ふぇ 페
            elif ch == 'う': v = {'i': 'wi', 'e': 'we', 'o': 'wo'}.get(sv, sv)
            elif ch in 'しち' and sv == 'e': v = 'ye' if ch == 'し' else 'e'   # しぇ 셰, ちぇ 체
            elif ch in 'てで' and sv in 'iu': v = sv           # てぃ 티, でぃ 디
            else: v = sv
            i += 1
        out.append(_syl(c, v)); prev_v = v; i += 1
    return ''.join(out)


def _kata2hira(s):
    return ''.join(chr(ord(c) - 0x60) if 'ァ' <= c <= 'ヶ' else c for c in s)


_kks = None


def _kakasi():
    global _kks
    if _kks is None:
        import pykakasi
        _kks = pykakasi.kakasi()
    return _kks


HANGUL = re.compile('[가-힣]')
JA = re.compile('[぀-ヿ一-鿿]')


@lru_cache(maxsize=200000)
def to_korean(name):
    """일본어가 섞인 이름 → 한글 표기. 일본어가 없으면(영문 등) 그대로."""
    name = unicodedata.normalize('NFKC', name or '').strip()
    if not JA.search(name):
        return name
    tail = ''
    if name.endswith('店') and not re.search('(本|支|商)店$', name):   # 지점명 '…店' → '…점' (コメダ珈琲店 → 코메다 커피점)
        name, tail = name[:-1], '점'
    # 일반 단어를 먼저 치환 표시 (긴 것부터)
    parts = [name]
    for w in sorted(WORDS, key=len, reverse=True):
        parts = [p for s in parts for p in ([s] if isinstance(s, tuple) else _split(s, w))]
    out = []
    for p in parts:
        if isinstance(p, tuple):
            out.append(p[1]); continue
        try:
            segs = _kakasi().convert(p)
        except Exception:   # pykakasi 가 드물게 실패하는 문자열 → 원문 유지
            out.append(p); continue
        for seg in segs:
            orig, hira = seg['orig'], seg['hira']
            if not JA.search(orig):
                out.append(orig); continue
            loan = bool(re.fullmatch('[゠-ヿー・]+', orig))
            out.append(kana_to_hangul(_kata2hira(hira), loan=loan))
    s = ''.join(out)
    s = re.sub(r'\s+', ' ', s.replace('・', ' ')).strip() + tail
    return re.sub(r' (역|성|신사|점)(?= |$)', r'\1', s)   # 교토 역 → 교토역


def _split(s, w):
    if w not in s: return [s]
    out = []
    for k, piece in enumerate(s.split(w)):
        if k: out.append((w, ' ' + WORDS[w] + ' '))
        if piece: out.append(piece)
    return out
