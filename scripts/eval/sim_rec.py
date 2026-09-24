"""추천 성능 오프라인 시뮬레이션 (LLM 없음, 무료·재현 가능).

가상 사용자: 숨은 취향(하위분류별 선호도, 좋아하는 것 3개) + 하루 동선(7턴).
시작 위치: 일본 전역의 유명 관광지(인기도 ≥0.5) 중 무작위. 매 턴 다음 카테고리·반경 1km(후보 5개 미만이면 2km).
식사 턴의 30%는 좋아하는 음식을 직접 말함(include_sub). 사용자는 보여준 5곳 중 선호도+잡음이 가장 높은 곳을
고르되, 기준(ACCEPT) 미만이면 아무것도 안 고름(목록 거절 → 보여준 곳 skip). 고르면 그곳으로 이동.

비교: ours(학습하는 추천), no_learn(학습 없음 = 인기도+거리), distance(가까운 순), random.
지표: 성공률(고른 턴 비율), 턴 4~7 성공률(개인화 효과), 고른 곳 순위, 목록 다양성(하위분류 수), 후보 부족률, 종류 조건 준수율.
실행: [DAYS=3] [METHODS=ours,no_learn] python3 scripts/eval/sim_rec.py [사용자 수=300]
"""
import os, sys, json, random, collections, copy
import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..')
sys.path.insert(0, os.path.join(ROOT, 'src'))
from japan_rec import recommender as rec, candidates as cg
from japan_rec.categories import resolve, matches

N_USERS = int(sys.argv[1]) if len(sys.argv) > 1 else 300
PLAN = ['meal', 'sight', 'cafe', 'walk', 'meal', 'shop', 'bar'] * int(os.environ.get('DAYS', 1))
FOOD = {'meal', 'cafe', 'bar'}
ACCEPT = 0.45            # 이 선호도 미만만 보이면 거절
NOISE = 0.1
ASK_RATE = 0.3           # 식사·술 턴에서 좋아하는 종류를 직접 말하는 비율
N_SHOW = int(os.environ.get('N_SHOW', rec.N_SHOW))  # 추천 목록 길이
I = rec.items()
SUBS = collections.defaultdict(collections.Counter)
for it in I.values():
    SUBS[it['category']][it['sub']] += 1
UNKNOWN_SUB = {'식당', '카페·디저트', '술집'}
STARTS = [it for it in I.values() if it['category'] in ('sight', 'walk') and it['popularity'] >= 0.5]


def make_user(rng):
    taste = {}
    for cat, cnt in SUBS.items():
        subs = [s for s, n in cnt.items() if n >= 30 and s not in UNKNOWN_SUB]
        fav = rng.sample(subs, min(3, len(subs)))
        for s in subs:
            taste[(cat, s)] = rng.uniform(0.0, 0.3)
        for s, w in zip(fav, (1.0, 0.8, 0.6)):
            taste[(cat, s)] = w
        for s in UNKNOWN_SUB:
            taste[(cat, s)] = 0.35  # 종류 모르는 가게: 그저 그런 기대
    return taste


def rank(method, cands, user, radius, rng):
    if method in ('ours', 'no_learn'):
        u = user if method == 'ours' else rec.new_user()
        return [x['id'] for x in rec.recommend(cands, u, radius, n=N_SHOW, seed=rng.randrange(10**6))]
    if method == 'distance':
        return [c[0] for c in sorted(cands, key=lambda c: c[1])[:N_SHOW]]
    return [c[0] for c in rng.sample(cands, min(N_SHOW, len(cands)))]


def run(method, seed):
    rng = random.Random(seed)
    taste = make_user(rng)
    start = rng.choice(STARTS)
    user = rec.new_user()
    cur, visited = {'lat': start['lat'], 'lon': start['lon']}, []
    out = []
    for t, cat in enumerate(PLAN):
        c = {'next_category': cat, 'max_distance_km': 1.0}
        if cat in ('meal', 'bar') and rng.random() < ASK_RATE:
            fav = max((s for (k, s) in taste if k == cat), key=lambda s: taste[(cat, s)])
            c['include_sub'] = [fav]
        q = {'constraints': c, 'context': {'current': cur, 'visited': visited}}
        cands, _, _ = cg.generate(q, I)
        short = len(cands) < N_SHOW
        if short:
            c['max_distance_km'] = 2.0
            cands, _, _ = cg.generate(q, I)
        if not cands:
            out.append(dict(t=t, cat=cat, ok=False, rank=None, short=True, div=0, comply=None, asked='include_sub' in c)); continue
        shown = rank(method, cands, user, c['max_distance_km'], rng)
        util = [taste.get((cat, I[i]['sub']), 0.1) + rng.gauss(0, NOISE) for i in shown]
        best = int(np.argmax(util))
        ok = util[best] >= ACCEPT
        comply = None
        if 'include_sub' in c:
            r = resolve(c['include_sub']); comply = np.mean([matches(I[i], r) for i in shown])
        out.append(dict(t=t, cat=cat, ok=ok, rank=best + 1 if ok else None, short=short, n_shown=len(shown),
                        div=len({I[i]['sub'] for i in shown}), comply=comply, asked='include_sub' in c))
        if method == 'ours':
            if ok:
                for k, i in enumerate(shown):
                    if k != best: rec.log_feedback(user, i, 'skip', position=k)
                rec.log_feedback(user, shown[best], 'select')
            else:
                rec.log_feedback(user, shown[0], 'skip', position=0)  # 목록 거절은 반응 1회로 (TODO 반영)
        if ok:
            it = I[shown[best]]
            cur = {'lat': it['lat'], 'lon': it['lon']}; visited.append(it['id'])
    return out


def summarize(rows):
    ok = np.array([r['ok'] for r in rows]); late = np.array([r['ok'] for r in rows if r['t'] >= 3])
    by_day = [np.mean([r['ok'] for r in rows if r['t'] // 7 == d]) for d in range(len(PLAN) // 7)]
    food = np.array([r['ok'] for r in rows if r['cat'] in FOOD and not r['asked']])
    ranks = [r['rank'] for r in rows if r['rank']]
    comply = [r['comply'] for r in rows if r['comply'] is not None]
    return dict(성공률=f'{ok.mean():.1%}', 턴4_7=f'{late.mean():.1%}', 음식_종류안말함=f'{food.mean():.1%}',
                평균순위=f'{np.mean(ranks):.2f}', 다양성=f"{np.mean([r['div'] for r in rows if r['div']]):.2f}",
                후보부족=f"{np.mean([r['short'] for r in rows]):.1%}", 평균노출=f"{np.mean([r.get('n_shown', 0) for r in rows]):.2f}", 일별성공=[f'{x:.1%}' for x in by_day], 조건준수=f'{np.mean(comply):.1%}' if comply else '-')


if __name__ == '__main__':
    res = {}
    for m in os.environ.get('METHODS', 'ours,no_learn,distance,random').split(','):
        rows = [r for s in range(N_USERS) for r in run(m, s)]
        res[m] = summarize(rows)
        print(m, res[m], flush=True)
    os.makedirs(os.path.join(ROOT, 'data/processed/eval'), exist_ok=True)
    json.dump(res, open(os.path.join(ROOT, f"data/processed/eval/sim_rec_days{os.environ.get('DAYS', 1)}_n{N_SHOW}.json"), 'w'), ensure_ascii=False, indent=1)
