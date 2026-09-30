import time
from decimal import Decimal
import os
import pymysql


def connect():
    return pymysql.connect(
        host=os.environ.get('DB_HOST', 'db'),
        user=os.environ.get('DB_USER', 'demo'),
        password=os.environ.get('DB_PASSWORD', 'local-demo-password'),
        database=os.environ.get('DB_NAME', 'observatory'),
        charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor,
        autocommit=False, connect_timeout=5, read_timeout=30,
    )


def clean(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def query(cur, sql, params=(), trace=None):
    start = time.perf_counter()
    cur.execute(sql, params)
    rows = cur.fetchall() if cur.description else []
    if trace is not None:
        trace.append({'sql': sql, 'params': list(params), 'ms': round((time.perf_counter()-start)*1000, 3)})
    return clean(rows)
