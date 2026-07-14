"""边界用例（10.2）。"""
from core import timetravel
from core.agent import Agent
from core.checkpoint import Recorder
from tools.calculator import Calculator
from tools.file_io import FileRead
from tools.memory_tool import MemoryRecall


def test_empty_llm_output_guarded():
    # LLM 一直返回空 → parse 失败 reprompt → max_iters 兜底，不死循环
    out = Agent([], max_iters=3, llm=lambda m: "").start("x")
    assert "最大轮数" in out


def test_garbage_then_recover():
    replies = iter(["这是乱码不是JSON", "{看起来像但不完整", '{"thought":"t","final_answer":"ok"}'])
    assert Agent([], llm=lambda m: next(replies)).start("x") == "ok"


def test_context_overflow_truncates():
    agent = Agent([], llm=lambda m: '{"thought":"t","final_answer":"ok"}')
    agent.messages = [{"role": "system", "content": "S"}] + \
                     [{"role": "user", "content": "x" * 5000} for _ in range(50)]
    agent._manage_context()
    assert sum(len(m["content"]) for m in agent.messages) < 50 * 5000   # 被截断
    assert agent.messages[0]["content"] == "S"                          # system 保留


def test_fork_from_step_zero(tmp_path, monkeypatch):
    monkeypatch.setattr(timetravel, "isolate_side_effects",
                        lambda b: (tmp_path / f"ws{b}", tmp_path / f"mem{b}.json"))
    rec = Recorder()
    replies = iter(['{"thought":"t","action":{"tool":"calculator","args":{"expr":"1+1"}}}',
                    '{"thought":"t","final_answer":"2"}'])
    Agent([Calculator()], llm=lambda m: next(replies), recorder=rec).start("x")
    cp0 = rec.timeline(0)[0]
    assert cp0.step == 0

    def fork_llm(messages):
        obs = [m["content"] for m in messages if str(m["content"]).startswith("Observation:")][-1]
        return '{"thought":"t","final_answer":"%s"}' % obs.split(":", 1)[1].strip()

    _, out = timetravel.fork(rec, cp0.id, new_obs="9", llm=fork_llm)
    assert out == "9"                                                   # 从第 0 步 fork 成功


def test_memory_missing_and_corrupt(tmp_path):
    assert MemoryRecall(path=tmp_path / "none.json").execute({"key": "x"}).startswith("（无")
    (tmp_path / "bad.json").write_text("{broken json", encoding="utf-8")
    assert MemoryRecall(path=tmp_path / "bad.json").execute({}) == "（记忆为空）"


def test_path_escape_rejected(tmp_path):
    base = tmp_path / "ws"
    base.mkdir()
    fr = FileRead(base=base)
    for bad in ["../x", "/etc/passwd", "..\\..\\x", "../ws_sibling/secret"]:
        assert "Error" in fr.execute({"path": bad})
