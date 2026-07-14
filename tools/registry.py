"""工具注册表：收集工具、按名分发、生成注入提示词的清单。"""
from __future__ import annotations

from core.prompt import describe_tools


class Registry:
    def __init__(self, tools=None):
        self._tools = {}
        for t in tools or []:
            self.register(t)

    def register(self, tool):
        self._tools[tool.name] = tool
        return tool

    def get(self, name):
        return self._tools.get(name)

    def all(self):
        return list(self._tools.values())

    def describe(self) -> str:
        return describe_tools(self.all())


def default_tools(*, file_base=None, memory_path=None):
    """构造全部内置工具实例。file_base/memory_path 供时间旅行分支隔离注入（Phase 4.6）。"""
    from tools.calculator import Calculator
    from tools.search import Search
    from tools.file_io import FileRead, FileWrite
    from tools.python_exec import PythonExec
    from tools.memory_tool import MemoryStore, MemoryRecall

    return [
        Calculator(),
        Search(),
        FileRead(base=file_base),
        FileWrite(base=file_base),
        PythonExec(),
        MemoryStore(path=memory_path),
        MemoryRecall(path=memory_path),
    ]
