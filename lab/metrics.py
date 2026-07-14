"""ASR 与置信区间 —— 诚实地量化不确定性。

研究结论：temp=0 也不等于确定（GPU 批不变性）；N=1 是把噪声当信号。
所以每格跑 N 次，用 Wilson 95% 区间报，而不是裸点估计。
（参见 research notes task-d：Wilson/Clopper-Pearson、ASR@α%、20-30 次重复。）
"""
from __future__ import annotations

import math


def wilson_ci(successes: int, n: int, z: float = 1.96):
    """二项比例的 Wilson 95% 置信区间。n=0 返回 (0,1)。"""
    if n == 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def asr(successes: int, n: int) -> float:
    return successes / n if n else 0.0


def fmt_cell(successes: int, n: int) -> str:
    """'60% (3/5) [23-88%]' 这样一格，带 N 和置信区间——图注铁律。"""
    lo, hi = wilson_ci(successes, n)
    return f"{asr(successes, n) * 100:.0f}% ({successes}/{n}) [{lo * 100:.0f}-{hi * 100:.0f}%]"
