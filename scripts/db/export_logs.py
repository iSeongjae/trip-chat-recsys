"""Supabase 행동 로그(기본: reaction_logs) → 로컬 파일 증분 내보내기.

설정: config/export_logs.json (테이블·배치 크기·재시도·지연 등). 진행 위치(커서)는 state_file 에 저장되어,
다음 실행은 마지막으로 내보낸 행 바로 뒤부터 이어간다.

출력: {out_dir}/{table}/date=YYYY-MM-DD/part-{첫커서}-{끝커서}.jsonl.gz   (한 줄 = 한 행, JSON)
      {out_dir}/_manifest.jsonl  (파일별 행 수·sha256·커서 범위),  {out_dir}/_export.log

장애 대처
- 연결 끊김·타임아웃: 지수 백오프로 재연결 후 같은 커서부터 다시 (config.retry). 비밀번호·권한 오류는 재시도 없이 바로 실패
- 중간에 죽음: 파일을 먼저 원자적으로 쓰고(임시 파일 → fsync → rename) 그다음 커서를 저장한다.
  커서 저장 전에 죽으면 다음 실행이 같은 범위를 다시 읽어 **같은 파일 이름으로 덮어쓴다** → 중복·누락 없음
- 커밋이 늦게 끝난 행을 놓치지 않게, 만든 지 safety_lag_seconds 가 지난 행만 내보낸다
- 동시 실행 방지: 잠금 파일. 커서 파일이 깨지면 .bak 로 복구하고, 둘 다 없으면 처음부터 다시 받지 않고 멈춘다
- 파일을 쓴 뒤 다시 읽어 행 수를 확인한다

사용
  python3 scripts/db/export_logs.py                 # 설정에서 enabled 인 테이블 모두
  python3 scripts/db/export_logs.py --table turn_logs
  python3 scripts/db/export_logs.py --status        # 테이블별 진행 상황
  python3 scripts/db/export_logs.py --dry-run       # 몇 행이 남았는지만
  python3 scripts/db/export_logs.py --reset reaction_logs --yes   # 커서 초기화 (기존 파일은 직접 지울 것)
"""
import os, sys, json, gzip, time, fcntl, hashlib, logging, argparse, datetime, decimal, uuid, re
sys.path.insert(0, os.path.dirname(__file__))
import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from pg import connect, backoff, fatal, RETRYABLE, ROOT

p = argparse.ArgumentParser()
p.add_argument('--config', default=os.path.join(ROOT, 'config', 'export_logs.json'))
p.add_argument('--table', action='append', help='이 테이블만 (여러 번 가능)')
p.add_argument('--status', action='store_true')
p.add_argument('--dry-run', action='store_true')
p.add_argument('--reset')
p.add_argument('--yes', action='store_true')
p.add_argument('--max-batches', type=int)
args = p.parse_args()

CFG = json.load(open(args.config))
OUT = os.path.join(ROOT, CFG['out_dir'])
STATE = os.path.join(ROOT, CFG['state_file'])
os.makedirs(OUT, exist_ok=True)
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                    handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(OUT, '_export.log'))])
log = logging.getLogger('export')


# ───────── 파일 유틸 (원자적 쓰기) ─────────
def atomic_write(path, data: bytes):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f'{path}.tmp-{os.getpid()}'
    with open(tmp, 'wb') as f:
        f.write(data); f.flush(); os.fsync(f.fileno())
    os.replace(tmp, path)


def jdefault(o):
    if isinstance(o, (datetime.datetime, datetime.date)): return o.isoformat()
    if isinstance(o, uuid.UUID): return str(o)
    if isinstance(o, decimal.Decimal): return float(o)
    raise TypeError(type(o))


