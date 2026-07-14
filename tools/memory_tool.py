"""长期记忆工具：memory_store / memory_recall → data/memory.json。

跨会话持久；文件缺失/损坏优雅降级（不崩溃）。
path 可注入分支本地 overlay（时间旅行隔离，Phase 4.6）。
"""
from __future__ import annotations

import json
from pathlib import Path

import config
from tools.base import Tool

_DEFAULT_PATH = config.DATA / "memory.json"


def _load(path) -> dict:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}  # 缺失/损坏 → 优雅初始化为空


def _save(data, path):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def summary(path=None) -> str:
    """把长期记忆汇成一段可注入系统提示词的文字；空则返回 ''（用于自动召回）。"""
    data = _load(path or _DEFAULT_PATH)
    if not data:
        return ""
    lines = "\n".join(f"- {k}：{v}" for k, v in data.items())
    return f"【长期记忆】你记得以下关于用户的信息，回答时可直接使用，无需再查：\n{lines}"


class MemoryStore(Tool):
    name = "memory_store"
    description = "把一条信息存入长期记忆（跨会话）。参数 key, value。"
    params = {"key": "键", "value": "值"}

    def __init__(self, path=None):
        self.path = path or _DEFAULT_PATH

    def execute(self, args):
        data = _load(self.path)
        data[str(args.get("key"))] = args.get("value")
        _save(data, self.path)
        return f"已记住 {args.get('key')!r}"


class MemoryRecall(Tool):
    name = "memory_recall"
    description = "从长期记忆取回信息。参数 key（省略则列出全部键）。"
    params = {"key": "键，可省略"}

    def __init__(self, path=None):
        self.path = path or _DEFAULT_PATH

    def execute(self, args):
        data = _load(self.path)
        key = args.get("key")
        if not key:
            return ("记忆中的键: " + ", ".join(data.keys())) if data else "（记忆为空）"
        return str(data.get(str(key), f"（无 {key!r} 的记忆）"))
