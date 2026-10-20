"""验证 tools/llm_tool.py：文本对话与向量化。"""

import logging
import sys

sys.path.insert(0, __file__.rsplit('\\', 2)[0])

logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')

from tools import config, llm_tool  # noqa: E402

print('配置摘要：')
print(config.describe())
print()

print('=== 1) 普通对话 call_llm ===')
answer = llm_tool.call_llm('用一句话介绍宫保鸡丁。', system='你是中餐点餐助手，回答简洁。')
print('回复:', answer[:200] if answer else '(空)')
print(f'长度: {len(answer)} 字')
print()

print('=== 2) 原始响应（看推理字段与 token 用量）===')
raw = llm_tool.call_llm_raw('这家店有素食吗？', system='你是中餐点餐助手，回答简洁。')
print('消息类型   :', type(raw).__name__)
print('content    :', repr(str(raw.content)[:120]))
extra = getattr(raw, 'additional_kwargs', None) or {}
print('附加字段键 :', list(extra.keys()))
if extra.get('reasoning_content'):
    print('思维链长度 :', len(str(extra['reasoning_content'])), '字')
print('token 用量 :', getattr(raw, 'response_metadata', {}).get('token_usage'))
print('结束原因   :', getattr(raw, 'response_metadata', {}).get('finish_reason'))
print()

print('=== 3) 向量化 embed_query ===')
vec = llm_tool.embed_query('麻辣的川菜')
print('向量维度:', len(vec), '（应等于', config.EMBEDDING_DIMENSION, '）')
print('前 5 维 :', [round(v, 5) for v in vec[:5]])
print()

print('=== 4) 批量向量化 embed_texts ===')
vecs = llm_tool.embed_texts(['宫保鸡丁 酸甜微辣', '麻婆豆腐 麻辣鲜香', '清炒时蔬 清淡爽口'])
print('返回条数:', len(vecs), '每条的维度:', [len(v) for v in vecs])
print()

print('llm_tool 验证完成')