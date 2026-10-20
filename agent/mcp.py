"""
实现LangChain中各个工具的定义（定义三个工具、工具一：实现常规问题的对话回答 工具二：实现菜品查询问题对话 工具三：实现距离范围配送问题对话）

三个工具都返回**可直接展示给用户的中文文本**，同时把结构化结果（推荐的菜品 ID、
配送距离等）写进一次对话的轨迹里，供 assistant 组装接口返回值。

轨迹用 contextvars 保存，因此每次对话互不干扰，也能安全地在多线程下并发调用。
"""

import contextvars
import json
import logging
from typing import Any, Dict, List, Optional

from langchain_core.tools import tool

from tools import amap_tool, config, db_tool, llm_tool, pinecone_tool

logger = logging.getLogger(__name__)

# 单次对话的工具调用轨迹
_trace: contextvars.ContextVar[Optional[List[Dict[str, Any]]]] = contextvars.ContextVar(
    'diancan_tool_trace', default=None)


def start_trace() -> List[Dict[str, Any]]:
    """开始记录本次对话的工具调用轨迹，返回轨迹列表。"""
    items: List[Dict[str, Any]] = []
    _trace.set(items)
    return items


def get_trace() -> List[Dict[str, Any]]:
    """读取当前对话的轨迹；没有开始时返回空列表。"""
    return _trace.get() or []


def _record(payload: Dict[str, Any]) -> None:
    trace = _trace.get()
    if trace is not None:
        trace.append(payload)


# ==================================================================
# 工具一：常规问题的对话回答
# ==================================================================

@tool
def restaurant_qa(question: str) -> str:
    """回答与具体菜品无关的常规咨询问题。

    适用场景：本店叫什么、地址在哪、电话多少、营业时间、配送范围多大、
    怎么下单、打招呼寒暄、饮食搭配建议、忌口提醒等。
    当用户的问题不是针对某道菜、也没有给出收货地址时，用这个工具。
    """
    info = amap_tool.get_merchant_info()
    menu_text = db_tool.get_menu_summary_text()

    system = (
        f'你是「{info["name"]}」的点餐客服。回答要口语化、简洁，'
        f'一般不超过 150 字，不要编造本店没有的信息。'
    )
    prompt = f"""本店信息：
- 店名：{info['name']}
- 地址：{info['address'] or '（未配置）'}
- 电话：{info['phone'] or '（未配置）'}
- 营业时间：{info['business_hours'] or '（未配置）'}
- 配送范围：{info['delivery_radius_text']}（默认按{info['default_path_mode_text']}计算）

在售菜品：
{menu_text}

顾客的问题：{question}

请直接回答顾客。如果问的是本店信息，就按上面的资料回答；
如果资料里没有（比如问有没有会员卡），就如实说明并引导顾客换个问题。"""

    answer = llm_tool.call_llm(prompt, system=system) or '抱歉，我暂时回答不了这个问题。'

    _record({'tool': 'restaurant_qa', 'type': 'general',
             'question': question, 'answer': answer})
    return answer


# ==================================================================
# 工具二：菜品查询与推荐
# ==================================================================

def _parse_preferences(query: str) -> Dict[str, Any]:
    """从自然语言里抠出能用来过滤的硬条件（预算、素食、辣度）。

    纯向量检索只看语义相似度，理解不了"不超过 20 块"这种数值约束，
    所以这里先解析出来，交给检索当过滤条件用。
    """
    import re

    prefs: Dict[str, Any] = {}

    price_patterns = [
        r'不超过\s*(\d+(?:\.\d+)?)',
        r'不高于\s*(\d+(?:\.\d+)?)',
        r'预算\s*(?:是|在|大概)?\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*(?:块|元|块钱)?\s*(?:以内|以下|之内)',
        r'(\d+(?:\.\d+)?)\s*(?:块|元)钱?\s*(?:以?内|以?下)?',
    ]
    for pattern in price_patterns:
        found = re.search(pattern, query)
        if found:
            value = float(found.group(1))
            # 太小的数字多半不是价格（比如"2个人"）
            if 1 <= value <= 1000:
                prefs['max_price'] = value
                break

    if any(word in query for word in ('素食', '素菜', '吃素', '全素', '素的', '不吃肉', '斋')):
        prefs['vegetarian_only'] = True

    if any(word in query for word in ('清淡', '不辣', '不要辣', '不能吃辣', '怕辣')):
        prefs['max_spice_level'] = 0

    return prefs


def _collect_candidates(query: str, top_k: int = 5) -> List[Dict[str, Any]]:
    """收集候选菜品：先补上用户直接点名的菜，再叠加语义检索结果。"""
    candidates: List[Dict[str, Any]] = []
    seen = set()
    preferences = _parse_preferences(query)

    def matches(dish):
        return (dish.get('is_available')
                and (not preferences.get('vegetarian_only') or dish.get('is_vegetarian'))
                and ('max_price' not in preferences or dish['price'] <= preferences['max_price'])
                and ('max_spice_level' not in preferences or dish['spice_level'] <= preferences['max_spice_level']))

    # 1) 用户话里直接提到了菜名，这类必须排在前面
    for dish in db_tool.get_menu_items():
        if dish['dish_name'] in query and dish['id'] not in seen and matches(dish):
            candidates.append(dish)
            seen.add(dish['id'])

    # 2) 语义检索，带上解析出来的硬条件
    preferences = _parse_preferences(query)
    hits: List[Dict[str, Any]] = []
    try:
        hits = pinecone_tool.search_menu_items(query, top_k=top_k,
                                               enrich_from_db=False, **preferences)
    except pinecone_tool.PineconeError as exc:
        logger.warning('向量检索不可用，回退到数据库检索：%s', exc)

    for hit in hits:
        if hit['dish_id'] in seen:
            continue
        detail = db_tool.get_dish_by_id(hit['dish_id'])
        if not detail or not matches(detail):
            continue
        detail = dict(detail)
        detail['score'] = hit['score']
        candidates.append(detail)
        seen.add(detail['id'])

    # 3) 关键词 + 条件兜底，保证向量库挂了也能推荐
    if not candidates:
        for dish in db_tool.get_menu_items(keyword=query, limit=top_k, **preferences):
            if dish['id'] not in seen:
                candidates.append(dish)
                seen.add(dish['id'])
    if not candidates:
        candidates = db_tool.get_menu_items(limit=top_k, **preferences)

    return [dish for dish in candidates if matches(dish)][:max(top_k, 3)]


