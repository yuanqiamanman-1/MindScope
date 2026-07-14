"""搜索工具测试（离线确定性，不打真网络）：格式化 / 空查询 / provider 兜底 / 无结果。"""
import tools.search as S
from tools.search import Search


def test_search_formats_results(monkeypatch):
    monkeypatch.setattr(S, "_PROVIDER", "ddg")          # 强制 ddg，避开 env key
    monkeypatch.setitem(S._PROVIDERS, "ddg", lambda q, k: [
        {"title": "阿尔伯特·爱因斯坦", "snippet": "1879 年生，1955 年卒。", "url": "http://x"}])
    out = Search().execute({"query": "爱因斯坦"})
    assert "爱因斯坦" in out and "1879" in out and "ddg" in out


def test_search_empty_query():
    assert "Error" in Search().execute({"query": "  "})


def test_search_falls_back_to_ddg(monkeypatch):
    """指定 provider 抛错 → 兜底回 DuckDuckGo。"""
    monkeypatch.setattr(S, "_PROVIDER", "tavily")

    def boom(q, k):
        raise RuntimeError("provider down")

    monkeypatch.setitem(S._PROVIDERS, "tavily", boom)
    monkeypatch.setattr(S, "_ddg", lambda q, k: [{"title": "兜底结果", "snippet": "ok", "url": "u"}])
    assert "兜底结果" in Search().execute({"query": "x"})


def test_no_results(monkeypatch):
    monkeypatch.setattr(S, "_PROVIDER", "ddg")
    monkeypatch.setitem(S._PROVIDERS, "ddg", lambda q, k: [])
    assert "未搜到" in Search().execute({"query": "asdkfjalskdfj"})
