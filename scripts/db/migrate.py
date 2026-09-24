"""supabase/migrations/*.sql 을 이름 순서대로 한 번씩 적용한다. 적용 기록은 public._migrations (이름·체크섬).
이미 적용한 파일이 바뀌었으면 멈춘다 (새 마이그레이션 파일로 고칠 것). 파일 하나 = 트랜잭션 하나라 실패하면 그 파일은 통째로 롤백.
사용: python3 scripts/db/migrate.py [--dry-run]"""
import os, sys, glob, hashlib, logging
sys.path.insert(0, os.path.dirname(__file__))
from pg import connect, ROOT

logging.basicConfig(level=logging.INFO, format='%(message)s')
DRY = '--dry-run' in sys.argv
files = sorted(glob.glob(os.path.join(ROOT, 'supabase', 'migrations', '*.sql')))
with connect() as c:
    c.execute('create table if not exists _migrations (name text primary key, checksum text not null, applied_at timestamptz not null default now())')
    c.execute('alter table _migrations enable row level security')
    c.commit()
    done = dict(c.execute('select name, checksum from _migrations').fetchall())
    for f in files:
        name, sql = os.path.basename(f), open(f).read()
        chk = hashlib.sha256(sql.encode()).hexdigest()
        if name in done:
            if done[name] != chk:
                sys.exit(f'✗ {name}: 이미 적용된 뒤 내용이 바뀜 — 새 마이그레이션 파일로 변경할 것')
            print(f'· {name} (적용됨)'); continue
        if DRY:
            print(f'→ {name} (적용 예정)'); continue
        try:
            with c.transaction():
                c.execute(sql)
                c.execute('insert into _migrations(name, checksum) values (%s, %s)', (name, chk))
            print(f'✓ {name}')
        except Exception as ex:
            sys.exit(f'✗ {name}: {ex} (이 파일은 롤백됨)')
