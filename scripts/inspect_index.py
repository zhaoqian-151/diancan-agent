"""检查 Pinecone 索引里的历史遗留向量，并复测配送地址置信度判断。"""

import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

from tools import amap_tool, config, llm_tool, pinecone_tool  # noqa: E402

print('=== A) 索引内全部向量 ===')
index = pinecone_tool.get_index()
stats = index.describe_index_stats()
print(f"  总数 {stats['total_vector_count']}，命名空间 {stats.get('namespaces')}")

# 用一次宽泛查询把尽可能多的向量取回来
probe = llm_tool.embed_query('菜品')
response = index.query(vector=probe, top_k=50, include_metadata=True, namespace='')
matches = response.get('matches') or []
print(f'  查询取回 {len(matches)} 条')

print('\n  ID 与元数据：')
for match in matches:
    meta = match.get('metadata') or {}
    print(f"    {match['id']:<24} score={match.get('score', 0):.4f} "
          f"dish_id={meta.get('dish_id')} name={meta.get('dish_name')}")

ids = [m['id'] for m in matches]
ours = [i for i in ids if i.startswith('dish-')]
others = [i for i in ids if not i.startswith('dish-')]
print(f'\n  本项目写入的（dish-*）：{len(ours)} 条 -> {sorted(ours)}')
print(f'  其它历史遗留        ：{len(others)} 条 -> {sorted(others)}')

names = [((m.get('metadata') or {}).get('dish_name')) for m in matches]
dup = {n: c for n, c in Counter(names).items() if c > 1}
print(f'\n  重复的菜品名（会污染检索结果）：{dup if dup else "无"}')

non_dish = [n for n in names if n and n not in
            {'宫保鸡丁', '麻婆豆腐', '清炒时蔬', '红烧鲈鱼', '蒜蓉西兰花'}]
print(f'  不属于当前菜单的名字：{non_dish if non_dish else "无"}')
print(f'  无名字的元数据条数  ：{sum(1 for n in names if not n)}')

print()
print('=== B) 配送地址置信度复测 ===')
for address in ['不存在的地址乱码xyz', '重庆市大渡口区茄子溪', '大渡口区', '重庆市大渡口区兴海路204号']:
    result = amap_tool.check_delivery_range(address, travel_mode=3)
    print(f'\n  查询：{address}')
    print(f"    low_confidence={result['low_confidence']}  "
          f"address_level={result.get('address_level')!r}  in_range={result['in_range']}  "
          f"distance={result['distance']}")
    print(f"    {result['message']}")