"""
Pinecone向量数据库工具模块

该模块提供Pinecone向量数据库的连接和操作功能，
用于存储和查询菜品信息的向量化数据，支持语义搜索

向量 ID 规则为 dish-<菜品ID>，重复写入会覆盖同一条记录，因此种子脚本可以反复执行。

注意：菜品本体数据仍以 MySQL 为准，Pinecone 里只存向量和少量用于过滤的元数据，
检索命中后再回 MySQL 取完整信息，避免两边数据不一致。
"""

import logging
from typing import Any, Dict, Iterable, List, Optional

from pinecone import Pinecone

from . import config, db_tool, llm_tool

logger = logging.getLogger(__name__)

# 统一使用默认命名空间
NAMESPACE = ''

_pc: Optional[Pinecone] = None


class PineconeError(RuntimeError):
    """向量库访问失败。"""


# ---------------------------------------------------------------- 连接

def get_client() -> Pinecone:
    global _pc
    if _pc is None:
        if not config.PINECONE_API_KEY:
            raise PineconeError(f'未配置 PINECONE_API_KEY，请检查 {config.ENV_PATH}')
        _pc = Pinecone(api_key=config.PINECONE_API_KEY)
    return _pc


# 索引对象要缓存：get_index 里既要 list_indexes 又要构造 Index，
# 是两次网络往返；而且 Pinecone 7.x 的 Index 对象持有 gRPC 通道，
# 每次重建等于每次重连。实测不缓存时单次检索要 3.3 秒。
_index = None


def get_index():
    """取到配置里指定的索引对象（缓存复用）。"""
    global _index
    if _index is None:
        client = get_client()
        name = config.PINECONE_INDEX_NAME
        try:
            names = [idx['name'] for idx in client.list_indexes()]
        except Exception as exc:  # noqa: BLE001
            raise PineconeError(f'无法列出 Pinecone 索引：{exc}') from exc

        if name not in names:
            raise PineconeError(f'Pinecone 中不存在索引「{name}」。现有索引：{names}')
        _index = client.Index(name)
    return _index


def reset_index() -> None:
    """丢弃缓存的索引对象（索引被重建后调用）。"""
    global _index
    _index = None


def get_index_stats() -> Dict[str, Any]:
    """索引统计信息，用于确认维度与数据量。"""
    index = get_index()
    stats = index.describe_index_stats()
    return {
        'index_name': config.PINECONE_INDEX_NAME,
        'dimension': stats.get('dimension'),
        'total_vector_count': stats.get('total_vector_count'),
        'namespaces': {k: v.get('vector_count') for k, v in (stats.get('namespaces') or {}).items()},
    }


# ---------------------------------------------------------------- 文档构造

def build_dish_document(dish: Dict[str, Any]) -> str:
    """把一道菜拼成用于向量化的文本。

    把名称、分类、口味、描述、食材、做法、辣度、素食都写进去，
    这样用户说“想吃辣的”“有没有素的”“清淡点的”都能命中。
    """
    parts = [
        dish['dish_name'],
        f"分类：{dish['category']}",
        f"口味：{dish.get('flavor') or '无'}",
        f"辣度：{dish.get('spice_text') or db_tool.spice_text(dish.get('spice_level'))}",
        f"价格：{dish.get('formatted_price') or db_tool.format_price(dish.get('price'))}",
    ]
    if dish.get('description'):
        parts.append(f"描述：{dish['description']}")
    if dish.get('main_ingredients'):
        parts.append(f"主要食材：{dish['main_ingredients']}")
    if dish.get('cooking_method'):
        parts.append(f"烹饪方法：{dish['cooking_method']}")
    parts.append('素食' if dish.get('is_vegetarian') else '荤菜')
    if dish.get('allergens'):
        parts.append(f"过敏原：{dish['allergens']}")
    return '；'.join(parts)


def _dish_metadata(dish: Dict[str, Any]) -> Dict[str, Any]:
    """Pinecone 元数据只放能做过滤的简单类型。"""
    return {
        'dish_id': int(dish['id']),
        'dish_name': str(dish['dish_name']),
        'category': str(dish['category']),
        'price': float(dish['price']),
        'spice_level': int(dish.get('spice_level') or 0),
        'is_vegetarian': bool(dish.get('is_vegetarian')),
        'flavor': str(dish.get('flavor') or ''),
    }


def _vector_id(dish_id: Any) -> str:
    return f'dish-{int(dish_id)}'


