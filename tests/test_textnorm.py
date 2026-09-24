import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from japan_rec.textnorm import same_name


def test_no_space_name_is_not_erased():
    assert same_name('祭尾商店', 'ラーメンSHOP 祭尾商店')


def test_branch_suffix_stripped():
    assert same_name('一蘭 キャナルシティ博多店', '一蘭')
    assert same_name('因幡うどん 渡辺通店', '因幡うどん')


def test_generic_word_after_strip_does_not_match():
    assert not same_name('大衆酒場 大桝', '酒場 山加商店')


def test_different_names():
    assert not same_name('スターバックス', 'ドトール')


def test_generic_word_left_after_strip_is_ignored():
    assert not same_name('居酒屋 ごちや大ホール天神西通り店', '居酒屋 天神商店 天神店')
