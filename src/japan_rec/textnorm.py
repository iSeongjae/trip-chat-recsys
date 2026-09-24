"""가게·장소 이름 비교용 정규화."""
import re, unicodedata


def norm(s):
    return re.sub(r'[\s\W_]', '', unicodedata.normalize('NFKC', s or '').lower())


# 지점명을 떼고 남으면 안 되는 일반 단어 (이것만 남으면 가게 이름이 아님)
from .rules import words as _words
GENERIC = {norm(w) for w in _words('generic_words.json')}  # rules/generic_words.json


def name_keys(s):
    """비교 키: 이름 전체 + (띄어쓰기로 구분된 마지막 토큰이 '…店'이면) 그 지점명을 뗀 이름.
    '祭尾商店' 처럼 띄어쓰기 없는 이름은 통째로 지우지 않고, 'ラーメンSHOP 祭尾商店' 처럼 마지막 토큰이
    가게 이름인 경우도 전체 키로 매칭되게 둘 다 쓴다.
    전체 키는 2글자 이상, 지점명을 뗀 키는 3글자 이상만 ('酒場 山加商店' → '酒場' 같은 일반어 키 방지)."""
    s = unicodedata.normalize('NFKC', s or '')
    keys = [norm(s)] if len(norm(s)) >= 2 else []
    stripped = norm(re.sub(r'\s+\S*店$', '', s))
    if len(stripped) >= 3 and stripped not in keys and stripped not in GENERIC:
        keys.append(stripped)
    return keys


def same_name(a, b):
    """한쪽 키가 다른 쪽 키에 포함되면 같은 이름으로 본다."""
    return any(x in y or y in x for x in name_keys(a) for y in name_keys(b))
