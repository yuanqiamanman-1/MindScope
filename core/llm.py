"""DeepSeek 客户端薄封装（chat + 流式）。

openai SDK 仅作 HTTP 客户端指向 DeepSeek 端点——不是 agent 框架，合规。
客户端懒加载：不配 key / 未装 openai 也能 import 本模块（便于 stub 测试）。
"""
from __future__ import annotations

import time

import config

_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI  # 懒导入
        _client = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
    return _client


def chat(messages, *, stream=False, temperature=0.6, model=None, max_tokens=None):
    kw = {}
    if max_tokens:                       # 限长 → 每轮更快出完（对戏/短回复用）
        kw["max_tokens"] = max_tokens
    return _get_client().chat.completions.create(
        model=model or config.MODEL,
        messages=messages,
        stream=stream,
        temperature=temperature,
        **kw,
    )


def chat_text(messages, *, retries=3, **kw) -> str:
    """非流式取整段文本，带 None/空响应防御 + 退避重试 + reasoning_content 兜底。"""
    kw.pop("stream", None)
    last = None
    for i in range(retries):
        resp = chat(messages, stream=False, **kw)
        choices = getattr(resp, "choices", None)
        if choices:
            msg = choices[0].message
            content = getattr(msg, "content", None) or getattr(msg, "reasoning_content", None)
            if content:
                return content
        last = resp
        time.sleep(0.8 * (i + 1))
    raise RuntimeError(f"LLM 无有效返回（重试 {retries} 次）: {str(last)[:300]}")


def chat_stream(messages, **kw):
    """逐 chunk 产出原始 token 文本（前端 raw→structured 用）。"""
    kw.pop("stream", None)
    for chunk in chat(messages, stream=True, **kw):
        choices = getattr(chunk, "choices", None)
        if not choices:
            continue
        delta = choices[0].delta
        if delta and getattr(delta, "content", None):
            yield delta.content
