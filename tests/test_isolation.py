import config
from core.isolation import isolate_side_effects


def test_branch_isolation(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    data = tmp_path / "data"
    ws.mkdir()
    data.mkdir()
    (ws / "orig.txt").write_text("hi", encoding="utf-8")
    monkeypatch.setattr(config, "WORKSPACE", ws)
    monkeypatch.setattr(config, "DATA", data)

    bws, mem = isolate_side_effects(1)
    assert (bws / "orig.txt").read_text(encoding="utf-8") == "hi"   # 拿到原 workspace 副本

    (bws / "new.txt").write_text("x", encoding="utf-8")
    assert not (ws / "new.txt").exists()                            # 写分支不污染原 workspace
    assert str(mem).endswith("memory_branch_1.json")
