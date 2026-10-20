"""
智能点餐助手 服务类封装

封装三个核心功能：
- smart_chat: 调用 assistant.py 中的 chat_with_assistant 函数
- delivery_check: 调用 check_delivery_range 函数 获取配送范围展示
- get_menu: 调用 get_menu_items_list 函数 获取菜品区域数据的展示

另外负责多轮对话的会话保持：Web 请求本身是无状态的，这里用进程内的
会话表按 session_id 保存最近几轮对话，再交给 Agent 当上下文。
"""

import logging
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

from agent import assistant
from tools import amap_tool, config, db_tool

logger = logging.getLogger(__name__)


class SessionStore:
    """进程内的会话历史表（线程安全）。

    只保留最近 max_turns 轮对话；会话过期或数量超限时自动清理。
    重启服务会丢失历史，属于当前阶段的预期行为。
    """

    def __init__(self, max_turns: int = 6, ttl_seconds: int = 1800,
                 max_sessions: int = 500) -> None:
        self.max_turns = max_turns
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._data: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()

    def _prune_locked(self) -> None:
        now = time.time()
        expired = [sid for sid, item in self._data.items()
                   if now - item['updated_at'] > self.ttl_seconds]
        for sid in expired:
            self._data.pop(sid, None)

        # 还是太多就丢掉最旧的
        if len(self._data) > self.max_sessions:
            ordered = sorted(self._data.items(), key=lambda kv: kv[1]['updated_at'])
            for sid, _ in ordered[:len(self._data) - self.max_sessions]:
                self._data.pop(sid, None)

    def new_session_id(self) -> str:
        return uuid.uuid4().hex

    def get(self, session_id: str) -> List[Dict[str, str]]:
        with self._lock:
            self._prune_locked()
            item = self._data.get(session_id)
            return list(item['messages']) if item else []

    def append(self, session_id: str, role: str, content: str) -> None:
        if not content:
            return
        with self._lock:
            item = self._data.setdefault(
                session_id, {'messages': [], 'updated_at': time.time()})
            item['messages'].append({'role': role, 'content': content})
            # 只留最近 max_turns 轮（一问一答算一轮）
            limit = self.max_turns * 2
            if len(item['messages']) > limit:
                item['messages'] = item['messages'][-limit:]
            item['updated_at'] = time.time()
            self._prune_locked()

    def clear(self, session_id: str) -> bool:
        with self._lock:
            return self._data.pop(session_id, None) is not None

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            self._prune_locked()
            return {'sessions': len(self._data), 'max_turns': self.max_turns,
                    'ttl_seconds': self.ttl_seconds}


class DiancanService:
    """智能点餐的业务服务层，接口层只调这里。"""

    def __init__(self) -> None:
        self.sessions = SessionStore()

    # ------------------------------------------------------------ 智能对话
    def smart_chat(self, query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """处理一次对话，自动带上该会话的历史。"""
        question = (query or '').strip()
        session_id = (session_id or '').strip() or self.sessions.new_session_id()

        if not question:
            return {'response': '请问您想吃点什么？', 'recommendation': None,
                    'menu_ids': [], 'dishes': [], 'delivery': None, 'type': 'empty',
                    'tool_calls': [], 'elapsed_ms': 0, 'session_id': session_id}

        history = self.sessions.get(session_id)
        result = assistant.chat_with_assistant(question, history=history)

        # 出错的那一轮不写进历史，免得污染后续上下文
        if result.get('type') != 'error':
            self.sessions.append(session_id, 'user', question)
            self.sessions.append(session_id, 'assistant', result.get('response', ''))

        result['session_id'] = session_id
        result['history_turns'] = len(history) // 2
        return result

    # ------------------------------------------------------------ 配送范围
    def delivery_check(self, address: str, travel_mode: Optional[int] = None) -> Dict[str, Any]:
        """检查地址是否在配送范围内。"""
        mode = travel_mode if travel_mode in (1, 2, 3) else config.DEFAULT_PATH_MODE
        return amap_tool.check_delivery_range(address, mode)

    # ------------------------------------------------------------ 菜品列表
    def get_menu(self) -> Dict[str, Any]:
        """菜品列表，字段与前端展示一致。"""
        items = db_tool.get_menu_items_list()
        return {
            'menu_items': items,
            'total': len(items),
            'categories': db_tool.get_categories(),
        }

    # ------------------------------------------------------------ 健康检查
    def health(self, deep: bool = False) -> Dict[str, Any]:
        """服务健康状态。deep=True 时额外探测外部依赖（会慢一些）。"""
        report: Dict[str, Any] = {
            'status': 'ok',
            'config_file': str(config.ENV_PATH),
            'llm_model': config.LLM_MODEL,
            'shop': config.MERCHANT_NAME,
            'sessions': self.sessions.stats(),
            'checks': {},
        }

        try:
            report['checks']['mysql'] = db_tool.check_connection()
        except Exception as exc:  # noqa: BLE001
            report['status'] = 'degraded'
            report['checks']['mysql'] = {'ok': False, 'error': str(exc)}

        if deep:
            try:
                from tools import pinecone_tool
                stats = pinecone_tool.check_connection()
                report['checks']['pinecone'] = {'ok': bool(stats.get('dimension_ok')), **stats}
                if not stats.get('dimension_ok'):
                    report['status'] = 'degraded'
            except Exception as exc:  # noqa: BLE001
                report['status'] = 'degraded'
                report['checks']['pinecone'] = {'ok': False, 'error': str(exc)}

            try:
                report['checks']['amap'] = {'ok': True, **amap_tool.check_connection()}
            except Exception as exc:  # noqa: BLE001
                report['status'] = 'degraded'
                report['checks']['amap'] = {'ok': False, 'error': str(exc)}

        return report

    def clear_session(self, session_id: str) -> bool:
        return self.sessions.clear(session_id)


# 全局单例，接口层直接引用
service = DiancanService()


# ---------------------------------------------------------------- 模块级快捷函数

def smart_chat(query: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    return service.smart_chat(query, session_id)


def delivery_check(address: str, travel_mode: Optional[int] = None) -> Dict[str, Any]:
    return service.delivery_check(address, travel_mode)


def get_menu() -> Dict[str, Any]:
    return service.get_menu()