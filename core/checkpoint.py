"""时间旅行的不可变快照与分支记录。

每完成一步生成一个深拷贝 Checkpoint；Recorder 维护多分支时间轴（"Agent 的 git 树"）。
"""
from __future__ import annotations

import copy
import itertools


class Checkpoint:
    __slots__ = ("id", "branch", "step", "messages", "system", "step_obj", "obs", "parent", "user", "rule", "state")

    def __init__(self, id, branch, step, messages, system, step_obj, obs, parent, user=None, rule=None, state=None):
        self.id = id
        self.branch = branch
        self.step = step
        self.messages = copy.deepcopy(messages)   # 不可变快照：进来即深拷
        self.system = system
        self.step_obj = copy.deepcopy(step_obj)
        self.obs = obs
        self.parent = parent                       # 父 checkpoint id（构成树）
        self.user = user                           # 本步起始的"用户那一轮"输入（仅每轮首个 cp 有；否则 None）
        self.rule = rule                           # 时间旅行 fork 时追加的系统规则（仅分叉首个 cp 有；否则 None）
        # 会话级状态（galgame 好感度等）。深拷防分支间共享同一 dict 互相污染（Codex C1）
        self.state = copy.deepcopy(state) if state else None

    def to_dict(self):
        s = self.step_obj or {}
        return {
            "id": self.id, "branch": self.branch, "step": self.step,
            "thought": s.get("thought"), "action": s.get("action"),
            "final": s.get("final_answer"), "obs": self.obs, "parent": self.parent,
            "user": self.user, "rule": self.rule, "state": self.state,
        }

    def to_full_dict(self):
        """完整序列化（含 messages/system），用于会话持久化 + 重开后可继续 fork。"""
        return {
            "id": self.id, "branch": self.branch, "step": self.step,
            "messages": self.messages, "system": self.system,
            "step_obj": self.step_obj, "obs": self.obs, "parent": self.parent,
            "user": self.user, "rule": self.rule, "state": self.state,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["id"], d["branch"], d["step"], d["messages"],
                   d["system"], d["step_obj"], d["obs"], d["parent"],
                   d.get("user"), d.get("rule"), d.get("state"))


class Recorder:
    def __init__(self):
        self.cps: list[Checkpoint] = []                 # 按 id 顺序存（cps[id] == 该 cp）
        self._ids = itertools.count()
        self.branches = {0: {"parent_cp": None, "cps": []}}

    def snapshot(self, step, messages, system, step_obj, obs, branch=0, user=None, rule=None, state=None):
        if branch not in self.branches:
            self.branches[branch] = {"parent_cp": None, "cps": []}
        b = self.branches[branch]
        parent = b["cps"][-1] if b["cps"] else b["parent_cp"]
        cp = Checkpoint(next(self._ids), branch, step, messages, system, step_obj, obs, parent, user, rule, state)
        self.cps.append(cp)
        b["cps"].append(cp.id)
        return cp

    def get(self, cp_id) -> Checkpoint:
        return self.cps[cp_id]

    def timeline(self, branch=0):
        return [self.cps[i] for i in self.branches.get(branch, {}).get("cps", [])]

    def new_branch(self, parent_cp):
        bid = max(self.branches) + 1
        self.branches[bid] = {"parent_cp": parent_cp, "cps": []}
        return bid

    def tree(self):
        """返回分支树：{branch_id: {"parent_cp":.., "steps":[cp.to_dict..]}}。"""
        return {
            bid: {"parent_cp": b["parent_cp"],
                  "steps": [self.cps[i].to_dict() for i in b["cps"]]}
            for bid, b in self.branches.items()
        }

    # —— 完整持久化（含 messages，重开会话后仍可 fork）——
    def to_dict(self):
        return {"cps": [c.to_full_dict() for c in self.cps], "branches": self.branches}

    @classmethod
    def from_dict(cls, d):
        rec = cls()
        rec.cps = [Checkpoint.from_dict(c) for c in d["cps"]]
        rec.branches = {int(k): v for k, v in d["branches"].items()}
        rec._ids = itertools.count(len(rec.cps))
        return rec
