"""时间旅行：从某 checkpoint 回退 → 改提示词/观察值 → fork 重跑（新分支，原分支保留）。"""
from __future__ import annotations

import copy

import config
from core.agent import Agent
from core.isolation import isolate_side_effects
from tools.registry import default_tools


def fork(recorder, cp_id, *, new_system=None, append_system=None, new_obs=None,
         max_iters=None, llm=None, on_event=None):
    """从 cp_id 的（可编辑）状态分叉重跑。

    - new_system: 整体替换系统提示词；append_system: 在原系统提示词后追加一条规则（注入防御演示用）。
    - new_obs: 改写该 checkpoint 最后一条 Observation 的内容。
    返回 (new_branch_id, final_answer)。原分支不受影响（深拷贝 + 分支隔离）。
    """
    on_event = on_event or (lambda *a: None)
    cp = recorder.get(cp_id)
    messages = copy.deepcopy(cp.messages)

    if new_obs is not None:
        for m in reversed(messages):
            if m.get("role") == "user" and str(m.get("content", "")).startswith("Observation:"):
                m["content"] = f"Observation: {new_obs}"
                break

    system = new_system if new_system is not None else cp.system
    if append_system:
        system = system + "\n- " + append_system

    branch = recorder.new_branch(parent_cp=cp_id)
    ws, mem = isolate_side_effects(branch)
    tools = default_tools(file_base=ws, memory_path=mem)
    agent = Agent(tools, max_iters=max_iters or config.MAX_ITERS,
                  llm=llm, recorder=recorder, branch=branch, memory_path=mem)
    # 把"这条分支改了什么提示词"记进首个 cp，玻璃盒里看得见（哪怕模型无视它）
    rule_turn = append_system or (f"整体替换系统提示词" if new_system is not None else None)
    final = agent.resume_from(messages, system, branch, on_event=on_event, rule_turn=rule_turn)
    return branch, final
