"""
llm_tool模块

该模块提供了通用的llm调用
将llm调用进行封装,在后续调用时只需调用call_llm即可

同时提供文本向量化能力（embed_texts / embed_query），供 Pinecone 模块使用。

实现要点
--------
项目通过 OpenAI 兼容网关调用 deepseek-v4.1-flash，该模型是**推理模型**：
- 返回体里除了 content，还有一个 reasoning_content 字段放思维链；
- 思维链的 token 同样计入 completion_tokens，max_tokens 给小了 content 会是空串。

因此这里做了两件事：把 max_tokens 默认放宽到 4096，并在 content 为空时回退到
reasoning_content，避免上层拿到空回复。
"""

import logging
import time
from typing import Iterable, List, Optional, Sequence, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from . import config

logger = logging.getLogger(__name__)

# 兼容 OpenAI 的接口，同一套代码可切换到任意兼容网关
DEFAULT_SYSTEM_PROMPT = '你是一个专业、热情的中文智能点餐助手。'


def get_chat_model(
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> ChatOpenAI:
    """构造 ChatOpenAI 实例（按需指定温度与最大输出长度）。"""
    if not config.LLM_API_KEY:
        raise RuntimeError(f'未配置 LLM_API_KEY，请检查 {config.ENV_PATH}')

    return ChatOpenAI(
        model=config.LLM_MODEL,
        api_key=config.LLM_API_KEY,
        base_url=config.LLM_BASE_URL,
        temperature=config.LLM_TEMPERATURE if temperature is None else temperature,
        max_tokens=config.LLM_MAX_TOKENS if max_tokens is None else max_tokens,
        timeout=config.LLM_TIMEOUT,
        max_retries=2,
    )


def build_messages(
    prompt: Optional[str] = None,
    system: Optional[str] = None,
    messages: Optional[Sequence[BaseMessage]] = None,
) -> List[BaseMessage]:
    """把各种入参形式统一成消息列表。"""
    if messages:
        return list(messages)

    if prompt is None:
        raise ValueError('call_llm 需要提供 prompt 或 messages 之一')

    built: List[BaseMessage] = [SystemMessage(content=system or DEFAULT_SYSTEM_PROMPT)]
    built.append(HumanMessage(content=prompt))
    return built


def extract_text(message: AIMessage) -> str:
    """从返回结果里取出正文；正文为空时回退到思维链内容。"""
    content: Union[str, list] = message.content

    if isinstance(content, list):
        # 新版接口可能返回内容块列表
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get('type') == 'text':
                parts.append(block.get('text', ''))
        content = ''.join(parts)

    text = (content or '').strip()
    if text:
        return text

    # 推理模型：max_tokens 不够时 content 为空，只剩思维链
    reasoning = ''
    extra = getattr(message, 'additional_kwargs', None) or {}
    for key in ('reasoning_content', 'reasoning'):
        value = extra.get(key)
        if value:
            reasoning = str(value).strip()
            break

    if reasoning:
        logger.warning('模型只返回了思维链，content 为空；已回退到 reasoning_content。'
                       '请调大 LLM_MAX_TOKENS（当前 %s）。', config.LLM_MAX_TOKENS)
        return reasoning

    logger.warning('模型返回了空内容。响应元数据：%s', getattr(message, 'response_metadata', {}))
    return ''


def call_llm_raw(
    prompt: Optional[str] = None,
    system: Optional[str] = None,
    messages: Optional[Sequence[BaseMessage]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> AIMessage:
    """调用大模型并返回原始消息对象（调试用，可看思维链与 token 用量）。"""
    model = get_chat_model(temperature=temperature, max_tokens=max_tokens)
    started = time.time()
    message = model.invoke(build_messages(prompt=prompt, system=system, messages=messages))
    elapsed_ms = int((time.time() - started) * 1000)

    # 一次对话会触发多次模型调用（选工具 + 生成答复），打点才能定位慢在哪
    usage = getattr(message, 'usage_metadata', None) or {}
    logger.info('大模型调用 %d ms（输入 %s / 输出 %s tokens）', elapsed_ms,
                usage.get('input_tokens', '?'), usage.get('output_tokens', '?'))
    return message


def call_llm(
    prompt: Optional[str] = None,
    system: Optional[str] = None,
    messages: Optional[Sequence[BaseMessage]] = None,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
) -> str:
    """调用大模型，直接返回文本结果。

    三种用法：
        call_llm('今天有什么推荐？')
        call_llm('今天有什么推荐？', system='你是点餐助手')
        call_llm(messages=[SystemMessage(...), HumanMessage(...)])
    """
    return extract_text(call_llm_raw(
        prompt=prompt, system=system, messages=messages,
        temperature=temperature, max_tokens=max_tokens,
    ))


# ---------------------------------------------------------------- 向量化

_embeddings: Optional[OpenAIEmbeddings] = None


def get_embeddings() -> OpenAIEmbeddings:
    """构造文本向量化模型（与 Pinecone 索引维度保持一致）。"""
    global _embeddings
    if _embeddings is None:
        if not config.LLM_API_KEY:
            raise RuntimeError(f'未配置 LLM_API_KEY，请检查 {config.ENV_PATH}')

        _embeddings = OpenAIEmbeddings(
            model=config.EMBEDDING_MODEL,
            api_key=config.LLM_API_KEY,
            base_url=config.LLM_BASE_URL,
            dimensions=config.EMBEDDING_DIMENSION,
            # 关键：非 OpenAI 官方端点必须关掉 tiktoken 分词，
            # 否则会按 OpenAI 的编码去数 token 并报错。
            check_embedding_ctx_length=False,
            # DashScope 的 text-embedding-v3 单次最多 10 条
            chunk_size=10,
        )
    return _embeddings


def embed_texts(texts: Iterable[str]) -> List[List[float]]:
    """批量把文本转成向量。"""
    items = [t for t in texts]
    if not items:
        return []
    return get_embeddings().embed_documents(items)


def embed_query(text: str) -> List[float]:
    """把单条查询文本转成向量。"""
    return get_embeddings().embed_query(text)