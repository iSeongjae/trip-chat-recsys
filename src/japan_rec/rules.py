"""규칙 목록 로더. 목록은 프로젝트 루트의 rules/*.json 에서 관리하고, 코드는 읽어서 적용만 한다.
(CSV 와 속도 비교 결과 JSON 이 더 빨라 JSON 사용, 2026-09-24)"""
import json, os
RULES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'rules')


def load(name):
    with open(os.path.join(RULES_DIR, name), encoding='utf-8') as f:
        return json.load(f)


def patterns(name):
    """priority 순 (category, pattern) 목록."""
    return [(r['category'], r['pattern']) for r in sorted(load(name), key=lambda r: int(r['priority']))]


def words(name, col='word'):
    return [r[col] for r in load(name) if r[col]]
