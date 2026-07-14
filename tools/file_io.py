"""文件读写：限定 workspace 沙箱。

用 Path.is_relative_to 判定（非 startswith 字符串前缀，防 sibling 前缀误判），
resolve() 会折叠 `..` 并跟随符号链接，故能拦住路径穿越与符号链接逃逸。
base 可注入分支本地 workspace（时间旅行隔离，Phase 4.6）。
"""
from __future__ import annotations

from pathlib import Path

import config
from tools.base import Tool


def _safe(base: Path, path: str) -> Path:
    base = Path(base).resolve()
    p = (base / str(path)).resolve()
    if not p.is_relative_to(base):
        raise ValueError(f"路径越界沙箱: {path!r}")
    return p


class FileRead(Tool):
    name = "file_read"
    description = "读取 workspace 沙箱内的文本文件。参数 path。"
    params = {"path": "相对 workspace 的文件路径"}

    def __init__(self, base=None):
        self.base = base or config.WORKSPACE

    def execute(self, args):
        try:
            p = _safe(self.base, args.get("path", ""))
        except ValueError as e:
            return f"Error: {e}"
        if not p.exists():
            return f"Error: 文件不存在 {args.get('path')!r}"
        return p.read_text(encoding="utf-8")


class FileWrite(Tool):
    name = "file_write"
    description = "写入文本到 workspace 沙箱内的文件。参数 path, content。"
    params = {"path": "相对 workspace 的文件路径", "content": "要写入的文本"}

    def __init__(self, base=None):
        self.base = base or config.WORKSPACE

    def execute(self, args):
        content = str(args.get("content", ""))
        try:
            p = _safe(self.base, args.get("path", ""))
        except ValueError as e:
            return f"Error: {e}"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"已写入 {len(content)} 字符到 {args.get('path')}"
