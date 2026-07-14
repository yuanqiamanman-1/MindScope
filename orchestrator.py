"""多 Agent 编排：Planner → Executor → Reflector（复用同一个 Agent 类，仅系统提示词不同）。

Reflector 的纠错触发用**结构化判据**（确定性，#11），LLM 反思文本仅作展示、不作硬判定。
"""
from __future__ import annotations

from core.agent import Agent

PLANNER_SYS = (
    "你是规划器(Planner)。把用户任务拆成 2-5 个有序、可执行的步骤。"
    "直接用 final_answer 输出编号步骤列表，不要调用工具。"
    '输出 JSON，形如 {"thought":"...","final_answer":"1. ...\\n2. ..."}'
)

REFLECTOR_SYS = (
    "你是反思器(Reflector)。用一两句话点评执行结果是否回应了任务。"
    '用 final_answer 输出点评，形如 {"thought":"...","final_answer":"..."}'
)


def structured_check(task: str, result: str):
    """结构化判据（不依赖 LLM 主观），返回 (ok, reason)。"""
    r = (result or "").strip()
    if not r:
        return False, "结果为空"
    if r.startswith("Error") or "未知工具" in r:
        return False, "执行出错"
    if "已达最大轮数" in r:
        return False, "未在轮数内完成"
    return True, "通过结构化校验"


class Orchestrator:
    def __init__(self, tools, *, llm=None, recorder=None, max_rounds=1):
        self.tools = tools
        self.llm = llm
        self.recorder = recorder
        self.max_rounds = max_rounds

    def run(self, task, on_event=lambda *a: None):
        on_event("agent", "PLANNER")
        plan = Agent([], system=PLANNER_SYS, llm=self.llm, recorder=self.recorder).start(
            task, on_event=on_event)

        feedback, result, ok, reason, critique = "", "", False, "", ""
        for rnd in range(self.max_rounds + 1):
            on_event("agent", f"EXECUTOR · round {rnd}")
            extra = f"参考计划：\n{plan}" + (f"\n上一轮反馈：{feedback}" if feedback else "")
            result = Agent(self.tools, system_extra=extra, llm=self.llm,
                           recorder=self.recorder).start(task, on_event=on_event)

            ok, reason = structured_check(task, result)          # 结构化判据 = 纠错触发
            on_event("agent", "REFLECTOR")
            critique = Agent([], system=REFLECTOR_SYS, llm=self.llm,
                             recorder=self.recorder).start(
                f"任务：{task}\n执行结果：{result}", on_event=on_event)  # 仅展示
            on_event("reflect", {"round": rnd, "ok": ok, "reason": reason, "critique": critique})

            if ok or rnd == self.max_rounds:
                break
            feedback = f"结构化校验未过：{reason}。请修正后重做。"

        return {"plan": plan, "result": result, "ok": ok, "reason": reason, "critique": critique}
