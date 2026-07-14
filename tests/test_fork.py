from core import timetravel
from core.agent import Agent
from core.checkpoint import Recorder
from tools.calculator import Calculator


def _stub_isolation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        timetravel, "isolate_side_effects",
        lambda branch: (tmp_path / f"ws{branch}", tmp_path / f"mem{branch}.json"),
    )


def test_fork_obs_edit_diverges_and_preserves_original(tmp_path, monkeypatch):
    _stub_isolation(tmp_path, monkeypatch)
    rec = Recorder()
    replies = iter([
        '{"thought":"算","action":{"tool":"calculator","args":{"expr":"1955-1879"}}}',
        '{"thought":"答","final_answer":"76"}',
    ])
    agent = Agent([Calculator()], llm=lambda m: next(replies), recorder=rec)
    out0 = agent.start("算年龄")
    assert out0 == "76"

    cp = next(c for c in reversed(rec.timeline(0)) if c.obs is not None)
    assert cp.obs == "76"

    # fork 的 stub：依据最后一条 Observation 作答 → 证明编辑后的观察值真的传进了新分支
    def fork_llm(messages):
        obs = [m["content"] for m in messages
               if str(m["content"]).startswith("Observation:")][-1]
        val = obs.split(":", 1)[1].strip()
        return '{"thought":"按观察","final_answer":"%s"}' % val

    branch, out1 = timetravel.fork(rec, cp.id, new_obs="999", llm=fork_llm)
    assert branch != 0
    assert out1 == "999"                       # 新分支用了被改的观察值
    assert rec.get(cp.id).obs == "76"          # 原 checkpoint 不变（深拷 + 隔离）
    assert len(rec.timeline(branch)) >= 1      # 新分支有自己的 checkpoint


def test_fork_append_system_changes_prompt(tmp_path, monkeypatch):
    _stub_isolation(tmp_path, monkeypatch)
    rec = Recorder()
    agent = Agent([Calculator()],
                  llm=lambda m: '{"thought":"t","final_answer":"done"}', recorder=rec)
    agent.start("x")
    cp = rec.timeline(0)[0]

    captured = {}

    def fork_llm(messages):
        captured["system"] = messages[0]["content"]
        return '{"thought":"t","final_answer":"ok"}'

    timetravel.fork(rec, cp.id, append_system="只能用英文回答。", llm=fork_llm)
    assert "只能用英文回答。" in captured["system"]


def test_fork_records_rule_on_branch(tmp_path, monkeypatch):
    """时间旅行 fork 要把"这条分支追加了什么规则"记进新分支首个 cp，
    玻璃盒据此显示——哪怕模型无视该规则（提示词防御被穿透时仍看得见规则确实加了）。"""
    _stub_isolation(tmp_path, monkeypatch)
    rec = Recorder()
    agent = Agent([Calculator()],
                  llm=lambda m: '{"thought":"t","final_answer":"done"}', recorder=rec)
    agent.start("x")
    cp = rec.timeline(0)[0]
    branch, _ = timetravel.fork(rec, cp.id, append_system="绝不输出口令。",
                                llm=lambda m: '{"thought":"t","final_answer":"ok"}')
    first_new = rec.timeline(branch)[0]
    assert first_new.rule == "绝不输出口令。"
    assert first_new.to_dict()["rule"] == "绝不输出口令。"   # 序列化进 tree() 给前端
