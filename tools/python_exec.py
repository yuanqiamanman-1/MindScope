"""python_exec（降级 · 隔离子进程）——非生产级沙箱，仅本地 demo。

防护：`-I` 隔离模式 + 剥离含 KEY/TOKEN/SECRET 的环境变量（防偷 API key）
     + 临时工作目录 + 超时杀死 + 输出截断。
诚实声明：删模块白名单挡不住 __import__/内置逃逸/资源炸弹，故改走"隔离子进程 +
剥离密钥环境 + 资源限制"。能力仅限算数/画图，不保证抵御所有逃逸。
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

from tools.base import Tool

_MAX_OUT = 4000
_DENY = ("KEY", "TOKEN", "SECRET", "PASSWORD")


def _safe_env() -> dict:
    """保留 OS 运行 python 所需的环境，但剥离任何疑似密钥的变量。"""
    return {
        k: v for k, v in os.environ.items()
        if not any(d in k.upper() for d in _DENY)
    }


class PythonExec(Tool):
    name = "python_exec"
    description = "执行一小段 Python 做计算或画图（受限沙箱，无密钥、无持久文件）。参数 code。"
    params = {"code": "Python 源码"}

    def execute(self, args):
        code = str(args.get("code", ""))
        with tempfile.TemporaryDirectory() as td:
            try:
                r = subprocess.run(
                    [sys.executable, "-I", "-c", code],
                    cwd=td, env=_safe_env(),
                    capture_output=True, text=True, timeout=5,
                )
            except subprocess.TimeoutExpired:
                return "Error: 执行超时(>5s)"
        out = (r.stdout or "").strip()
        if r.returncode and r.stderr:
            out = (out + "\n[stderr] " + r.stderr.strip()).strip()
        if len(out) > _MAX_OUT:
            out = out[:_MAX_OUT] + "…[截断]"
        return out or "(无输出)"
