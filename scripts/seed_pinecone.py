"""把 MySQL 里的菜单写入 Pinecone 向量库，并做一次语义检索抽查。"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

from tools import config, db_tool, pinecone_tool  # noqa: E402

print('=== 1) 索引状态（写入前）===')
stats = pinecone_tool.check_connection()
print(f"  索引      : {stats['index_name']}")
print(f"  维度      : {stats['dimension']}（配置要求 {stats['expected_dimension']}，"
      f"{'一致' if stats['dimension_ok'] else '不一致！'}）")
print(f"  向量总数  : {stats['total_vector_count']}")
print()

print('=== 2) 读取 MySQL 菜单 ===')
dishes = db_tool.get_menu_items()
print(f'  共 {len(dishes)} 道菜')
print()

print('=== 3) 构造向量化文本（以宫保鸡丁为例）===')
sample = next((d for d in dishes if d['dish_name'] == '宫保鸡丁'), dishes[0] if dishes else None)
if sample:
    print('  ' + pinecone_tool.build_dish_document(sample))
print()

print('=== 4) 写入向量库 ===')
result = pinecone_tool.seed_menu_items(dishes)
print(f"  已写入 {result['seeded']} 条，维度 {result['dimension']}")
print(f"  菜品 ID：{result['dish_ids']}")
print()

print('=== 5) 索引状态（写入后）===')
stats = pinecone_tool.check_connection()
print(f"  向量总数  : {stats['total_vector_count']}")
print(f"  命名空间  : {stats['namespaces']}")
print()

print('=== 6) 语义检索抽查 ===')
QUERIES = [
    '我想吃点辣的',
    '有没有清淡的素菜',
    '适合减肥的菜',
    '有什么鱼',
    '便宜的下饭菜',
]
for query in QUERIES:
    hits = pinecone_tool.search_menu_items(query, top_k=3)
    print(f'  查询「{query}」')
    for hit in hits:
        print(f"    {hit['score']:.4f}  {hit['dish_name']:<8} "
              f"{hit.get('formatted_price', '')}  {hit.get('flavor', '')}")
print()

print('=== 7) 带过滤条件的检索（素食 + 价格上限 20）===')
for hit in pinecone_tool.search_menu_items('想吃点东西', top_k=5, vegetarian_only=True, max_price=20):
    print(f"  {hit['score']:.4f}  {hit['dish_name']:<8} {hit.get('formatted_price', '')} "
          f"素食={hit.get('is_vegetarian')}")
print()

print('Pinecone 数据准备完成')