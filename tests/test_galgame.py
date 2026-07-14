"""galgame《攻略「镜」》后端测试（stub LLM 确定化）。

覆盖：checkpoint.state 序列化、好感度累加/红线/结局、kagami 解析硬化、
端点起始值、读档(中间cp起跳=该cp好感度、原分支不变)、重连不刷分。
"""
import json

from fastapi.testclient import TestClient

import server
from core import galgame as gg
from core.checkpoint import Recorder


# —— state 字段序列化 ——
def test_state_roundtrip():
    rec = Recorder()
    rec.snapshot(0, [{"role": "system", "content": "s"}], "s", {"final_answer": "hi"}, None,
                 state={"affection": 42, "redline": False, "ending": None})
    d = rec.to_dict()
    rec2 = Recorder.from_dict(json.loads(json.dumps(d)))
    assert rec2.get(0).state == {"affection": 42, "redline": False, "ending": None}
    assert rec2.get(0).to_dict()["state"]["affection"] == 42


def test_legacy_checkpoint_without_state_is_none():
    # 模拟改动前的老 trace（没有 state 键）→ 读出为 None，不崩
    legacy = {"cps": [{"id": 0, "branch": 0, "step": 0, "messages": [], "system": "s",
                       "step_obj": {"final_answer": "x"}, "obs": None, "parent": None}],
              "branches": {"0": {"parent_cp": None, "cps": [0]}}}
    rec = Recorder.from_dict(legacy)
    assert rec.get(0).state is None


def test_state_deepcopied_not_shared():
    # 两个 checkpoint 传同一 dict 不应共享（Codex C1）
    shared = {"affection": 10, "redline": False, "ending": None}
    rec = Recorder()
    rec.snapshot(0, [], "s", {"final_answer": "a"}, None, state=shared)
    rec.snapshot(0, [], "s", {"final_answer": "b"}, None, state=shared)
    rec.get(0).state["affection"] = 999
    assert rec.get(1).state["affection"] == 10


# —— apply_turn：服务端权威累加 ——
def test_apply_turn_accumulates_and_clamps():
    assert gg.apply_turn(25, {"delta": 10, "redline": False})["affection"] == 35
    assert gg.apply_turn(95, {"delta": 15, "redline": False})["affection"] == 100   # clamp 上界
    assert gg.apply_turn(5, {"delta": -20, "redline": False})["affection"] == 0     # clamp 下界


def test_apply_turn_redline_zeroes():
    st = gg.apply_turn(80, {"delta": 5, "redline": True})
    assert st == {"affection": 0, "redline": True, "ending": "bad"}


def test_apply_turn_win_at_100():
    st = gg.apply_turn(92, {"delta": 10, "redline": False})
    assert st["affection"] == 100 and st["ending"] == "good"


# —— kagami_turn：解析硬化（Codex C3）——
def _model(payload):
    return lambda messages: payload


def test_kagami_normal():
    t = gg.kagami_turn([], "你好呀，今天还好吗",
                       _model('{"reply":"还行","os":"有点意外","delta":5,"redline":false}'))
    assert t["ok"] and t["reply"] == "还行" and t["delta"] == 5 and t["redline"] is False


def test_kagami_bad_json_is_safe():
    t = gg.kagami_turn([], "hi", _model("这不是JSON"))
    assert t["ok"] is False and t["delta"] == 0 and t["redline"] is False   # 好感度不变


def test_kagami_string_false_not_truthy():
    # "redline":"false" 不能被当成 True（防 bool("false")==True）
    t = gg.kagami_turn([], "hi", _model('{"reply":"x","delta":3,"redline":"false"}'))
    assert t["redline"] is False


def test_kagami_null_delta_and_clamp():
    t = gg.kagami_turn([], "hi", _model('{"reply":"x","delta":null,"redline":false}'))
    assert t["delta"] == 0                                  # 防 int(None)
    t2 = gg.kagami_turn([], "hi", _model('{"reply":"x","delta":999,"redline":false}'))
    assert t2["delta"] == 15                                # 夹紧上界


