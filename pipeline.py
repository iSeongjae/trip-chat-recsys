"""재현 파이프라인: 데이터 수집 → 전처리(라벨·BERT) → 아이템 DB → 평가 → 로컬 CLI 테스트.

각 단계는 저장소의 스크립트를 그대로 실행하고, 끝나면 출력 파일의 행 수·크기·sha256 을 data/_runs/manifest.json 에 남긴다.
다시 돌렸을 때 결과가 같은지는 `compare` 로 이전 기록과 비교한다.

  python3 pipeline.py list                         # 단계 목록 (태그: network=외부 API, paid=과금, long=오래 걸림, frozen=결과 고정)
  python3 pipeline.py status                       # 단계별 출력이 있는지 + 기록된 행 수
  python3 pipeline.py run all                      # 출력이 없는 단계만 차례로 (network·paid·long 은 --allow 로 허용해야 실행)
  python3 pipeline.py run preprocess evaluate --force --allow long   # 그룹·단계 지정, 출력이 있어도 다시
  python3 pipeline.py verify [--allow long]        # 외부 호출 없는 단계를 전부 다시 돌리고 이전 기록과 비교
  python3 pipeline.py compare                      # 마지막 기록을 그 전 기록들과 비교
  python3 pipeline.py snapshot                     # 지금 있는 출력을 실행 없이 기록 (비교 기준점)

환경변수(.env)가 필요한 단계는 자동으로 .env 를 읽는다. LLM 라벨(llm_labels)은 과금 + 결과 고정이라 --allow paid 로만 실행된다.
"""
import os, sys, json, time, glob, hashlib, argparse, subprocess, datetime, csv

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
RUNS = os.path.join(ROOT, 'data', '_runs')
D = lambda *p: os.path.join('data', *p)

