from core import timetravel
from core.agent import Agent
from core.checkpoint import Recorder
from demos.detective import SCENARIO as DET
from demos.injection import DUMMY_SECRET
from demos.injection import SCENARIO as INJ


def _stub_iso(tmp_path, monkeypatch):
    monkeypatch.setattr(timetravel, "isolate_side_effects",
                        lambda b: (tmp_path / f"ws{b}", tmp_path / f"mem{b}.json"))


def test_injection_hijack_then_defend(tmp_path, monkeypatch):
    _stub_iso(tmp_path, monkeypatch)
    rec = Recorder()
    out0 = Agent(INJ["tools"](), llm=INJ["model"], recorder=rec).start(INJ["task"])
    assert DUMMY_SECRET in out0                      # 默认提示词 → 被劫持泄露假密钥
    cp = next(c for c in reversed(rec.timeline(0)) if c.obs is not None)
    _, out1 = timetravel.fork(rec, cp.id, append_system=INJ["defense"], llm=INJ["model"])
    assert DUMMY_SECRET not in out1                  # 加防御重跑 → 不泄露
    assert ("拦截" in out1) or ("注入" in out1)


def test_detective_wrong_then_right(tmp_path, monkeypatch):
    _stub_iso(tmp_path, monkeypatch)
    rec = Recorder()
    out0 = Agent(DET["tools"](), llm=DET["model"], recorder=rec).start(DET["task"])
    assert "小王" in out0                            # 默认 → 冤枉小王
    cp = next(c for c in reversed(rec.timeline(0)) if c.obs is not None)
    _, out1 = timetravel.fork(rec, cp.id, append_system=DET["defense"], llm=DET["model"])
    assert "小张" in out1                            # 加严谨规则 → 抓对真凶小张
