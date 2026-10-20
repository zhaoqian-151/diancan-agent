"""清理 Pinecone 索引里不属于本项目的历史遗留向量。

索引 menu-item-index 里存在一批更早的实现写下的向量：ID 是纯数字（1~10），
元数据形如 {'dish_id': '菜品ID:6'}，没有 dish_name。它们不是本项目写入的，
会白占检索名额（tools/pinecone_tool.py 已在代码里过滤，但清理掉更干净）。

默认只列出、不删除；确认无误后加 -Apply 才真正删除。
"""

import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

from tools import llm_tool, pinecone_tool  # noqa: E402

parser = argparse.ArgumentParser(description='清理 Pinecone 里的历史遗留向量')
parser.add_argument('--apply', action='store_true', help='真正执行删除（默认只预览）')
parser.add_argument('--top-k', type=int, default=200, help='扫描多少条向量')
args = parser.parse_args()

index = pinecone_tool.get_index()
stats = index.describe_index_stats()
print(f"索引 {pinecone_tool.config.PINECONE_INDEX_NAME}，共 {stats['total_vector_count']} 条向量")

# 用一个泛化查询把索引里的向量尽量捞回来
probe = llm_tool.embed_query('菜品 食物 餐 菜单')
matches = (index.query(vector=probe, top_k=args.top_k, include_metadata=True,
                       namespace=pinecone_tool.NAMESPACE).get('matches') or [])

ours, legacy = [], []
for match in matches:
    meta = match.get('metadata') or {}
    if match['id'].startswith('dish-') and meta.get('dish_name'):
        ours.append(match['id'])
    else:
        legacy.append((match['id'], meta))

print(f'  本项目向量 : {len(ours)} 条')
print(f'  遗留向量   : {len(legacy)} 条')
print()
for vid, meta in sorted(legacy):
    print(f'    {vid:<10} 元数据={meta}')

if not legacy:
    print('\n没有需要清理的向量。')
    raise SystemExit(0)

if not args.apply:
    print(f'\n以上 {len(legacy)} 条为预览。确认后执行：')
    print(f'  .venv\\Scripts\\python.exe scripts\\cleanup_index.py --apply')
    raise SystemExit(0)

index.delete(ids=[vid for vid, _ in legacy], namespace=pinecone_tool.NAMESPACE)
print(f'\n已删除 {len(legacy)} 条遗留向量。')
after = index.describe_index_stats()
print(f"删除后索引共 {after['total_vector_count']} 条向量")