def load_state():
    for path in (STATE, STATE + '.bak'):
        if os.path.exists(path):
            try:
                return json.load(open(path))
            except json.JSONDecodeError:
                log.error('커서 파일이 깨짐: %s → 백업으로 시도', path)
    if os.path.exists(STATE) or os.path.exists(STATE + '.bak'):
        sys.exit('커서 파일과 백업이 모두 깨짐. 처음부터 다시 받으면 중복이 생기므로 멈춤 — _manifest.jsonl 의 마지막 커서로 복구할 것')
    return {'version': 1, 'tables': {}}


def save_state(st):
    if os.path.exists(STATE):
        os.replace(STATE, STATE + '.bak')
    atomic_write(STATE, json.dumps(st, ensure_ascii=False, indent=1, default=jdefault).encode())


def slug(vals):
    s = '_'.join(re.sub(r'[^0-9A-Za-z]', '', str(v))[:20] for v in vals)
    return s or 'x'


# ───────── 한 배치 읽기 (재시도) ─────────
class Reader:
    def __init__(self):
        self.conn = None
        r = CFG['retry']; self.attempts, self.base, self.cap = r['attempts'], r['base_delay_s'], r['max_delay_s']

    def _conn(self):
        if self.conn is None or self.conn.closed:
            self.conn = connect(attempts=self.attempts, row_factory=dict_row)
        return self.conn

    def fetch(self, table, tcfg, cursor, limit):
        cols = tcfg['cursor']
        where = [sql.SQL('{} < now() - make_interval(secs => %s)').format(sql.Identifier(tcfg['time_col']))]
        params = [CFG['safety_lag_seconds']]
        if cursor is not None:
            where.append(sql.SQL('({}) > ({})').format(sql.SQL(', ').join(map(sql.Identifier, cols)),
                                                       sql.SQL(', ').join(sql.Placeholder() * len(cols))))
            params += cursor
        q = sql.SQL('select * from {} where {} order by {} limit %s').format(
            sql.Identifier(table), sql.SQL(' and ').join(where), sql.SQL(', ').join(map(sql.Identifier, cols)))
        params.append(limit)
        for i in range(self.attempts):
            try:
                c = self._conn()
                with c.transaction():
                    c.execute('set transaction read only')
                    c.execute(sql.SQL('set local statement_timeout = {}').format(sql.Literal(CFG['statement_timeout_ms'])))
                    return c.execute(q, params).fetchall()
            except RETRYABLE as ex:
                try: self.conn and self.conn.close()
                except Exception: pass
                self.conn = None
                if i == self.attempts - 1 or fatal(ex): raise
                w = backoff(i, self.base, self.cap)
                log.warning('%s 읽기 실패 (%s/%s): %s → %.0f초 뒤 같은 위치부터 재시도', table, i + 1, self.attempts, str(ex).splitlines()[0][:120], w)
                time.sleep(w)

    def count_pending(self, table, tcfg, cursor):
        cols = tcfg['cursor']
        where = [sql.SQL('{} < now() - make_interval(secs => %s)').format(sql.Identifier(tcfg['time_col']))]
        params = [CFG['safety_lag_seconds']]
        if cursor is not None:
            where.append(sql.SQL('({}) > ({})').format(sql.SQL(', ').join(map(sql.Identifier, cols)),
                                                       sql.SQL(', ').join(sql.Placeholder() * len(cols))))
            params += cursor
        c = self._conn()
        return c.execute(sql.SQL('select count(*) as n from {} where {}').format(sql.Identifier(table), sql.SQL(' and ').join(where)), params).fetchone()['n']