def _mentioned_menu_ids(answer: str, candidates: List[Dict[str, Any]]) -> List[int]:
    """从模型写好的答复里反查出它到底推荐了哪几道菜。

    不能直接取候选列表的前三个：模型可能只挑了其中两道，
    那样前端会高亮到用户根本没看到的菜。
    """
    found = []
    for dish in candidates:
        position = answer.find(dish['dish_name'])
        if position >= 0:
            found.append((position, dish['id']))
    found.sort()
    ids = [dish_id for _, dish_id in found][:3]
    return ids


@tool
def menu_consult(query: str) -> str:
    """查询菜品信息并根据需求推荐菜品。

    适用场景：让店家推荐菜、想吃某种口味（辣/清淡/酸甜）、有预算限制、
    吃素、忌口或过敏、想了解某道菜的价格/食材/做法/辣度等。
    例如「有什么推荐」「想吃辣的」「便宜点的」「有没有素的」「宫保鸡丁多少钱」。
    """
    preferences = _parse_preferences(query)
    candidates = _collect_candidates(query)
    if not candidates:
        answer = '抱歉，菜单里暂时没有符合条件的菜品，要不要换个口味试试？'
        _record({'tool': 'menu_consult', 'type': 'recommend',
                 'query': query, 'answer': answer, 'menu_ids': [], 'dishes': [],
                 'preferences': preferences})
        return answer

    lines = []
    for dish in candidates:
        tags = [dish['category'], dish['spice_text']]
        if dish['is_vegetarian'] and '素食' not in tags:
            tags.append('素食')
        detail = [f"{dish['id']}. {dish['dish_name']} {dish['formatted_price']}"
                  f"（{'/'.join(tags)}）"]
        if dish.get('description'):
            detail.append(f"   描述：{dish['description']}")
        if dish.get('main_ingredients'):
            detail.append(f"   食材：{dish['main_ingredients']}")
        if dish.get('allergens') and dish['allergens'] not in ('无过敏源', '无'):
            detail.append(f"   过敏原：{dish['allergens']}")
        lines.append('\n'.join(detail))

    system = '你是专业的中餐点餐顾问，推荐要具体、有理由，语气热情但不啰嗦。'
    prompt = f"""顾客的需求：{query}

店里可以推荐给这位顾客的菜品：
{chr(10).join(lines)}

请据此回答顾客：
1. 先正面回应需求；
2. 推荐 1 到 3 道最合适的菜，说明推荐理由和价格；
3. 如果顾客提到了忌口或过敏，必须明确提醒相关菜品；
4. 不要推荐上面清单以外的菜，也不要编造价格。
控制在 200 字以内。"""

    answer = llm_tool.call_llm(prompt, system=system) or '这几道菜可能合您的口味。'

    # 按答复里真正提到的菜来定高亮 ID，而不是取候选列表的前几个
    menu_ids = _mentioned_menu_ids(answer, candidates)
    id_set = set(menu_ids)
    mentioned = [d for d in candidates if d['id'] in id_set][:3]

    _record({'tool': 'menu_consult', 'type': 'recommend', 'query': query,
             'answer': answer, 'menu_ids': menu_ids, 'preferences': preferences,
             'dishes': [{k: v for k, v in d.items() if k != 'score'} for d in mentioned]})
    return answer


# ==================================================================
# 工具三：配送范围检查
# ==================================================================

@tool
def delivery_query(address: str, travel_mode: int = 3) -> str:
    """检查某个收货地址是否在本店配送范围内，并给出距离与预计时间。

    适用场景：顾客提供了地址并询问能不能送到，例如「能送到大渡口区九宫庙吗」
    「送不送到解放碑」「XX小区在配送范围吗」。

    Args:
        address: 收货地址，越详细越准，最好带城市和区。
        travel_mode: 出行方式，1-步行，2-骑行，3-驾车，默认 3。
    """
    result = amap_tool.check_delivery_range(address, travel_mode)
    _record({'tool': 'delivery_query', 'type': 'delivery', 'address': address,
             'answer': result['message'], 'delivery': result})
    return result['message']


# 三个工具，顺序与脚手架注释一致
ALL_TOOLS = [restaurant_qa, menu_consult, delivery_query]


def tool_names() -> List[str]:
    return [t.name for t in ALL_TOOLS]


def describe_tools() -> str:
    """列出工具名与用途，便于排查模型为什么选错工具。"""
    return '\n'.join(f'  {t.name}: {(t.description or "").splitlines()[0]}'
                     for t in ALL_TOOLS)


def tool_result_json(payload: Dict[str, Any]) -> str:
    """把结构化结果转成 JSON 字符串（调试用）。"""
    return json.dumps(payload, ensure_ascii=False, default=str)
