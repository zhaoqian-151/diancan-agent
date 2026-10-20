"""
智能点餐助手主程序

该程序构建了一个包含工具选择功能的LLM系统(相当于LangChain中的Agent角色)，能够：
1. 自动选择合适的工具（常规咨询、菜品推荐、配送范围检查）
2. 调用相应工具并返回结果
3. 提供自然、友好的对话体验

实现说明
--------
用 LangChain 1.x 的 create_agent 构建工具调用循环。三个工具（见 mcp.py）返回的
已经是写好的中文答复，Agent 的职责是**判断该用哪个工具**并把答复交给用户，
因此系统提示里明确要求它原样转述、不要自己发挥，避免二次改写引入幻觉。

对外只暴露 chat_with_assistant，返回值已经按前端需要的结构整理好。
"""

import logging
import time
from typing import Any, Dict, List, Optional, Sequence

from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from tools import config, llm_tool

from . import mcp

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是「智能点餐助手」的调度中枢，负责判断顾客的请求该交给哪个工具处理。

可用工具：
1. restaurant_qa —— 常规咨询：店铺名称、地址、电话、营业时间、配送范围、寒暄、忌口建议等，
   与具体菜品无关的问题。
2. menu_consult —— 菜品查询与推荐：让推荐菜、想吃某种口味、有预算限制、吃素、过敏忌口，
   或想了解某道菜的价格 / 食材 / 做法 / 辣度。
3. delivery_query —— 配送范围检查：顾客给出了收货地址并问能不能送到。

工作规则：
- 必须调用工具，不要凭自己的知识直接回答。
- 一次只调用最合适的那一个工具；只有顾客同时问了菜品和配送时才调用两个。
- 工具返回的已经是写给顾客的成品答复，请把它作为你的最终回答原样输出，
  不要改写、不要补充工具没有提到的信息、不要额外加客套话。
- 如果顾客的问题信息不全（比如只说了"能送到吗"但没给地址），
  就用 restaurant_qa 说明情况并请顾客补充。
