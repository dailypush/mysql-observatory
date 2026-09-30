"""Versioned, additive migrations for existing and fresh demo volumes."""
from pathlib import Path
from database import connect


def migrate():
    with connect() as db, db.cursor() as cur:
        cur.execute("SELECT GET_LOCK('observatory_migrations', 30)")
        if next(iter(cur.fetchone().values())) != 1:
            raise RuntimeError('Could not acquire migration lock')
        cur.execute('CREATE TABLE IF NOT EXISTS schema_migrations (name VARCHAR(200) PRIMARY KEY, applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)')
        for path in sorted(Path('/app/migrations').glob('*.sql')):
            cur.execute('SELECT name FROM schema_migrations WHERE name=%s', (path.name,))
            if cur.fetchone():
                continue
            # These migration files contain simple DDL, not stored routines.
            # DDL commits implicitly; statements must be safe to retry after a crash.
            for statement in path.read_text().split(';'):
                if statement.strip():
                    cur.execute(statement)
            cur.execute('INSERT INTO schema_migrations(name) VALUES (%s)', (path.name,))
            db.commit()
            print(f'Applied migration: {path.name}', flush=True)

if __name__ == '__main__':
    migrate()
