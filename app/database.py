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