"""

_agent = None


class ModelCallCounter(BaseCallbackHandler):
    """统计一次对话里大模型被调用了几次、各花了多久。

    一次对话通常要调 2~3 次模型（选工具 -> 工具内生成答复 -> Agent 汇总），
    deepseek-v4.1-flash 又是推理模型，单次就可能十几秒。没有这个打点就
    只能看到总耗时，定位不到慢在哪一步。
    """

    def __init__(self) -> None:
        super().__init__()
        self.durations_ms: List[int] = []
        self._starts: Dict[Any, float] = {}

    def on_llm_start(self, serialized, prompts, **kwargs) -> None:  # noqa: ANN001
        run_id = kwargs.get('run_id')
        if run_id is not None:
            self._starts[run_id] = time.time()

    def on_llm_end(self, response, **kwargs) -> None:  # noqa: ANN001
        self._finish(kwargs.get('run_id'))

    def on_llm_error(self, error, **kwargs) -> None:  # noqa: ANN001
        self._finish(kwargs.get('run_id'))

    def _finish(self, run_id) -> None:  # noqa: ANN001
        started = self._starts.pop(run_id, None)
        if started is not None:
            self.durations_ms.append(int((time.time() - started) * 1000))

    @property
    def count(self) -> int:
        return len(self.durations_ms)

    @property
    def total_ms(self) -> int:
        return sum(self.durations_ms)

    def summary(self) -> str:
        if not self.durations_ms:
            return '无模型调用'
        parts = ' + '.join(f'{ms}ms' for ms in self.durations_ms)
        return f'{self.count} 次调用（{parts}）'


def get_agent():
    """构建（并缓存）Agent。"""
    global _agent
    if _agent is None:
        _agent = create_agent(
            model=llm_tool.get_chat_model(temperature=0.3),
            tools=mcp.ALL_TOOLS,
            system_prompt=SYSTEM_PROMPT,
        )
    return _agent


def reset_agent() -> None:
    """丢弃缓存的 Agent（改了系统提示或工具后调用）。"""
    global _agent
    _agent = None


def _to_messages(history: Optional[Sequence[Dict[str, str]]]) -> List[BaseMessage]:
    """把 [{'role': 'user'|'assistant', 'content': ...}] 转成 LangChain 消息。"""
    messages: List[BaseMessage] = []
    for item in history or []:
        content = (item.get('content') or '').strip()
        if not content:
            continue
        role = (item.get('role') or 'user').lower()
        if role in ('assistant', 'ai'):
            messages.append(AIMessage(content=content))
        else:
            messages.append(HumanMessage(content=content))
    return messages


def _last_text(messages: Sequence[Any]) -> str:
    """取最后一条有正文的 AI 消息。"""
    for message in reversed(list(messages)):
        if isinstance(message, AIMessage):
            content = message.content
            if isinstance(content, list):
                content = ''.join(
                    part if isinstance(part, str) else part.get('text', '')
                    for part in content
                )
            if content and str(content).strip():
                return str(content).strip()
    return ''


def _shape(question: str, trace: List[Dict[str, Any]], final_text: str) -> Dict[str, Any]:
    """把工具轨迹和最终答复整理成接口需要的结构。"""
    recommend = next((t for t in reversed(trace) if t.get('type') == 'recommend'), None)
    delivery = next((t for t in reversed(trace) if t.get('type') == 'delivery'), None)

    # Agent 原样转述时 final_text 就是工具答复；万一它没输出内容，就用工具答复兜底
    tool_answers = [t['answer'] for t in trace if t.get('answer')]
    display = final_text or ('\n\n'.join(dict.fromkeys(tool_answers)) if tool_answers
                             else '抱歉，我没能理解您的意思，可以再说一遍吗？')

    if recommend:
        kind = 'recommend'
    elif delivery:
        kind = 'delivery'
    elif trace:
        kind = 'general'
    else:
        kind = 'unknown'

    return {
        'response': display,
        # 前端先看 recommendation，有值就按"推荐结果"渲染并高亮菜品
        'recommendation': display if kind == 'recommend' else None,
        'menu_ids': list(recommend['menu_ids']) if recommend else [],
        'dishes': list(recommend['dishes']) if recommend else [],
        'delivery': delivery['delivery'] if delivery else None,
        'type': kind,
        'tool_calls': [t.get('tool') for t in trace],
        'question': question,
    }


def chat_with_assistant(
    query: str,
    history: Optional[Sequence[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """处理一次用户请求，返回结构化结果。

    Args:
        query: 用户这一轮说的话。
        history: 之前的对话，形如 [{'role': 'user', 'content': '...'}, ...]。

    Returns:
        含 response / recommendation / menu_ids / type / delivery 等字段的字典。
    """
    started = time.time()
    question = (query or '').strip()

    if not question:
        return {'response': '请问您想吃点什么？', 'recommendation': None, 'menu_ids': [],
                'dishes': [], 'delivery': None, 'type': 'empty', 'tool_calls': [],
                'question': '', 'llm_calls': 0, 'llm_ms': 0, 'elapsed_ms': 0}

    trace = mcp.start_trace()
    messages = _to_messages(history) + [HumanMessage(content=question)]

    counter = ModelCallCounter()
    try:
        result = get_agent().invoke(
            {'messages': messages},
            config={'recursion_limit': 15, 'callbacks': [counter]},
        )
        final_text = _last_text(result.get('messages') or [])
        logger.info('模型调用：%s', counter.summary())
    except Exception as exc:  # noqa: BLE001  网络、限流、工具异常都走这里
        logger.exception('Agent 调用失败')
        fallback = _fallback(question)
        return {
            'response': f'处理您的请求时出了点问题（{type(exc).__name__}），{fallback}',
            'recommendation': None, 'menu_ids': [], 'dishes': [], 'delivery': None,
            'type': 'error', 'tool_calls': [t.get('tool') for t in trace],
            'question': question, 'error': f'{type(exc).__name__}: {exc}',
            'llm_calls': counter.count, 'llm_ms': counter.total_ms,
            'elapsed_ms': int((time.time() - started) * 1000),
        }

    shaped = _shape(question, trace, final_text)
    shaped['llm_calls'] = counter.count
    shaped['llm_ms'] = counter.total_ms
    shaped['elapsed_ms'] = int((time.time() - started) * 1000)
    return shaped


def _fallback(question: str) -> str:
    """Agent 整体不可用时的兜底提示。"""
    if any(word in question for word in ('送', '配送', '地址', '能到')):
        return '请稍后再试配送查询。'
    return '请稍后再试。'


def describe() -> str:
    """启动时打印的组件摘要。"""
    return '\n'.join([
        f'  大模型  : {config.LLM_MODEL}',
        f'  工具数  : {len(mcp.ALL_TOOLS)}',
        mcp.describe_tools(),
    ])