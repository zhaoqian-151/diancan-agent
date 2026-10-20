"""验证 agent/mcp.py 与 agent/assistant.py：三个工具的选择与输出。"""

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.WARNING, format='%(levelname)s %(message)s')

from agent import assistant, mcp  # noqa: E402

print('=== 0) 组件摘要 ===')
print(assistant.describe())
print()

print('=== 0.1) 偏好解析（不需要大模型）===')
for text in ['我不想超过 20 块钱，推荐一个',
             '预算 30 元以内',
             '有没有清淡一点的素菜',
             '我想吃点辣的',
             '10块以内来个菜',
             '两个人吃点什么好']:
    print(f"  {text:<24} -> {mcp._parse_preferences(text)}")
print()

print('=== 0.2) 高亮 ID 反查（只挑答复里真正提到的菜）===')
candidates = [
    {'id': 1, 'dish_name': '宫保鸡丁'},
    {'id': 2, 'dish_name': '麻婆豆腐'},
    {'id': 5, 'dish_name': '蒜蓉西兰花'},
    {'id': 3, 'dish_name': '清炒时蔬'},
    {'id': 4, 'dish_name': '红烧鲈鱼'},
]
for answer in ['推荐蒜蓉西兰花和清炒时蔬',
               '麻婆豆腐最合适，也可以试试宫保鸡丁',
               '红烧鲈鱼不错']:
    print(f"  {answer:<26} -> {mcp._mentioned_menu_ids(answer, candidates)}")
print()

CASES = [
    ('常规咨询-店铺信息', '你们店在哪儿？几点开门？'),
    ('常规咨询-寒暄', '你好呀'),
    ('菜品推荐-辣', '我想吃点辣的，有什么推荐吗？'),
    ('菜品推荐-素食', '有没有清淡一点的素菜？'),
    ('菜品咨询-指定菜', '宫保鸡丁多少钱？里面有什么食材？'),
    ('菜品推荐-预算', '我不想超过 20 块钱，推荐一个'),
    ('配送检查-范围内', '能送到重庆市大渡口区茄子溪吗？'),
    ('配送检查-范围外', '重庆市渝中区解放碑送不送？'),
]

for label, question in CASES:
    print('=' * 70)
    print(f'【{label}】用户：{question}')
    result = assistant.chat_with_assistant(question)
    print(f"  选用工具 : {result['tool_calls']}")
    print(f"  类型     : {result['type']}")
    print(f"  耗时     : {result['elapsed_ms']} ms")
    if result.get('menu_ids'):
        print(f"  推荐菜品ID: {result['menu_ids']}")
    print(f"  回复     : {result['response']}")
    print()

print('=' * 70)
print('【多轮对话】带历史记录')
history = [
    {'role': 'user', 'content': '我想吃点辣的'},
    {'role': 'assistant', 'content': '推荐麻婆豆腐，麻辣鲜香，¥18.00，很下饭。'},
]
result = assistant.chat_with_assistant('那这个能送到大渡口区九宫庙吗？', history=history)
print(f"  选用工具 : {result['tool_calls']}")
print(f"  类型     : {result['type']}")
print(f"  回复     : {result['response']}")
print()

print('=' * 70)
print('【空输入】')
print(' ', assistant.chat_with_assistant('   '))
print()

print('agent 验证完成')
print(f'最终索引统计: {mcp.pinecone_tool.get_index_stats()}')