# (이름, 그룹, 명령, 출력들, 태그, 작업 폴더, 추가 환경변수)
STAGES = [
    # ── 1. 수집 ──
    ('osm_download',    'collect',    ['bash', 'scripts/download_osm.sh'],                   [D('raw/osm_pbf')],                                   {'network', 'long'}),
    ('osm_eateries',    'collect',    [PY, 'scripts/extract_pbf.py'],                        [D('interim/osm_eateries_jp.json')],                  {'long'}),
    ('osm_attractions', 'collect',    [PY, 'scripts/extract_attractions.py'],                [D('interim/osm_attractions_jp.json')],               {'long'}),
    ('osm_stations',    'collect',    [PY, 'scripts/extract_stations.py'],                   [D('interim/osm_stations_jp.json')],                  {'long'}),
    ('wikidata',        'collect',    [PY, 'scripts/fetch_wikidata.py', '&&', PY, 'scripts/fetch_wikidata_sparql.py'], [D('raw/wikidata/entities.jsonl')], {'network', 'long'}),
    ('wikidata_link',   'collect',    [PY, 'scripts/analyze_wikidata_link.py'],              [D('interim/wikidata_popularity.json')],              {'network'}),
    ('pageviews',       'collect',    [PY, 'scripts/fetch_pageviews.py', 'ja', '12m', '&&', PY, 'scripts/fetch_pageviews.py', 'ko', '36m',
                                       '&&', PY, 'scripts/fetch_pageviews.py', 'en', '36m'],
                                      [D('raw/wikidata/pageviews_ja.jsonl'), D('raw/wikidata/pageviews_ko_36m.jsonl'), D('raw/wikidata/pageviews_en_36m.jsonl')], {'network', 'long'}),
    ('lang_indices',    'collect',    [PY, 'scripts/exploration/lang_indices_monthly.py'],   [D('interim/lang_indices_monthly.csv')],              set()),
    ('foursquare',      'collect',    [PY, 'scripts/fsq_extract_jp.py'],                     [D('raw/fsq/places_jp_2026-09-15.parquet')],          {'network', 'long'}),
    ('brands',          'collect',    [PY, 'scripts/labeling/fetch_brands_wikidata.py'],     [D('raw/wikidata/brands.json')],                      {'network'}),
    ('geoip',           'collect',    ['bash', 'scripts/download_geoip.sh'],                 [D('geoip/dbip-country-lite.mmdb')],                  {'network'}),
    # ── 2. 전처리 (음식점 라벨) ──
    ('chains',          'preprocess', [PY, 'scripts/labeling/build_chain_list.py'],          [D('interim/gold/chains_wikidata.csv')],              set()),
    ('name_rules',      'preprocess', [PY, 'scripts/labeling/name_rules.py'],                [D('interim/gold/name_rule_labels.jsonl'), D('interim/gold/unlabeled.jsonl')], set()),
    ('llm_input',       'preprocess', [PY, 'scripts/labeling/make_full_input.py'],           [D('interim/gold/llm_full/unlabeled_all.csv')],       set()),
    ('llm_labels',      'preprocess', ['bash', '-c', 'cd data/interim/gold/llm_full && ' + PY + ' ../../../../scripts/labeling/classify.py batch-submit '
                                       '--input unlabeled_all.csv --out labels.jsonl --effort low --prompt ../../../../prompts/prompt.txt '
                                       '--fewshot ../../../../prompts/fewshot.jsonl && ' + PY + ' ../../../../scripts/labeling/wait_and_collect.py'],
                                      [D('interim/gold/llm_full/labels.jsonl')],            {'network', 'paid', 'long', 'frozen'}),
    ('merge',           'preprocess', [PY, 'scripts/labeling/merge_labels.py'],              [D('interim/gold/all_labels.jsonl')],                 set()),
    ('fsq_match',       'preprocess', [PY, 'scripts/fsq_match_osm.py'],                      [D('interim/fsq/osm_fsq_match.jsonl')],               set()),
    ('bert_data',       'preprocess', [PY, 'scripts/ml/make_fsq_dataset.py'],                [D('interim/cuisine_ds_fsq_ml/train.jsonl'), D('interim/cuisine_ds_fsq_ml/test.jsonl')], set(),
                                      None, {'OUT_DS': 'cuisine_ds_fsq_ml'}),
    ('bert_train',      'preprocess', [PY, 'train_bert_multi.py'],                           [D('models/cuisine_bert_fsq_ml/test_prob.npy')],      {'long'},
                                      'scripts/ml', {'DS': 'cuisine_ds_fsq_ml', 'RUN': 'cuisine_bert_fsq_ml'}),
    ('apply',           'preprocess', [PY, 'scripts/labeling/apply_fsq.py'],                 [D('interim/gold/all_labels_fsq.jsonl')],             set()),
    # ── 3. 아이템 DB ──
    ('items',           'items',      [PY, '-m', 'japan_rec.build_items'],                   [D('processed/items_japan.json')],                    set(), 'src'),
    # ── 4. 평가 ──
    ('eval_labels',     'evaluate',   [PY, 'scripts/eval/label_quality.py'],                 [D('reports/label_quality.json')],                    set()),
    ('eval_bert',       'evaluate',   [PY, 'scripts/ml/eval_bert.py'],                       [D('reports/bert_eval.json')],                        set()),
    ('eval_rec',        'evaluate',   [PY, 'scripts/eval/sim_rec.py', '300'],                [D('processed/eval/sim_rec_days1_n8.json')],          {'long'}),
    ('tests',           'evaluate',   [PY, '-m', 'pytest', '-q', 'tests'],                   [],                                                   set()),
    # ── 5. 로컬 테스트 (Supabase 사용, dev 로그는 끝나고 지움) ──
    ('db_migrate',      'serve',      [PY, 'scripts/db/migrate.py'],                         [],                                                   {'network'}),
    ('cli',             'serve',      [PY, 'scripts/cli_chat.py', '--rules', '--start', '교토역', '--script', '라멘 먹고 싶어', '/go 1', '/chip cafe', '이번 달 명소'],
                                      [],                                                   {'network'}),
]
GROUPS = ['collect', 'preprocess', 'items', 'evaluate', 'serve']
S = {s[0]: s for s in STAGES}


