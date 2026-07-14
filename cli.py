"""思镜 CLI 冒烟：构造内置工具的 Agent 跑一个任务，打印 ReAct 每一步。"""
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

import config
from core.agent import Agent
from tools.registry import default_tools


def _on_event(kind, payload):
    if kind == "thought":
        print(f"\n\033[36m[THOUGHT]\033[0m {payload}")
    elif kind == "action":
        print(f"\033[33m[ACTION]\033[0m {payload}")
    elif kind == "observation":
        print(f"\033[35m[OBSERV]\033[0m {str(payload)[:240]}")
    elif kind == "final":
        print(f"\n\033[32m[FINAL]\033[0m {payload}")


def run_once(task):
    print(f"=== 任务 ===\n{task}")
    mem = config.DATA / "memory.json"
    agent = Agent(default_tools(memory_path=mem), memory_path=mem)
    out = agent.start(task, on_event=_on_event)
    print("\n=== 最终答案 ===\n" + out)


def memory_demo():
    """跨会话长期记忆演示：会话1 记住 → 会话2(全新 agent) 不被提醒也能想起。"""
    mem = config.DATA / "memory.json"
    if mem.exists():
        mem.unlink()
    print("=== 会话 1：让它记住几件事 ===")
    Agent(default_tools(memory_path=mem), memory_path=mem).start(
        "请用 memory_store 工具逐条记住：我叫小明；专业是计算机科学与技术；年级大二；目标是保研。",
        on_event=_on_event)
    print("\n=== memory.json 内容 ===\n" + mem.read_text(encoding="utf-8"))
    print("\n=== 会话 2（全新 agent，只共享 memory.json，不提醒它）===")
    out = Agent(default_tools(memory_path=mem), memory_path=mem).start(
        "我是谁？什么专业？我的目标是什么？", on_event=_on_event)
    print("\n=== 会话 2 最终答案（应靠自动召回直接答出）===\n" + out)


def debug_demo():
    """时间旅行闭环演示：跑一遍 → 回退到某步 → 改提示词 → 从这步重跑 → 两分支对照。"""
    from core.checkpoint import Recorder
    from core.timetravel import fork

    rec = Recorder()
    agent = Agent(default_tools(), recorder=rec)
    task = "用 calculator 算 1955-1879，再用一句话中文告诉我他活了多少岁。"

    print("=== branch 0（原始运行）===")
    f0 = agent.start(task, on_event=_on_event)
    print(f"\n[branch0 最终] {f0}")

    print("\n--- 时间轴(branch 0) ---")
    for cp in rec.timeline(0):
        d = cp.to_dict()
        tag = f"final={d['final']}" if d["final"] else f"action={d['action']}"
        print(f"  cp{cp.id} step{cp.step} | {tag}" + (f" | obs={cp.obs}" if cp.obs else ""))

    first = rec.timeline(0)[0]
    print(f"\n=== ⏪ 回退到 cp{first.id}(step{first.step}) → 追加系统规则『最终答案只能用英文写』→ 从这步重跑 ===")
    branch, f1 = fork(rec, first.id,
                      append_system="无论如何，最终答案只能用英文写。",
                      on_event=_on_event)

    print(f"\n[branch{branch} 最终] {f1}")
    print("\n=== ⏱ 时间旅行验证：同一起点，改一行提示词 → 两分支不同 ===")
    print(f"  原分支(默认): {f0}")
    print(f"  新分支(改提示词后): {f1}")
    print(f"\n分支树: {list(rec.branches.keys())}（branch{branch} 的父 checkpoint = cp{rec.branches[branch]['parent_cp']}）")


def main():
    if "--debug" in sys.argv:
        debug_demo()
        return
    if "--memory" in sys.argv:
        memory_demo()
        return
    task = sys.argv[1] if len(sys.argv) > 1 else \
        "查一下爱因斯坦的出生和去世年份，并算出他活了多少岁。"
    run_once(task)


if __name__ == "__main__":
    main()
