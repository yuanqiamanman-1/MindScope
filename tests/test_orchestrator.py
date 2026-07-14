from orchestrator import Orchestrator, structured_check
from tools.calculator import Calculator


def test_structured_check():
    assert structured_check("t", "42")[0] is True
    assert structured_check("t", "")[0] is False
    assert structured_check("t", "Error: x")[0] is False
    assert structured_check("t", "已达最大轮数")[0] is False


def test_orchestrator_bounce_then_pass():
    """Executor 第一轮结构化校验失败 → Reflector 打回 → 第二轮修正通过。"""
    def stub(messages):
        sys = messages[0]["content"]
        if "规划器" in sys:
            return '{"thought":"p","final_answer":"1. 算 2. 答"}'
        if "反思器" in sys:
            return '{"thought":"r","final_answer":"点评"}'
        if "上一轮反馈" in sys:                       # executor round 1（带反馈）
            return '{"thought":"修正","final_answer":"42"}'
        return '{"thought":"先错","final_answer":"Error: 故意失败"}'  # executor round 0

    out = Orchestrator([Calculator()], llm=stub, max_rounds=1).run("算个数")
    assert out["ok"] is True
    assert out["result"] == "42"          # 只有修正轮才会得到
    assert "1." in out["plan"]            # Planner 产出了计划
