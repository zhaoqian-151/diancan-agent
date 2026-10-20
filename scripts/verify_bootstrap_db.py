"""Verify fresh installation in an isolated disposable database, never the configured database."""
import json
import re
import sys
import uuid
from pathlib import Path

import mysql.connector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.bootstrap_db import bootstrap
from tools import config


def main():
    target = 'release_check_' + uuid.uuid4().hex[:12]
    assert re.fullmatch(r'release_check_[a-f0-9]{12}', target) and target != config.MYSQL_DB_NAME
    connection = mysql.connector.connect(host=config.MYSQL_HOST, port=config.MYSQL_PORT,
        user=config.MYSQL_USER_NAME, password=config.MYSQL_USER_PASSWORD)
    cursor = connection.cursor()
    cursor.execute('SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = %s', (target,))
    assert cursor.fetchone() is None, 'Refusing to reuse an existing database'
    # Release the information_schema snapshot before another connection creates
    # the schema; MySQL 8's transactional data dictionary otherwise looks stale.
    connection.commit()
    try:
        bootstrap(target, seed_menu=True)
        connection.database = target
        cursor.execute('SHOW TABLES')
        tables = [row[0] for row in cursor.fetchall()]
        assert len(tables) == 10, f'Unexpected installed tables: {tables}'
        cursor.execute('SELECT COUNT(*) FROM menu_items')
        assert cursor.fetchone()[0] == 14
        for table in ('users', 'orders', 'members', 'coupons', 'shopping_cart'):
            cursor.execute(f'SELECT COUNT(*) FROM `{table}`')
            assert cursor.fetchone()[0] == 0, f'Unexpected private records in {table}'
        connection.commit()
        bootstrap(target)
        try:
            bootstrap(target, seed_menu=True)
        except ValueError as error:
            assert 'not empty' in str(error)
        else:
            raise AssertionError('Seeding existing menu should be refused')
        cursor.execute('SELECT COUNT(*) FROM menu_items')
        assert cursor.fetchone()[0] == 14
        print(json.dumps({'passed':True,'tables':10,'menu_items':14,'private_records':0,'repeat_seed_refused':True}))
    finally:
        # The generated target is checked above and never points at the user database.
        cursor.execute(f'DROP DATABASE IF EXISTS `{target}`')
        cursor.close()
        connection.close()


if __name__ == '__main__':
    main()