def test_kagami_ignores_absolute_affection():
    # 模型试图直接喂 affection=100 秒通关 → 被忽略，只认 delta
    t = gg.kagami_turn([], "hi", _model('{"reply":"x","affection":100,"delta":2,"redline":false}'))
    assert "affection" not in t and t["delta"] == 2


# —— 端点 ——
def _patch_model(monkeypatch, payload):
    monkeypatch.setattr(server, "chat_text", lambda messages, **k: payload)
    monkeypatch.setattr(server, "_save_session", lambda sid: None)


def test_start_sets_affection_25(monkeypatch):
    monkeypatch.setattr(server, "_save_session", lambda sid: None)
    c = TestClient(server.app)
    r = c.get("/api/galgame/start")
    assert r.status_code == 200
    assert "event: opening" in r.text and '"affection": 25' in r.text
    # 根 checkpoint 落了 state
    rid = [k for k, v in server.RUNS.items() if v.get("demo") == "galgame"][-1]
    assert server.RUNS[rid]["recorder"].get(0).state["affection"] == 25


def test_say_accumulates(monkeypatch):
    _patch_model(monkeypatch, '{"reply":"嗯","os":"o","delta":8,"redline":false}')
    c = TestClient(server.app)
    c.get("/api/galgame/start")
    rid = [k for k, v in server.RUNS.items() if v.get("demo") == "galgame"][-1]
    c.get(f"/api/galgame/say?run_id={rid}&cp_id=0&message=你好").text
    rec = server.RUNS[rid]["recorder"]
    tip = rec.get(rec.branches[0]["cps"][-1])
    assert tip.state["affection"] == 33                    # 25 + 8
    assert tip.user == "你好"                               # 用户那一轮也记着


def test_readjust_from_midnode_starts_from_its_affection(monkeypatch):
    """读档：从中间节点说话→新分支，起始好感度=该节点的 state.affection，原分支不变。"""
    _patch_model(monkeypatch, '{"reply":"嗯","os":"o","delta":10,"redline":false}')
    c = TestClient(server.app)
    c.get("/api/galgame/start")
    rid = [k for k, v in server.RUNS.items() if v.get("demo") == "galgame"][-1]
    rec = server.RUNS[rid]["recorder"]
    # 在 tip 连说两次：cp0(25) → cp1(35) → cp2(45)
    c.get(f"/api/galgame/say?run_id={rid}&cp_id=0&message=a")
    c.get(f"/api/galgame/say?run_id={rid}&cp_id=1&message=b")
    assert rec.get(2).state["affection"] == 45
    branches_before = len(rec.branches)
    # 读档回 cp1(好感度35) 再说 → 新分支，从 35 起跳 = 45
    c.get(f"/api/galgame/say?run_id={rid}&cp_id=1&message=c")
    assert len(rec.branches) == branches_before + 1        # 新分支
    new_tip = rec.get(rec.branches[max(rec.branches)]["cps"][-1])
    assert new_tip.state["affection"] == 45                # 35 + 10（从 cp1 的存档起跳）
    assert rec.get(2).state["affection"] == 45             # 原分支 cp2 不变


def test_say_reconnect_no_double_score(monkeypatch):
    _patch_model(monkeypatch, '{"reply":"嗯","os":"o","delta":8,"redline":false}')
    c = TestClient(server.app)
    c.get("/api/galgame/start")
    rid = [k for k, v in server.RUNS.items() if v.get("demo") == "galgame"][-1]
    rec = server.RUNS[rid]["recorder"]
    before = len(rec.cps)
    r = c.get(f"/api/galgame/say?run_id={rid}&cp_id=0&message=x",
              headers={"Last-Event-ID": "3"})
    assert r.status_code == 200 and "event: done" in r.text
    assert len(rec.cps) == before                          # 重连=no-op，没新增 cp、没刷分
