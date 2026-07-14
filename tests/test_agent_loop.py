from core.agent import Agent


class StubTool:
    name = "echo"
    description = "回显输入"
    params = {"x": "str"}

    def execute(self, args):
        return f"echoed:{args.get('x')}"


def test_multi_step_then_final():
    replies = iter([
        '{"thought":"先调工具","action":{"tool":"echo","args":{"x":"hi"}}}',
        '{"thought":"够了","final_answer":"final-42"}',
    ])
    agent = Agent([StubTool()], llm=lambda msgs: next(replies))
    out = agent.start("做这件事")
    assert out == "final-42"
    # Observation 被回灌进上下文
    assert any("echoed:hi" in m["content"] for m in agent.messages)


def test_unknown_tool_recovers():
    replies = iter([
        '{"thought":"调个不存在的","action":{"tool":"nope","args":{}}}',
        '{"thought":"算了","final_answer":"done"}',
    ])
    agent = Agent([StubTool()], llm=lambda msgs: next(replies))
    out = agent.start("x")
    assert out == "done"
    assert any("未知工具" in m["content"] for m in agent.messages)


def test_malformed_json_reprompts():
    replies = iter([
        "这不是 JSON",
        '{"thought":"补救","final_answer":"ok"}',
    ])
    agent = Agent([StubTool()], llm=lambda msgs: next(replies))
    out = agent.start("x")
    assert out == "ok"
    assert any("合法 JSON" in m["content"] for m in agent.messages)


def test_max_iters_guard():
    # 永远只调工具、不给 final_answer → 必须被 max_iters 拦住
    agent = Agent(
        [StubTool()],
        max_iters=3,
        llm=lambda msgs: '{"thought":"loop","action":{"tool":"echo","args":{"x":"a"}}}',
    )
    out = agent.start("x")
    assert "最大轮数" in out
