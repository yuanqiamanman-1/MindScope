from core.agent import Agent
from tools.memory_tool import MemoryStore, summary


def test_summary_injects(tmp_path):
    p = tmp_path / "mem.json"
    MemoryStore(path=p).execute({"key": "专业", "value": "计算机"})
    s = summary(p)
    assert "专业" in s and "计算机" in s


def test_agent_autorecall(tmp_path):
    """记忆里有内容时，Agent 构造即把它注入系统提示词（无需被叫就'想得起来'）。"""
    p = tmp_path / "mem.json"
    MemoryStore(path=p).execute({"key": "专业", "value": "计算机"})
    agent = Agent([], memory_path=p, llm=lambda m: '{"thought":"t","final_answer":"ok"}')
    assert "计算机" in agent.system          # 自动召回：记忆进了系统提示词


def test_no_memory_no_injection(tmp_path):
    p = tmp_path / "empty.json"
    agent = Agent([], memory_path=p, llm=lambda m: '{"thought":"t","final_answer":"ok"}')
    assert "长期记忆" not in agent.system      # 空记忆不注入噪声
