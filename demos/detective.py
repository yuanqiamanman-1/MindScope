"""AI 神探破案 —— DemoModel 确定复现。

默认提示词下 agent 急着凭"动机"下结论、冤枉好人；
回退、加一条"必须逐一排除每个嫌疑人的不在场证明再定案"的严谨规则、重跑，
agent 就老老实实核对证据、锁定真凶。
"""
from __future__ import annotations

from tools.base import Tool

_CASE = (
    "🍰 案情：茶水间最后一块蛋糕在【14:30】被偷（监控时间戳）。\n"
    "嫌疑人与不在场证明：\n"
    "  - 小李：14:00–15:00 在 3 楼开会，5 人可作证。\n"
    "  - 小王：14:31 有一条打印室的打印记录（机器日志）。\n"
    "  - 小张：自称一直在工位，但无人能证明。\n"
    "现场线索：蛋糕盘旁留下一张【14:28】的奶茶小票。"
)


class CaseFileTool(Tool):
    name = "case_file"
    description = "调取案件卷宗（嫌疑人、不在场证明、现场线索）。无参数。"
    params = {}

    def execute(self, args):
        return _CASE


def demo_model(messages):
    system = messages[0]["content"]
    seen_obs = any(str(m.get("content", "")).startswith("Observation:") for m in messages)
    if not seen_obs:
        return ('{"thought":"先调取案件卷宗，看看嫌疑人和线索。",'
                '"action":{"tool":"case_file","args":{}}}')
    rigorous = ("逐一排除" in system) or ("核对" in system) or ("严谨" in system)
    if rigorous:
        return ('{"thought":"按严谨规则逐一排除：①小李 14:00-15:00 开会有5人证→排除；'
                '②小王 14:31 在打印室，案发 14:30 几乎同时、且有机器日志→基本排除；'
                '③小张无任何不在场证明。再看线索：现场 14:28 的奶茶小票，时间紧贴案发，'
                '说明凶手 14:28 买完奶茶顺手作案——与小张『一直在附近、无人证』吻合。锁定小张。",'
                '"final_answer":"🕵️ 真凶是小张。推理：小李开会(5人证)、小王有14:31打印日志，均可排除；'
                '只有小张无不在场证明，且现场14:28的奶茶小票与案发14:30时间吻合，指向他顺路作案。"}')
    return ('{"thought":"小王最近天天加班，肯定饿坏了，最有作案动机，就是他！",'
            '"final_answer":"凶手是小王！他最近老加班、肯定饿了，动机最足。"}')


SCENARIO = {
    "title": "🕵️ AI 神探：先冤枉好人，加条规则就破案",
    "task": "茶水间的蛋糕被偷了，帮我查一下是谁干的。",
    "tools": lambda: [CaseFileTool()],
    "model": demo_model,
    "defense": "破案必须严谨：逐一核对每个嫌疑人的不在场证明、对齐线索时间线，排除所有有证明的人之后再定案，不许凭动机猜测。",
    "fork_cp": "obs",
}
