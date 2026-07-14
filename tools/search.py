"""联网搜索工具 —— 可插拔多 provider，默认 DuckDuckGo（免 key，国内这台机实测可用）。

为什么不是维基：zh.wikipedia 在国内常不可达。DuckDuckGo 免 key 且中文结果不错；
若配了 TAVILY_API_KEY / BOCHA_API_KEY / SERPER_API_KEY 则优先用对应 API（更干净稳定）。

provider 选择（env `SEARCH_PROVIDER`，默认 auto）：
  auto -> 有 key 用对应 API，否则 DuckDuckGo
  ddg / tavily / bocha / serper -> 强制指定
返回 agent 的是 top-N 条 "标题 / 摘要 / 链接" 的纯文本。
"""
from __future__ import annotations

import os

import requests

from tools.base import Tool

_PROVIDER = os.getenv("SEARCH_PROVIDER", "auto").lower()
_TAVILY = os.getenv("TAVILY_API_KEY", "")
_BOCHA = os.getenv("BOCHA_API_KEY", "")
_SERPER = os.getenv("SERPER_API_KEY", "")
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
_TIMEOUT = 12


def _resolve() -> str:
    if _PROVIDER != "auto":
        return _PROVIDER
    if _TAVILY:
        return "tavily"
    if _BOCHA:
        return "bocha"
    if _SERPER:
        return "serper"
    return "ddg"


# —— 各 provider：统一返回 [{"title","snippet","url"}] —— #
def _ddg(query: str, k: int):
    try:                                          # 优先用库
        from duckduckgo_search import DDGS
        rows = DDGS().text(query, max_results=k, region="cn-zh") or []
        out = [{"title": r.get("title", ""), "snippet": r.get("body", ""),
                "url": r.get("href", "")} for r in rows]
        if out:
            return out
    except Exception:
        pass
    return _ddg_scrape(query, k)                  # 库被限流则降级直接抓 HTML


def _ddg_scrape(query: str, k: int):
    from bs4 import BeautifulSoup
    html = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                         headers={"User-Agent": _UA}, timeout=_TIMEOUT).text
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for res in soup.select(".result")[:k]:
        a = res.select_one(".result__a")
        sn = res.select_one(".result__snippet")
        if a:
            out.append({"title": a.get_text(" ", strip=True),
                        "snippet": sn.get_text(" ", strip=True) if sn else "",
                        "url": a.get("href", "")})
    return out


def _tavily(query: str, k: int):
    r = requests.post("https://api.tavily.com/search", json={
        "api_key": _TAVILY, "query": query, "max_results": k,
        "search_depth": "basic"}, timeout=_TIMEOUT).json()
    return [{"title": x.get("title", ""), "snippet": x.get("content", ""),
             "url": x.get("url", "")} for x in r.get("results", [])]


def _bocha(query: str, k: int):
    r = requests.post("https://api.bochaai.com/v1/web-search",
                      headers={"Authorization": f"Bearer {_BOCHA}"},
                      json={"query": query, "count": k}, timeout=_TIMEOUT).json()
    pages = (((r.get("data") or {}).get("webPages") or {}).get("value")) or []
    return [{"title": x.get("name", ""), "snippet": x.get("snippet", ""),
             "url": x.get("url", "")} for x in pages]


def _serper(query: str, k: int):
    r = requests.post("https://google.serper.dev/search",
                      headers={"X-API-KEY": _SERPER, "Content-Type": "application/json"},
                      json={"q": query, "num": k}, timeout=_TIMEOUT).json()
    return [{"title": x.get("title", ""), "snippet": x.get("snippet", ""),
             "url": x.get("link", "")} for x in r.get("organic", [])]


_PROVIDERS = {"ddg": _ddg, "tavily": _tavily, "bocha": _bocha, "serper": _serper}


class Search(Tool):
    name = "search"
    description = "联网搜索查事实/实时信息（默认 DuckDuckGo，中文优先）。参数 query 是搜索关键词。"
    params = {"query": "搜索关键词"}

    def execute(self, args):
        query = str(args.get("query", "")).strip()
        if not query:
            return "Error: query 为空"
        provider = _resolve()
        fn = _PROVIDERS.get(provider, _ddg)
        try:
            results = fn(query, 3)
        except Exception as e:
            try:                                  # 指定 provider 失败兜底回 DuckDuckGo
                results = _ddg(query, 3)
            except Exception:
                return f"Error: 搜索失败（provider={provider}）：{e}"
        if not results:
            return f"未搜到与 {query!r} 相关的结果。"
        lines = [f"搜索“{query}”（provider={provider}）Top {len(results)}："]
        for i, r in enumerate(results, 1):
            lines.append(f"{i}. {r['title']}\n   {r['snippet'][:160]}\n   {r['url']}")
        return "\n".join(lines)
