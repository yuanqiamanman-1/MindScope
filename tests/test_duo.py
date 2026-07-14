"""对戏剧场 DUO 后端测试（stub 流式确定化）。"""
from fastapi.testclient import TestClient

import server
from core import duo


def _sess():
    return {"A": {"name": "甲", "persona": "乐观"},
            "B": {"name": "乙", "persona": "悲观"},
            "scene": "天台对话", "transcript": [], "turn": "A", "busy": False}


# —— build_messages 视角映射 ——
def test_build_messages_empty_kickoff():
    msgs = duo.build_messages(_sess(), "A")
    assert msgs[0]["role"] == "system" and "甲" in msgs[0]["content"]
    assert msgs[-1]["role"] == "user"                  # 空 transcript→补开场 user
    assert "开口" in msgs[-1]["content"]


def test_build_messages_role_mapping():
    s = _sess()
    s["transcript"] = [{"who": "A", "name": "甲", "text": "你好"},
                       {"who": "B", "name": "乙", "text": "哼"}]
    s["turn"] = "A"
    msgs = duo.build_messages(s, "A")               # 从甲视角：甲=assistant，乙=user
    assert msgs[1] == {"role": "assistant", "content": "你好"}
    assert msgs[2]["role"] == "user" and "乙：哼" in msgs[2]["content"]
    assert msgs[-1]["role"] == "user"


def test_build_messages_narrator_is_user():
    s = _sess()
    s["transcript"] = [{"who": "narrator", "name": "旁白", "text": "天黑了"}]
    msgs = duo.build_messages(s, "B")
    assert msgs[-1]["role"] == "user" and "（旁白：天黑了）" in msgs[-1]["content"]


def test_coalesce_merges_same_role():
    s = _sess()
    s["transcript"] = [{"who": "B", "name": "乙", "text": "一"},
                       {"who": "narrator", "name": "旁白", "text": "二"}]
    msgs = duo.build_messages(s, "A")               # 乙(user)+旁白(user) 连续→合并
    users = [m for m in msgs if m["role"] == "user"]
    assert len(users) == 1 and "乙：一" in users[0]["content"] and "旁白：二" in users[0]["content"]


# —— 端点 ——
def _stub_stream(monkeypatch, text="嗯。"):
    monkeypatch.setattr(server, "chat_stream", lambda messages, **k: iter(list(text)))


def test_duo_start_and_step(monkeypatch):
    _stub_stream(monkeypatch, "你好呀")
    c = TestClient(server.app)
    r = c.get("/api/duo/start?nameA=甲&personaA=乐观&nameB=乙&personaB=悲观&scene=天台")
    assert "event: started" in r.text
    sid = [k for k in server.DUOS][-1]
    r2 = c.get(f"/api/duo/step?sid={sid}").text
    assert "event: turn" in r2
    sess = server.DUOS[sid]
    assert sess["transcript"][0] == {"who": "A", "name": "甲", "text": "你好呀"}
    assert sess["turn"] == "B"                        # 翻面
    c.get(f"/api/duo/step?sid={sid}")                 # 乙说一句
    assert server.DUOS[sid]["transcript"][1]["who"] == "B"
    assert server.DUOS[sid]["turn"] == "A"


def test_duo_inject(monkeypatch):
    _stub_stream(monkeypatch)
    c = TestClient(server.app)
    c.get("/api/duo/start?nameA=甲&nameB=乙")
    sid = [k for k in server.DUOS][-1]
    c.get(f"/api/duo/inject?sid={sid}&text=突然下雨了")
    e = server.DUOS[sid]["transcript"][-1]
    assert e["who"] == "narrator" and e["text"] == "突然下雨了" and e["target"] == "all"
    # 私语：只塞给 B
    c.get(f"/api/duo/inject?sid={sid}&text=别信他&target=B")
    assert server.DUOS[sid]["transcript"][-1]["target"] == "B"


# —— 结构化 turn / 关系累加 ——
def test_parse_turn_json_and_degrade():
    t = duo.parse_turn('{"reply":"哼","os":"心里想啥","tactic":"激将","rel_delta":8}')
    assert t["ok"] and t["reply"] == "哼" and t["tactic"] == "激将" and t["rel_delta"] == 8
    bad = duo.parse_turn("这不是JSON只是台词")        # 0 调用降级：原文当台词
    assert bad["ok"] is False and bad["reply"] == "这不是JSON只是台词" and bad["rel_delta"] == 0
    clamp = duo.parse_turn('{"reply":"x","rel_delta":999,"tactic":"瞎编的招"}')
    assert clamp["rel_delta"] == 15 and clamp["tactic"] == ""    # 越界夹紧、非法招剔除


