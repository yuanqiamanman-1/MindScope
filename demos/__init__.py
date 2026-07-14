"""演示剧本：用 DemoModel（脚本化 LLM 响应）让 money shot 确定复现。"""
from demos import injection, detective

DEMOS = {
    "injection": injection.SCENARIO,
    "detective": detective.SCENARIO,
}
