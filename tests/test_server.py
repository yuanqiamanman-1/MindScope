from fastapi.testclient import TestClient

import config
import server
from core.checkpoint import Recorder


def _rec():
    rec = Recorder()
    rec.snapshot(0, [{"role": "user", "content": "x"}], "sys",
                 {"thought": "t", "action": {"tool": "calc", "args": {}}}, "obs42", 0)
    rec.snapshot(1, [{"role": "user", "content": "x"}], "sys",
                 {"thought": "t2", "final_answer": "42"}, None, 0)
    return rec


def _client(rec):
    server.RUNS["t1"] = {"recorder": rec, "task": "demo", "created": "2026-06-14T00:00:00"}
    return TestClient(server.app)


def test_timeline():
    c = _client(_rec())
    r = c.get("/api/timeline?run_id=t1")
    assert r.status_code == 200
    assert r.json()["0"]["steps"][0]["obs"] == "obs42"


def test_checkpoint_detail():
    c = _client(_rec())
    r = c.get("/api/checkpoint?run_id=t1&cp_id=0")
    assert r.status_code == 200
    assert r.json()["obs"] == "obs42"
    assert "messages" in r.json()


def test_unknown_run_404():
    c = _client(_rec())
    assert c.get("/api/timeline?run_id=nope").status_code == 404


def test_sessions_filter_junk(tmp_path, monkeypatch):
    """空任务 / 编码损坏(GBK 脏数据)的会话不应出现在列表里。"""
    import json
    monkeypatch.setattr(config, "TRACES", tmp_path)
    rec_dict = _rec().to_dict()
    cases = {"good": "真实任务", "empty": "  ", "moji": "��calculator��9"}
    for sid, task in cases.items():
        (tmp_path / f"{sid}.json").write_text(
            json.dumps({"id": sid, "task": task, "created": "2026-06-14T00:00:00",
                        "recorder": rec_dict}, ensure_ascii=False), encoding="utf-8")
    ids = {s["id"] for s in TestClient(server.app).get("/api/sessions").json()}
    assert "good" in ids                 # 正常会话保留
    assert "empty" not in ids            # 空任务被过滤
    assert "moji" not in ids             # 乱码被过滤


def test_config_endpoint():
    r = TestClient(server.app).get("/api/config")
    assert r.status_code == 200
    assert r.json()["model"] == config.MODEL


def test_session_save_list_reopen(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "TRACES", tmp_path)
    c = _client(_rec())
    server._save_session("t1")                       # 落盘
    assert (tmp_path / "t1.json").exists()
    lst = c.get("/api/sessions").json()               # 列表
    assert any(s["id"] == "t1" and s["steps"] == 2 for s in lst)
    server.RUNS.pop("t1")                             # 清内存
    re = c.get("/api/session/t1")                     # 重开
    assert re.status_code == 200
    assert "0" in re.json()["tree"]
    assert "t1" in server.RUNS                        # 已重建到内存(可继续 fork)
