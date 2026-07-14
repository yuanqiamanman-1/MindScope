from tools.calculator import Calculator
from tools.file_io import FileRead, FileWrite
from tools.memory_tool import MemoryStore, MemoryRecall


def test_calculator():
    c = Calculator()
    assert abs(float(c.execute({"expr": "(3.8*152-3.62*96)/56"})) - 4.107) < 0.01
    assert "Error" in c.execute({"expr": "__import__('os')"})  # 拒绝任意代码


def test_file_roundtrip_and_sandbox(tmp_path):
    base = tmp_path / "ws"
    base.mkdir()
    w = FileWrite(base=base)
    r = FileRead(base=base)
    w.execute({"path": "a/b.txt", "content": "hi"})
    assert r.execute({"path": "a/b.txt"}) == "hi"
    assert "Error" in w.execute({"path": "../evil.txt", "content": "x"})
    assert "Error" in r.execute({"path": "/etc/passwd"})


def test_file_sibling_prefix(tmp_path):
    # is_relative_to 修复点：sibling 目录前缀相同（ws vs ws_evil）必须被拒
    base = tmp_path / "ws"
    base.mkdir()
    (tmp_path / "ws_evil").mkdir()
    assert "Error" in FileRead(base=base).execute({"path": "../ws_evil/secret.txt"})


def test_memory(tmp_path):
    p = tmp_path / "mem.json"
    MemoryStore(path=p).execute({"key": "major", "value": "CS"})
    assert MemoryRecall(path=p).execute({"key": "major"}) == "CS"  # 新实例=新会话
    assert MemoryRecall(path=tmp_path / "none.json").execute({"key": "x"}).startswith("（无")
    (tmp_path / "bad.json").write_text("{not json", encoding="utf-8")
    assert MemoryRecall(path=tmp_path / "bad.json").execute({}) == "（记忆为空）"
