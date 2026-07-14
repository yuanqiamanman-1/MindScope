"""多轮续聊 /api/continue 测试（离线确定化 stub）：验证 Codex 修正的语义。

- tip 续 → 接到同一分支末端、原 cp 不变
- 非 tip 续 → 新分支(parent_cp=cp)，且首个新 cp 的 messages **含用户新消息**
  （证明是"直接 resume"，不是 fork 重跑——fork 重跑的首个 cp 不含这句新 user 消息）
- busy → 409
"""
from fastapi.testclient import TestClient

import server
from core.agent import Agent
from core.checkpoint import Recorder


def _stub(messages):
    return '{"thought":"ok","final_answer":"续聊回复"}'


def _finished_rec():
    """模拟跑完的会话：branch0 两个 cp（cp1 是 final，末端）。"""
    rec = Recorder()
    m1 = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    rec.snapshot(0, m1, "sys", {"thought": "t", "action": {"tool": "x", "args": {}}}, "obs", 0)
    m2 = m1 + [{"role": "user", "content": "Observation: obs"}, {"role": "assistant", "content": "答"}]
    rec.snapshot(1, m2, "sys", {"thought": "t2", "final_answer": "答"}, None, 0)
    return rec


def _patch(monkeypatch):
    monkeypatch.setattr(server, "_save_session", lambda sid: None)
    monkeypatch.setattr(server, "_branch_paths", lambda b: (None, None))
    monkeypatch.setattr(server, "_make_agent",
                        lambda s, r, b, ws, mem: Agent([], recorder=r, branch=b, llm=_stub, system="sys"))


def test_continue_tip_extends_same_branch(monkeypatch):
    _patch(monkeypatch)
    rec = _finished_rec()
    server.RUNS["ct1"] = {"recorder": rec, "task": "t", "created": "x", "demo": "", "mode": "single"}
    before = list(rec.branches[0]["cps"])
    r = TestClient(server.app).get("/api/continue?run_id=ct1&cp_id=1&message=继续聊")
    assert r.status_code == 200
    assert len(rec.branches) == 1                          # 没新建分支
    assert rec.branches[0]["cps"][:2] == before            # 原 cp 不变
    assert len(rec.branches[0]["cps"]) == 3                # 追加了 1 个新 cp
    last = rec.get(rec.branches[0]["cps"][-1])
    assert any("继续聊" in str(m.get("content", "")) for m in last.messages)


def test_continue_midnode_new_branch_not_fork(monkeypatch):
    _patch(monkeypatch)
    rec = _finished_rec()
    server.RUNS["ct2"] = {"recorder": rec, "task": "t", "created": "x", "demo": "", "mode": "single"}
    r = TestClient(server.app).get("/api/continue?run_id=ct2&cp_id=0&message=换个说法")
    assert r.status_code == 200
    assert len(rec.branches) == 2                          # cp0 非末端 → 新分支
    nb = max(rec.branches)
    assert rec.branches[nb]["parent_cp"] == 0
    first_new = rec.get(rec.branches[nb]["cps"][0])
    # ★C1 关键：新分支首个 cp 含用户新消息 → 是直接续，不是 fork 重跑
    assert any("换个说法" in str(m.get("content", "")) for m in first_new.messages)


def test_continue_busy_409():
    rec = _finished_rec()
    server.RUNS["ct3"] = {"recorder": rec, "task": "t", "created": "x", "demo": "", "mode": "single", "busy": True}
    r = TestClient(server.app).get("/api/continue?run_id=ct3&cp_id=1&message=x")
    assert r.status_code == 409


def test_continue_bad_cp_404():
    rec = _finished_rec()
    server.RUNS["ct4"] = {"recorder": rec, "task": "t", "created": "x", "demo": "", "mode": "single"}
    r = TestClient(server.app).get("/api/continue?run_id=ct4&cp_id=99&message=x")
    assert r.status_code == 404


def test_continue_records_user_turn(monkeypatch):
    """续聊后，新增 cp 要带上"用户那一轮"输入（玻璃盒据此显示人类发言，不只有输出）。"""
    _patch(monkeypatch)
    rec = _finished_rec()
    server.RUNS["ct6"] = {"recorder": rec, "task": "t", "created": "x", "demo": "", "mode": "single"}
    TestClient(server.app).get("/api/continue?run_id=ct6&cp_id=1&message=继续问一个问题")
    new_cp = rec.get(rec.branches[0]["cps"][-1])
    assert new_cp.user == "继续问一个问题"          # 本轮首个 cp 挂着用户输入
    assert new_cp.to_dict()["user"] == "继续问一个问题"   # 序列化进 tree() 给前端


def test_continue_reconnect_is_noop(monkeypatch):
    """EventSource 断流自动重连同一 GET = 重复续聊（会岔出多余分支、白烧配额）。
    重连请求带 Last-Event-ID 头 → 端点识破，只回 done、零副作用。"""
    _patch(monkeypatch)
    rec = _finished_rec()
    server.RUNS["ct5"] = {"recorder": rec, "task": "t", "created": "x", "demo": "", "mode": "single"}
    before_branches = len(rec.branches)
    before_cps = len(rec.cps)
    r = TestClient(server.app).get(
        "/api/continue?run_id=ct5&cp_id=0&message=换个说法",
        headers={"Last-Event-ID": "7"})
    assert r.status_code == 200
    assert "event: done" in r.text
    assert len(rec.branches) == before_branches            # 没岔分支
    assert len(rec.cps) == before_cps                      # 没新 cp