def load_env():
    p = os.path.join(ROOT, '.env')
    env = dict(os.environ)
    if os.path.exists(p):
        for line in open(p):
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1); env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    env['PYTHONPATH'] = os.pathsep.join([os.path.join(ROOT, 'src'), env.get('PYTHONPATH', '')])
    return env


def stat(path):
    """출력 한 개의 요약: 행 수(가능하면)·크기·sha256(300MB 이하)."""
    p = os.path.join(ROOT, path)
    if os.path.isdir(p):
        fs = sorted(glob.glob(os.path.join(p, '*')))
        return {'files': len(fs), 'bytes': sum(os.path.getsize(f) for f in fs)}
    if not os.path.exists(p):
        return None
    out = {'bytes': os.path.getsize(p)}
    try:
        if p.endswith('.jsonl'):
            out['rows'] = sum(1 for _ in open(p, 'rb'))
        elif p.endswith('.csv'):
            out['rows'] = sum(1 for _ in open(p, 'rb')) - 1
        elif p.endswith('.json') and out['bytes'] < 400e6:
            d = json.load(open(p)); out['rows'] = len(d) if isinstance(d, (list, dict)) else None
        elif p.endswith('.parquet'):
            import duckdb; out['rows'] = duckdb.sql(f"select count(*) from '{p}'").fetchone()[0]
    except Exception as ex:
        out['rows_error'] = str(ex)[:80]
    if out['bytes'] <= 300e6:
        h = hashlib.sha256()
        with open(p, 'rb') as f:
            for chunk in iter(lambda: f.read(1 << 20), b''): h.update(chunk)
        out['sha256'] = h.hexdigest()[:16]
    return out


def manifest():
    p = os.path.join(RUNS, 'manifest.json')
    return json.load(open(p)) if os.path.exists(p) else {'runs': []}


def save_manifest(m):
    os.makedirs(RUNS, exist_ok=True)
    p = os.path.join(RUNS, 'manifest.json')
    json.dump(m, open(p + '.tmp', 'w'), ensure_ascii=False, indent=1); os.replace(p + '.tmp', p)


def expand(names):
    out = []
    for n in names:
        if n == 'all': out += [s[0] for s in STAGES]
        elif n in GROUPS: out += [s[0] for s in STAGES if s[1] == n]
        elif n in S: out.append(n)
        else: sys.exit(f'모르는 단계·그룹: {n} (list 참고)')
    return list(dict.fromkeys(out))


