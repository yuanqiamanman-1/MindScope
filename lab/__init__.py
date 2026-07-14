"""提示词注入攻防实验室 —— 真模型、可测量、诚实。

把"加一句防御就识破"的脚本木偶，换成一个真 GLM 上跑的
「攻击阶梯 × 防御层 → 攻击成功率(ASR) 热力图」实验。

核心论点（有文献支撑，见 research/2026-06-15-injection-lab/）：
提示词层防御在自适应攻击下会被击穿；真正稳的是架构层限权
（工具/上下文里压根没有密钥）。——「不要赌检测，要限权。」
"""
from lab.attacks import ATTACKS
from lab.defenses import DEFENSES
from lab.runner import run_cell, run_matrix
from lab.scenario import SECRET

__all__ = ["ATTACKS", "DEFENSES", "run_cell", "run_matrix", "SECRET"]