# ───────── 테이블 하나 내보내기 ─────────
def export_table(table, tcfg, st, reader, max_batches):
    ts = st['tables'].setdefault(table, {'cursor': None, 'rows_total': 0, 'files': 0})
    n_rows = n_files = 0
    for _ in range(max_batches):
        rows = reader.fetch(table, tcfg, ts['cursor'], CFG['batch_size'])
        if not rows:
            break
        first = [rows[0][c] for c in tcfg['cursor']]; last = [rows[-1][c] for c in tcfg['cursor']]
        day = rows[0][tcfg['time_col']].date().isoformat()
        rel = os.path.join(table, f'date={day}', f'part-{slug(first)}-{slug(last)}.jsonl.gz')
        body = ''.join(json.dumps(r, ensure_ascii=False, default=jdefault) + '\n' for r in rows).encode()
        data = gzip.compress(body, mtime=0)            # mtime 고정 → 같은 내용이면 같은 바이트
        path = os.path.join(OUT, rel)
        atomic_write(path, data)
        with gzip.open(path, 'rt') as f:               # 되읽어 확인
            if sum(1 for _ in f) != len(rows):
                raise RuntimeError(f'{rel}: 되읽은 행 수가 다름')
        if os.environ.get('EXPORT_FAIL_AFTER_WRITE') == '1':   # 장애 테스트용: 파일은 썼는데 커서 저장 전에 죽음
            raise SystemExit('테스트: 커서 저장 전 강제 종료')
        with open(os.path.join(OUT, '_manifest.jsonl'), 'a') as mf:
            mf.write(json.dumps(dict(table=table, file=rel, rows=len(rows), first=first, last=last,
                                     sha256=hashlib.sha256(data).hexdigest(), exported_at=datetime.datetime.now().isoformat()),
                                default=jdefault, ensure_ascii=False) + '\n')
        ts['cursor'] = json.loads(json.dumps(last, default=jdefault))
        ts['rows_total'] += len(rows); ts['files'] += 1
        ts['last_run'] = datetime.datetime.now().isoformat(); ts['last_error'] = None
        save_state(st)
        n_rows += len(rows); n_files += 1
        log.info('%s: %d행 → %s (누적 %d행)', table, len(rows), rel, ts['rows_total'])
        if len(rows) < CFG['batch_size']:
            break
    return n_rows, n_files


def main():
    st = load_state()
    tables = args.table or [t for t, c in CFG['tables'].items() if c.get('enabled')]
    unknown = [t for t in tables if t not in CFG['tables']]
    if unknown:
        sys.exit(f'설정에 없는 테이블: {unknown}')
    if args.status:
        for t in CFG['tables']:
            s = st['tables'].get(t, {})
            print(f"{t:14} {'켜짐' if CFG['tables'][t].get('enabled') else '꺼짐'} | 누적 {s.get('rows_total', 0)}행, 파일 {s.get('files', 0)}개 | 커서 {s.get('cursor')} | 마지막 {s.get('last_run')} | 오류 {s.get('last_error')}")
        return 0
    if args.reset:
        if not args.yes:
            sys.exit('--reset 은 --yes 와 같이 (커서만 지움. 기존 파일이 남아 있으면 중복되니 함께 지울 것)')
        st['tables'].pop(args.reset, None); save_state(st); print(f'{args.reset} 커서 초기화'); return 0

    lock = open(os.path.join(OUT, '.lock'), 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log.error('다른 내보내기가 실행 중 — 종료'); return 2

    reader, code = Reader(), 0
    for t in tables:
        tcfg = CFG['tables'][t]
        try:
            if args.dry_run:
                print(f"{t}: 남은 행 {reader.count_pending(t, tcfg, st['tables'].get(t, {}).get('cursor'))} (지연 {CFG['safety_lag_seconds']}초 이전 것만)")
                continue
            n, f = export_table(t, tcfg, st, reader, args.max_batches or CFG['max_batches_per_run'])
            log.info('%s 완료: 이번 실행 %d행, 파일 %d개', t, n, f)
        except SystemExit:
            raise
        except Exception as ex:
            code = 1
            st['tables'].setdefault(t, {})['last_error'] = f'{type(ex).__name__}: {str(ex)[:300]}'
            save_state(st)
            log.error('%s 실패 (커서는 마지막 성공 위치 유지, 다음 실행에서 이어감): %s', t, ex)
    if reader.conn: reader.conn.close()
    return code


if __name__ == '__main__':
    sys.exit(main())
