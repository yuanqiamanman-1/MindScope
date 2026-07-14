from core.checkpoint import Recorder


def test_snapshots_are_deepcopied():
    rec = Recorder()
    msgs = [{"role": "user", "content": "a"}]
    rec.snapshot(0, msgs, "sys", {"thought": "t", "action": {}}, "obs", 0)
    msgs[0]["content"] = "MUTATED"             # 改原始 messages
    assert rec.get(0).messages[0]["content"] == "a"   # 快照不受影响（深拷）


def test_timeline_order_and_parent():
    rec = Recorder()
    for i in range(3):
        rec.snapshot(i, [{"role": "user", "content": str(i)}], "s",
                     {"thought": "t"}, str(i), 0)
    tl = rec.timeline(0)
    assert [cp.step for cp in tl] == [0, 1, 2]
    assert tl[0].parent is None and tl[1].parent == tl[0].id


def test_new_branch_links_to_fork_point():
    rec = Recorder()
    cp = rec.snapshot(0, [], "s", {"thought": "t"}, "o", 0)
    b = rec.new_branch(parent_cp=cp.id)
    assert b != 0
    ncp = rec.snapshot(0, [], "s2", {"final_answer": "x"}, None, b)
    assert ncp.parent == cp.id          # 新分支首个 cp 指回分叉点


def test_recorder_serialization_roundtrip():
    import json

    rec = Recorder()
    rec.snapshot(0, [{"role": "user", "content": "hi"}], "sys",
                 {"thought": "t", "action": {"tool": "x", "args": {}}}, "o", 0)
    rec.snapshot(1, [{"role": "user", "content": "hi"}], "sys",
                 {"thought": "t", "final_answer": "done"}, None, 0)

    d = json.loads(json.dumps(rec.to_dict()))      # 过一遍真 JSON
    rec2 = Recorder.from_dict(d)

    assert rec2.tree() == rec.tree()
    assert rec2.get(0).messages == rec.get(0).messages   # 完整 messages 保留 → 重开后可继续 fork
    cp = rec2.snapshot(2, [], "s", {"final_answer": "x"}, None, 0)
    assert cp.id == 2                                     # id 续号不冲突