def run_stage(name, env, log):
    st = S[name]
    cmd, outs, tags = st[2], st[3], st[4]
    cwd = os.path.join(ROOT, st[5]) if len(st) > 5 and st[5] else ROOT
    e = dict(env, **(st[6] if len(st) > 6 and st[6] else {}))
    shell = '&&' in cmd
    line = ' '.join(cmd) if shell else cmd
    t0 = time.time()
    log.write(f'\n===== {name} {datetime.datetime.now().isoformat()} =====\n'); log.flush()
    p = subprocess.run(line, cwd=cwd, env=e, shell=shell, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log.write(p.stdout); log.flush()
    tail = '\n'.join(l for l in p.stdout.strip().splitlines()[-4:])
    return p.returncode, time.time() - t0, tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('cmd', choices=['list', 'status', 'run', 'verify', 'compare', 'snapshot'])
    ap.add_argument('stages', nargs='*')
    ap.add_argument('--force', action='store_true', help='출력이 있어도 다시 실행')
    ap.add_argument('--allow', default='', help='network,paid,long 중 허용할 태그')
    a = ap.parse_args()
    allow = {x for x in a.allow.split(',') if x}

    if a.cmd == 'list':
        for g in GROUPS:
            print(f'[{g}]')
            for s in STAGES:
                if s[1] == g: print(f"  {s[0]:16} {','.join(sorted(s[4])) or '-':28} → {', '.join(s[3]) or '(출력 없음)'}")
        return 0

    m = manifest()
    last = m['runs'][-1]['stages'] if m['runs'] else {}
    if a.cmd == 'status':
        for s in STAGES:
            outs = [stat(o) for o in s[3]]
            ok = all(outs) if outs else None
            rec = last.get(s[0], {})
            rows = [ (o or {}).get('rows', (o or {}).get('files')) for o in outs]
            print(f"{'✓' if ok else ('·' if ok is None else '✗')} {s[0]:16} 출력 {rows}  마지막 실행 {rec.get('when', '-')} {rec.get('status', '')}")
        return 0

    if a.cmd == 'snapshot':   # 지금 있는 출력을 실행 없이 기록 (비교 기준점)
        ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        run = {'started': ts, 'cmd': 'snapshot', 'stages': {}}
        for s in STAGES:
            if s[3] and all(stat(o) for o in s[3]):
                run['stages'][s[0]] = {'when': ts, 'status': 'snapshot', 'outputs': {o: stat(o) for o in s[3]}}
        m['runs'].append(run); save_manifest(m)
        print(f"기록 {len(run['stages'])}개 단계 → data/_runs/manifest.json"); return 0

    if a.cmd == 'compare':
        if len(m['runs']) < 2: print('기록이 2개 미만'); return 0
        prev, cur = {}, {}
        for r in m['runs'][:-1]:
            for k, v in r['stages'].items(): prev[k] = v
        cur = m['runs'][-1]['stages']
        return compare(prev, cur)

    names = expand(a.stages or ['all'])
    if a.cmd == 'verify':
        names = [n for n in expand(['all']) if not (S[n][4] - allow) & {'network', 'paid', 'frozen', 'long'}]
        a.force = True
    env = load_env()
    os.makedirs(RUNS, exist_ok=True)
    ts = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    run = {'started': ts, 'cmd': ' '.join(sys.argv[1:]), 'stages': {}}
    code = 0
    with open(os.path.join(RUNS, f'run-{ts}.log'), 'w') as log:
        for n in names:
            st = S[n]
            blocked = st[4] - allow
            if blocked & {'network', 'paid', 'long', 'frozen'}:
                have = all(stat(o) for o in st[3]) if st[3] else False
                print(f"· {n:16} 건너뜀 ({','.join(sorted(blocked))} — --allow 필요){' / 기존 출력 있음' if have else ' / ⚠ 출력 없음'}")
                continue
            if not a.force and st[3] and all(stat(o) for o in st[3]):
                print(f'· {n:16} 출력 있음 → 건너뜀 (--force 로 다시)'); continue
            print(f'▶ {n:16} 실행 중…', flush=True)
            rc, secs, tail = run_stage(n, env, log)
            outs = {o: stat(o) for o in st[3]}
            run['stages'][n] = {'when': ts, 'status': 'ok' if rc == 0 else f'실패({rc})', 'secs': round(secs), 'outputs': outs}
            m_now = manifest(); m_now['runs'] = [r for r in m_now['runs'] if r.get('started') != ts] + [run]; save_manifest(m_now)
            print(f"  {'✓' if rc == 0 else '✗'} {secs:.0f}초  {tail.splitlines()[-1][:110] if tail else ''}")
            if rc != 0:
                print(f'  실패 — 로그: data/_runs/run-{ts}.log\n{tail}'); code = 1; break
    if a.cmd == 'verify':
        compare(last, run['stages'])
    return code


def compare(prev, cur):
    print('\n== 이전 기록과 비교 (행 수 / sha256) ==')
    same = diff = 0
    for n, r in cur.items():
        for o, v in (r.get('outputs') or {}).items():
            pv = ((prev.get(n) or {}).get('outputs') or {}).get(o)
            if not v or not pv:
                print(f'  {o}: 비교할 이전 기록 없음'); continue
            if v.get('sha256') and v.get('sha256') == pv.get('sha256'):
                same += 1; continue
            if v.get('rows') == pv.get('rows'):
                print(f"  ≈ {o}: 행 수 같음 {v.get('rows')} (내용 일부 다름)"); diff += 1
            else:
                print(f"  ≠ {o}: 행 {pv.get('rows')} → {v.get('rows')}"); diff += 1
    print(f'  바이트까지 같음 {same}개, 다름 {diff}개')
    return 0


if __name__ == '__main__':
    sys.exit(main())
