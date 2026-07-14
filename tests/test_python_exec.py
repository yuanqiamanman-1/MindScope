from tools.python_exec import PythonExec


def test_print():
    assert PythonExec().execute({"code": "print(1+1)"}) == "2"


def test_no_key_leak(monkeypatch):
    monkeypatch.setenv("MODELSCOPE_API_KEY", "ms-supersecret")
    out = PythonExec().execute(
        {"code": "import os; print(os.environ.get('MODELSCOPE_API_KEY'))"})
    assert "supersecret" not in out  # 密钥被剥离，子进程拿不到


def test_timeout():
    assert "超时" in PythonExec().execute({"code": "\nwhile True:\n    pass\n"})