# ---------------------------------------------------------------- 写入

def seed_menu_items(
    items: Optional[Iterable[Dict[str, Any]]] = None,
    batch_size: int = 50,
) -> Dict[str, Any]:
    """把菜单写入向量库。items 为空时自动从 MySQL 取全部菜品。"""
    dishes = list(items) if items is not None else db_tool.get_menu_items()
    if not dishes:
        return {'seeded': 0, 'message': '菜单为空，没有需要写入的菜品'}

    documents = [build_dish_document(d) for d in dishes]
    vectors = llm_tool.embed_texts(documents)
    if len(vectors) != len(dishes):
        raise PineconeError(f'向量条数({len(vectors)})与菜品数({len(dishes)})不一致')

    payload = [
        {'id': _vector_id(d['id']), 'values': vec, 'metadata': _dish_metadata(d)}
        for d, vec in zip(dishes, vectors)
    ]

    index = get_index()
    for start in range(0, len(payload), batch_size):
        index.upsert(vectors=payload[start:start + batch_size], namespace=NAMESPACE)

    return {
        'seeded': len(payload),
        'index_name': config.PINECONE_INDEX_NAME,
        'dimension': len(vectors[0]),
        'dish_ids': [d['id'] for d in dishes],
    }


def delete_all() -> Dict[str, Any]:
    """清空索引里的全部向量（重建数据时使用）。"""
    index = get_index()
    index.delete(delete_all=True, namespace=NAMESPACE)
    return {'deleted': True, 'index_name': config.PINECONE_INDEX_NAME}


# ---------------------------------------------------------------- 检索

def search_menu_items(
    query: str,
    top_k: int = 5,
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    max_spice_level: Optional[int] = None,
    vegetarian_only: bool = False,
    enrich_from_db: bool = True,
) -> List[Dict[str, Any]]:
    """按语义检索菜品。

    返回列表，每项含 dish_id / score / 元数据；enrich_from_db=True 时
    还会回 MySQL 把完整菜品信息合并进来。
    """
    if not query or not query.strip():
        return []

    vector = llm_tool.embed_query(query.strip())

    conditions: Dict[str, Any] = {}
    if category:
        conditions['category'] = {'$eq': category}
    if max_price is not None:
        conditions['price'] = {'$lte': float(max_price)}
    if max_spice_level is not None:
        conditions['spice_level'] = {'$lte': int(max_spice_level)}
    if vegetarian_only:
        conditions['is_vegetarian'] = {'$eq': True}

    index = get_index()
    # 索引里可能存在别的实现写下的历史向量（元数据里没有 dish_name），
    # 这些条目会白占检索名额，所以多取一些、过滤掉之后只保留前 top_k 条。
    fetch_k = max(int(top_k) * 3, int(top_k) + 5)
    response = index.query(
        vector=vector,
        top_k=fetch_k,
        include_metadata=True,
        namespace=NAMESPACE,
        filter=conditions or None,
    )

    matches = response.get('matches') or []
    results: List[Dict[str, Any]] = []
    for match in matches:
        meta = match.get('metadata') or {}
        dish_id = meta.get('dish_id')
        dish_name = meta.get('dish_name')
        # 只认本项目写入的、元数据完整的向量
        if dish_name is None or dish_id is None:
            continue
        try:
            dish_id = int(dish_id)
        except (TypeError, ValueError):
            continue

        results.append({
            'dish_id': dish_id,
            'dish_name': str(dish_name),
            'score': round(float(match.get('score') or 0.0), 4),
            'category': meta.get('category'),
            'price': meta.get('price'),
            'spice_level': meta.get('spice_level'),
            'is_vegetarian': meta.get('is_vegetarian'),
            'flavor': meta.get('flavor'),
        })
        if len(results) >= int(top_k):
            break

    if enrich_from_db and results:
        ids = [r['dish_id'] for r in results if r['dish_id'] is not None]
        detail_map = {d['id']: d for d in db_tool.get_dishes_by_ids(ids)}
        for item in results:
            detail = detail_map.get(item['dish_id'])
            if detail:
                item.update({k: v for k, v in detail.items() if k != 'id'})

    return results


def check_connection() -> Dict[str, Any]:
    """连通性自检：索引是否可用、维度是否正确。"""
    stats = get_index_stats()
    stats['expected_dimension'] = config.EMBEDDING_DIMENSION
    stats['dimension_ok'] = stats.get('dimension') == config.EMBEDDING_DIMENSION
    return stats
