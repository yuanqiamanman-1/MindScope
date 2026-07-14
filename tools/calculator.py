"""计算器：受限 AST 求值，只允许数字与算术运算，绝不 eval 任意代码。"""
from __future__ import annotations

import ast
import operator

from tools.base import Tool

_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
    ast.Div: operator.truediv, ast.Pow: operator.pow, ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv, ast.USub: operator.neg, ast.UAdd: operator.pos,
}


def _eval(node):
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        raise ValueError("只允许数字常量")
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("非法表达式（只支持数字算术）")


class Calculator(Tool):
    name = "calculator"
    description = "做数学计算。参数 expr 是一个算术表达式字符串。"
    params = {"expr": "算术表达式，如 (3.8*152-3.62*96)/56"}

    def execute(self, args):
        try:
            tree = ast.parse(str(args.get("expr", "")), mode="eval")
            return str(_eval(tree.body))
        except Exception as e:
            return f"Error: {e}"
