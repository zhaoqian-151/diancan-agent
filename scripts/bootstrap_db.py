"""Create missing tables without replacing existing data; optionally seed an empty menu."""
import argparse
import re
import sys
from pathlib import Path

import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import config


def execute_script(cursor, sql):
    cursor.execute(sql, map_results=True)
    while cursor.nextset():
        pass


def bootstrap(database=None, seed_menu=False):
    database = database or config.MYSQL_DB_NAME
    if not re.fullmatch(r'[A-Za-z0-9_]+', database):
        raise ValueError('Database name must contain only letters, numbers and underscores')
    root = config.PROJECT_ROOT / 'database'
    connection = mysql.connector.connect(
        host=config.MYSQL_HOST, port=config.MYSQL_PORT,
        user=config.MYSQL_USER_NAME, password=config.MYSQL_USER_PASSWORD,
        charset=config.MYSQL_CHARSET, connection_timeout=10,
    )
    cursor = connection.cursor()
    try:
        cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        connection.database = database
        execute_script(cursor, (root / 'schema.sql').read_text(encoding='utf-8'))
        if seed_menu:
            cursor.execute('SELECT COUNT(*) FROM menu_items')
            if cursor.fetchone()[0]:
                raise ValueError('Menu is not empty. Seed was refused; existing menu was not changed.')
            execute_script(cursor, (root / 'menu_seed.sql').read_text(encoding='utf-8'))
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.execute('SET FOREIGN_KEY_CHECKS = 1')
        cursor.close()
        connection.close()
    print(f'Database {database}: schema ready. Existing business records were preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-menu', action='store_true', help='Load the 14 initial dishes only when menu_items is empty')
    args = parser.parse_args()
    bootstrap(seed_menu=args.seed_menu)
