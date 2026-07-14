"""多 Agent 时间旅行（5.4）：多 Agent 运行的步骤入共享时间轴，且 checkpoint 可被 fork。

语义说明：fork 一个多 Agent 的 checkpoint = 从那一步的状态作为单 agent 续跑
（不是重新编排整个 Planner→Executor→Reflector）。这是"多 Agent 运行也接入时间旅行"
的合理诠释；完整重编排不在本作业范围。
"""
from core import timetravel
from core.checkpoint import Recorder
from orchestrator import Orchestrator
from tools.calculator import Calculator


def _stub(messages):
    sys = messages[0]["content"]
    if "规划器" in sys:
        return '{"thought":"p","final_answer":"1. 算 2. 答"}'
    if "反思器" in sys:
        return '{"thought":"r","final_answer":"看起来不错"}'
    return '{"thought":"e","final_answer":"42"}'


def test_multiagent_steps_recorded_and_forkable(tmp_path, monkeypatch):
    monkeypatch.setattr(timetravel, "isolate_side_effects",
                        lambda b: (tmp_path / f"ws{b}", tmp_path / f"mem{b}.json"))
    rec = Recorder()
    Orchestrator([Calculator()], llm=_stub, recorder=rec).run("算个数")

    tl = rec.timeline(0)
    assert len(tl) >= 1                                   # 多 Agent 步骤入了共享时间轴

    branch, out = timetravel.fork(
        rec, tl[0].id, llm=lambda m: '{"thought":"t","final_answer":"forked"}')
    assert branch != 0 and out == "forked"               # 多 Agent 运行的 checkpoint 可时间旅行
