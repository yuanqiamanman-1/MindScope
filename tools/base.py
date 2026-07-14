"""工具统一接口。每个工具暴露 name / description / params / execute(args)->str。"""
from __future__ import annotations


class Tool:
    name: str = ""
    description: str = ""
    params: dict = {}

    def execute(self, args: dict) -> str:  # pragma: no cover - 抽象
        raise NotImplementedError
