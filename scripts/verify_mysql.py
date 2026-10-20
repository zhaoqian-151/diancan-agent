"""用项目虚拟环境和 .env 配置，验证 MySQL 连接与数据读取。"""
import os
import sys

from dotenv import dotenv_values

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(PROJECT_ROOT, '.env')

cfg = dotenv_values(ENV_PATH)
print('.env 读取结果:')
print(f"  MYSQL_HOST          = {cfg.get('MYSQL_HOST')}")
print(f"  MYSQL_PORT          = {cfg.get('MYSQL_PORT')}")
print(f"  MYSQL_USER_NAME     = {cfg.get('MYSQL_USER_NAME')}")
print(f"  MYSQL_DB_NAME       = {cfg.get('MYSQL_DB_NAME')}")
print(f"  LLM_MODEL           = {cfg.get('LLM_MODEL')}")
print(f"  EMBEDDING_MODEL     = {cfg.get('EMBEDDING_MODEL')}")
print(f"  PINECONE_INDEX_NAME = {cfg.get('PINECONE_INDEX_NAME')}")
print()

import mysql.connector  # noqa: E402

try:
    conn = mysql.connector.connect(
        host=cfg.get('MYSQL_HOST', '127.0.0.1'),
        port=int(cfg.get('MYSQL_PORT', 3306)),
        user=cfg.get('MYSQL_USER_NAME', 'root'),
        password=cfg.get('MYSQL_USER_PASSWORD', ''),
        database=cfg.get('MYSQL_DB_NAME', 'menu'),
        charset=cfg.get('MYSQL_CHARSET', 'utf8mb4'),
    )
except Exception as exc:  # noqa: BLE001
    print(f'连接失败: {type(exc).__name__}: {exc}')
    sys.exit(1)

print(f'连接成功: MySQL {conn.get_server_info()}')

cursor = conn.cursor()
cursor.execute('SELECT COUNT(*) FROM menu_items')
print('菜品数量:', cursor.fetchone()[0])

cursor.execute('SELECT id, dish_name, price, category, spice_level, flavor FROM menu_items ORDER BY id')
print('\n菜单:')
for row in cursor.fetchall():
    print(f'  {row[0]}  {row[1]:<8} ¥{row[2]:>6}  {row[3]:<4} 辣度{row[4]}  {row[5]}')

cursor.close()
conn.close()
print('\n数据库层验证通过')