def test_parse_turn_labeled_fallback():
    # 模型吐 markdown 标签字段（非 JSON）→ 兜底也能抓到 os/tactic/rel
    md = '**reply:** （冷笑）随你便。\n**os:** 嘴上赶人心里盼留。\n**tactic:** 激将\n**rel_delta:** -3'
    t = duo.parse_turn(md)
    assert t["ok"] and "随你便" in t["reply"] and t["tactic"] == "激将" and t["rel_delta"] == -3
    assert "盼留" in t["os"]
    # 台词写在标签前(没写 reply:) → 开场白即台词，不能把 os:/tactic: 也带进台词
    pre = '（凝视字迹）有些字写给活人看。\nos: 我本该说再见。\ntactic: 质问\nrel_delta: 7'
    t2 = duo.parse_turn(pre)
    assert t2["reply"] == "（凝视字迹）有些字写给活人看。" and t2["tactic"] == "质问" and t2["rel_delta"] == 7
    assert "os:" not in t2["reply"] and "tactic:" not in t2["reply"]


def test_apply_rel_accumulates_clamp():
    assert duo.apply_rel(50, {"rel_delta": 10}) == 60
    assert duo.apply_rel(95, {"rel_delta": 15}) == 100
    assert duo.apply_rel(5, {"rel_delta": -15}) == 0


def test_duo_step_updates_rel_and_tree(monkeypatch):
    _stub_stream(monkeypatch, '{"reply":"你好","os":"试探一下","tactic":"试探","rel_delta":6}')
    c = TestClient(server.app)
    c.get("/api/duo/start?nameA=甲&nameB=乙&scene=天台")
    sid = [k for k in server.DUOS][-1]
    r = c.get(f"/api/duo/step?sid={sid}").text
    assert '"tactic": "试探"' in r and '"rel": 56' in r          # 50+6，turn 事件带 os/tactic/rel
    sess = server.DUOS[sid]
    assert sess["rel"] == 56
    # 落进世界树：根 cp + 这一轮 = 2 个 cp
    assert len(sess["rec"].cps) == 2
    assert sess["rec"].get(1).state["rel"] == 56 and sess["rec"].get(1).state["tactic"] == "试探"


def test_duo_fork_branches_and_restores(monkeypatch):
    _stub_stream(monkeypatch, '{"reply":"嗯","os":"o","tactic":"共情","rel_delta":10}')
    c = TestClient(server.app)
    c.get("/api/duo/start?nameA=甲&nameB=乙")
    sid = [k for k in server.DUOS][-1]
    c.get(f"/api/duo/step?sid={sid}")                  # cp1, rel=60
    c.get(f"/api/duo/step?sid={sid}")                  # cp2, rel=70
    rec = server.DUOS[sid]["rec"]
    nb = len(rec.branches)
    # 读档回 cp1(rel=60)，给 B 塞秘密
    r = c.get(f"/api/duo/fork?sid={sid}&cp_id=1&target=B&secret=其实你在骗他").json()
    assert r["ok"] and r["rel"] == 60                  # 从 cp1 的关系值起跳
    assert len(rec.branches) == nb + 1                 # 新枝
    assert "其实你在骗他" in server.DUOS[sid]["B"]["secret"]   # 秘密塞进 B 的人设
    assert server.DUOS[sid]["branch"] == r["branch"]
    assert rec.get(2).state["rel"] == 70               # 原枝 cp2 不变


def test_duo_timeline(monkeypatch):
    _stub_stream(monkeypatch, '{"reply":"嗯","os":"o","tactic":"共情","rel_delta":5}')
    c = TestClient(server.app)
    c.get("/api/duo/start?nameA=甲&nameB=乙")
    sid = [k for k in server.DUOS][-1]
    c.get(f"/api/duo/step?sid={sid}")
    tl = c.get(f"/api/duo/timeline?sid={sid}").json()
    assert "0" in tl and len(tl["0"]["steps"]) == 2    # 根 + 1 轮


def test_duo_step_reconnect_no_advance(monkeypatch):
    _stub_stream(monkeypatch)
    c = TestClient(server.app)
    c.get("/api/duo/start?nameA=甲&nameB=乙")
    sid = [k for k in server.DUOS][-1]
    before = len(server.DUOS[sid]["transcript"])
    r = c.get(f"/api/duo/step?sid={sid}", headers={"Last-Event-ID": "2"})
    assert r.status_code == 200 and "event: done" in r.text
    assert len(server.DUOS[sid]["transcript"]) == before   # 重连=不推进
    assert server.DUOS[sid]["turn"] == "A"


def test_duo_step_bad_sid():
    c = TestClient(server.app)
    assert c.get("/api/duo/step?sid=nope").status_code == 404
