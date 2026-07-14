"""从零实现的 ReAct Agent —— 不使用 LangChain/LlamaIndex。

- parse_action：把 LLM 输出解析为结构化 Action，带 JSON 容错。
- Agent：ReAct 循环；run 拆成 start()/resume_from()，共享 _loop()，
  使时间旅行能从任意 checkpoint 续跑而不重置 messages（见 design D10）。
"""
from __future__ import annotations

import json
import re

import config
from core.prompt import build_system


class ParseError(Exception):
    pass


def _extract_json(text: str) -> str:
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        return m.group(0)
    return text.strip()


def _repair(raw: str) -> str:
    # 去掉对象/数组里的尾随逗号：{"a":1,} -> {"a":1}
    return re.sub(r",\s*([}\]])", r"\1", raw.strip())


def parse_action(text: str) -> dict:
    """返回 {'thought',..,'action':{'tool','args'}} 或 {'thought',..,'final_answer'}。"""
    raw = _extract_json(text)
    obj = None
    for candidate in (raw, _repair(raw)):
        try:
            obj = json.loads(candidate)
            break
        except json.JSONDecodeError:
            obj = None
    if obj is None:
        raise ParseError(f"无法解析为 JSON: {text[:120]!r}")
    if not isinstance(obj, dict) or ("final_answer" not in obj and "action" not in obj):
        raise ParseError("缺少 action 或 final_answer")
    if "final_answer" not in obj:                       # 校验 action 结构，畸形则走纠错重试而非崩溃
        act = obj.get("action")
        if not isinstance(act, dict) or not isinstance(act.get("tool"), str):
            raise ParseError("action 必须是含字符串 tool 的对象")
        if not isinstance(act.get("args", {}), dict):
            raise ParseError("action.args 必须是对象")
    return obj


def _noop(*_a, **_k):
    pass


def _default_llm(messages):
    from core.llm import chat_text  # 懒导入，避免无 key/无 openai 时 import 失败
    return chat_text(messages)


class Agent:
    def __init__(self, tools, *, system=None, system_extra="", max_iters=config.MAX_ITERS,
                 llm=None, recorder=None, branch=0, memory_path=None, stream_fn=None):
        self.tools = {t.name: t for t in tools}
        self._tools_list = list(tools)
        self.max_iters = max_iters
        # system 显式给定则整体替换（多 Agent 角色用）；否则按工具+extra 构建 ReAct 提示词
        self.system = system if system is not None else build_system(self._tools_list, max_iters, system_extra)
        # 长期记忆自动召回：把已存的记忆注入系统提示词，agent 无需被叫就"想得起来"
        if memory_path is not None:
            from tools.memory_tool import summary as _mem_summary
            mem = _mem_summary(memory_path)
            if mem:
                self.system = self.system + "\n\n" + mem
        self.llm = llm or _default_llm          # 可注入 stub: callable(messages)->str
        self.stream_fn = stream_fn              # 流式生成器 callable(messages)->Iterator[str]，推 raw token
        self.recorder = recorder
        self.branch = branch
        self.messages: list[dict] = []
        self._pending_user = None                # 下一个 snapshot 要附带的"用户那一轮"输入
        self._pending_rule = None                # 下一个 snapshot 要附带的"时间旅行追加规则"

    # —— 入口：全新开始 ——
    def start(self, user_input, on_event=_noop):
        self.messages = [
            {"role": "system", "content": self.system},
            {"role": "user", "content": user_input},
        ]
        self._pending_user = user_input          # 原始任务也算"用户那一轮"，玻璃盒里显示
        self._pending_rule = None
        return self._loop(on_event)

    # —— 入口：从某 checkpoint 状态续跑（时间旅行 fork / 多轮续聊用），不重置 messages ——
    def resume_from(self, messages, system, branch, on_event=_noop, user_turn=None, rule_turn=None):
        self.messages = [dict(m) for m in messages]
        self.system = system
        if self.messages and self.messages[0].get("role") == "system":
            self.messages[0]["content"] = system
        self.branch = branch
        self._pending_user = user_turn           # 续聊传入用户消息；fork 重跑传 None（无新用户轮）
        self._pending_rule = rule_turn           # fork 传入追加的系统规则；续聊传 None
        return self._loop(on_event)

    # —— 共享循环体 ——
    def _generate(self, on_event):
        """生成本步回复。有 stream_fn 则逐 chunk 推 raw token 事件并累积；否则非流式。"""
        if self.stream_fn is not None:
            buf = []
            for chunk in self.stream_fn(self.messages):
                buf.append(chunk)
                on_event("token", chunk)
            return "".join(buf)
        return self.llm(self.messages)

    def _loop(self, on_event):
        for step_no in range(self.max_iters):
            reply = self._generate(on_event)
            try:
                step = parse_action(reply)
            except ParseError:
                self.messages.append({
                    "role": "user",
                    "content": "上一步输出不是合法 JSON，请仅输出规定格式的 JSON。",
                })
                continue
            self.messages.append({"role": "assistant", "content": reply})
            on_event("thought", step.get("thought", ""))
            if "final_answer" in step:
                cp = self._snapshot(step_no, step, None)
                if cp is not None:
                    on_event("checkpoint", cp.to_dict())
                on_event("final", step["final_answer"])
                return step["final_answer"]
            action = step["action"]
            on_event("action", action)
            obs = self._exec_tool(action)
            on_event("observation", obs)
            self.messages.append({"role": "user", "content": f"Observation: {obs}"})
            cp = self._snapshot(step_no, step, obs)
            if cp is not None:
                on_event("checkpoint", cp.to_dict())
            self._manage_context()
        on_event("final", "已达最大轮数，给出当前结论。")
        return "已达最大轮数。"

    def _exec_tool(self, action) -> str:
        name = action.get("tool")
        args = action.get("args", {}) or {}
        tool = self.tools.get(name)
        if tool is None:
            return f"Error: 未知工具 {name!r}"
        try:
            return str(tool.execute(args))
        except Exception as e:  # 工具错误 → 可恢复的 Observation
            return f"Error: {e}"

    def _snapshot(self, step_no, step, obs):
        if self.recorder is not None:
            cp = self.recorder.snapshot(step_no, self.messages, self.system, step, obs,
                                        self.branch, user=self._pending_user, rule=self._pending_rule)
            self._pending_user = None            # 用户那一轮 / 追加规则只挂在本轮首个 cp 上，之后清空
            self._pending_rule = None
            return cp
        return None

    def _manage_context(self):
        """粗略上下文管理：超阈值则保留 system + 最近若干轮（摘要 TODO）。"""
        approx_tokens = sum(len(m.get("content", "")) for m in self.messages) / 4
        if approx_tokens <= config.CTX_TOKEN_BUDGET:
            return
        sys_msg = self.messages[0]
        recent = self.messages[-8:]
        self.messages = [sys_msg] + [m for m in recent if m is not sys_msg]
