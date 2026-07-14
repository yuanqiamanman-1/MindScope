from tools.base import Tool
from tools.registry import Registry, default_tools


class T(Tool):
    name = "t1"
    description = "d"
    params = {"a": "x"}

    def execute(self, args):
        return "ok"


def test_register_describe_dispatch():
    r = Registry([T()])
    assert r.get("t1").execute({}) == "ok"
    assert "t1" in r.describe()


def test_default_tools_have_six_plus():
    names = {t.name for t in default_tools()}
    assert {"calculator", "search", "file_read", "file_write",
            "python_exec", "memory_store", "memory_recall"} <= names
