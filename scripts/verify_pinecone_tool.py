"""验证 tools/pinecone_tool.py：过滤、检索、写入幂等性。"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

from tools import db_tool, pinecone_tool  # noqa: E402

print('=== 1) 索引状态 ===')
stats = pinecone_tool.check_connection()
print(f"  索引 {stats['index_name']}  维度 {stats['dimension']}"
      f"（配置 {stats['expected_dimension']}，{'一致' if stats['dimension_ok'] else '不一致'}）")
print(f"  向量总数 {stats['total_vector_count']}  命名空间 {stats['namespaces']}")

valid_names = {d['dish_name'] for d in db_tool.get_menu_items()}
print(f'  当前菜单（MySQL 为准）：{sorted(valid_names)}')

print('\n=== 2) 语义检索（应只返回菜单里的菜，且不含遗留向量的空结果）===')
for query in ['我想吃点辣的', '有没有清淡的', '有什么鱼', '推荐几个招牌菜', '有什么主食']:
    hits = pinecone_tool.search_menu_items(query, top_k=5)
    print(f"\n  查询「{query}」-> {len(hits)} 条")
    for hit in hits:
        flag = '' if hit['dish_name'] in valid_names else '  <== 不在当前菜单里！'
        print(f"    {hit['score']:.4f}  dish_id={hit['dish_id']:<3} {hit['dish_name']:<8}"
              f" {hit.get('formatted_price', '')}{flag}")

print('\n=== 3) top_k 足够大时不应出现名称为空或 dish_id 非法的条目 ===')
hits = pinecone_tool.search_menu_items('菜品', top_k=20)
bad = [h for h in hits if not h['dish_name'] or not isinstance(h['dish_id'], int)]
print(f'  取回 {len(hits)} 条，非法条目 {len(bad)} 条')
print(f'  取回的菜：{[h["dish_name"] for h in hits]}')

print('\n=== 4) 带过滤的检索 ===')
for kwargs in [
    {'vegetarian_only': True},
    {'category': '川菜'},
    {'max_price': 20.0},
    {'max_spice_level': 1},
]:
    hits = pinecone_tool.search_menu_items('想吃点东西', top_k=5, **kwargs)
    print(f'  {kwargs} -> {[(h["dish_name"], h.get("formatted_price")) for h in hits]}')

print('\n=== 5) 写入幂等性（重复种子不应增加向量数）===')
before = pinecone_tool.get_index_stats()['total_vector_count']
pinecone_tool.seed_menu_items()
after = pinecone_tool.get_index_stats()['total_vector_count']
print(f'  写入前 {before} 条，写入后 {after} 条，'
      f'{"幂等正确" if before == after else "数量发生变化！"}')

print('\n=== 6) 向量文档示例 ===')
for dish in db_tool.get_menu_items()[:2]:
    print(f'  {pinecone_tool.build_dish_document(dish)}')

print('\npinecone_tool 验证完成')