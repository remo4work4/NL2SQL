"""Qwen3 接入：阿里云百炼 OpenAI 兼容端点 + langchain-openai。

- enable_thinking 默认关闭（需求文档风险应对：降低延迟），已实测兼容端点接受该参数
- json_mode 使用 response_format json_object（不被支持时调用方降级重试）
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI

from app.core.config import settings


def _build(json_mode: bool) -> ChatOpenAI:
    kwargs: dict = dict(
        model=settings.llm_model,
        api_key=settings.dashscope_api_key or "missing",
        base_url=settings.dashscope_base_url,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout,
        max_retries=1,
    )
    if not settings.llm_enable_thinking:
        kwargs["extra_body"] = {"enable_thinking": False}
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(**kwargs)


@lru_cache(maxsize=2)
def get_chat_model(json_mode: bool = True) -> ChatOpenAI:
    """按参数缓存模型实例（json_mode=True 为主路径，False 为降级路径）。"""
    return _build(json_mode)
