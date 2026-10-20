"""Export schema and public menu only; never exports orders, members or visitors."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import db_tool


def sql_value(value):
    if value is None:
        return 'NULL'
    if isinstance(value, (int, float)):
        return str(value)
    from decimal import Decimal
    if isinstance(value, Decimal):
        return str(value)
    return "'" + str(value).replace('\\', '\\\\').replace("'", "''").replace('\x00', '\\0') + "'"


def main():
    output = Path(__file__).resolve().parents[1] / 'database'
    output.mkdir(exist_ok=True)
    schema = ['-- Structure only. No customers, orders, members or account balances.',
              'SET NAMES utf8mb4;', 'SET FOREIGN_KEY_CHECKS = 0;']
    with db_tool.db_cursor() as cursor:
        cursor.execute('SHOW TABLES')
        tables = sorted(next(iter(row.values())) for row in cursor.fetchall())
        for table in tables:
            if not re.fullmatch(r'[a-zA-Z0-9_]+', table):
                raise ValueError('Invalid table identifier')
            cursor.execute(f'SHOW CREATE TABLE `{table}`')
            ddl = cursor.fetchone()['Create Table']
            ddl = re.sub(r'\sAUTO_INCREMENT=\d+', '', ddl)
            schema.append(ddl.replace('CREATE TABLE ', 'CREATE TABLE IF NOT EXISTS ', 1) + ';')
        cursor.execute(f'SELECT {db_tool._MENU_COLUMNS} FROM menu_items ORDER BY id')
        menu = cursor.fetchall()
    schema.append('SET FOREIGN_KEY_CHECKS = 1;')
    (output / 'schema.sql').write_text('\n\n'.join(schema) + '\n', encoding='utf-8')
    columns = [part.strip() for part in db_tool._MENU_COLUMNS.split(',')]
    seed = ['-- Optional initial menu dataset from the existing project; not sales data.',
            '-- Import only into a new empty menu. No business records are included.',
            'SET NAMES utf8mb4;']
    for dish in menu:
        # Release includes the bundled illustrative images, never expiring links.
        dish['image_url'] = f"/images/generated/menu-{dish['id']}.webp"
        values = ', '.join(sql_value(dish[column]) for column in columns)
        seed.append(f"INSERT INTO menu_items ({', '.join(columns)}) VALUES ({values});")
    (output / 'menu_seed.sql').write_text('\n'.join(seed) + '\n', encoding='utf-8')
    print(f'Exported {len(tables)} table definitions and {len(menu)} public menu items; no business records.')


if __name__ == '__main__':
    main()
