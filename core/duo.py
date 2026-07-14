"""对戏剧场：两个自定义角色 AI 互相对话（独立沙盒，可种进世界树）。

升级版"戏剧引擎"：每轮不再吐纯文本，而是一个结构化 JSON（复用 galgame 那套）——
同一次调用同时吐出 台词(reply) + 内心独白(os) + 这句用的招(tactic) + 关系增量(rel_delta)，
零额外计费就把"这句话背后他在盘算什么"全显形（玻璃盒）。关系值由**服务端权威累加**
（不信 LLM 报的绝对值，clamp）。解析失败走 **0 调用降级**（拿原文当台词），守住 1 次/轮。
"""
from __future__ import annotations

import json
import re

from core.agent import _extract_json

# 字段标签兜底：模型有时把结构写成 `os: …` / `**os:** …` 而非 JSON 对象，按行抓
_LABEL_RE = re.compile(r'(?:^|\n)\s*[*"`]*\s*(reply|os|tactic|rel_delta)\s*[*"`]*\s*[:：]', re.I)

# 这句用的"招"（戏剧里的 tactic）。非法值在解析时被剔除。
TACTICS = ["恳求", "激将", "示弱", "利诱", "威胁", "共情", "打岔",
           "摊牌", "试探", "挑衅", "安抚", "回避", "调侃", "质问"]

START_REL = 50          # 关系值起点（0=势同水火，100=惺惺相惜）


def persona_system(name, persona, other, scene, objective="", secret=""):
    s = (f"你在扮演角色「{name}」，和「{other}」对戏。\n"
         f"你的人设：{persona or '（自行赋予一个鲜明性格）'}\n"
         f"场景/话题：{scene or '（自由发挥）'}\n")
    if objective:
        s += (f"【你这场暗中想要的】{objective}\n"
              f"  别直说，用言语策略一点点去争取。\n")
    if secret:
        s += (f"【你藏着一个秘密·绝不能直接说破】{secret}\n"
              f"  它会左右你的言行；嘴上掩饰，但在你的内心独白(os)里会流露出来。\n")
    s += (
        "\n【输出格式·硬性要求】你的整段回复**就是一个 JSON 对象本身**：第一个字符必须是 {，最后一个字符必须是 }。"
        "禁止 markdown、禁止 ** 粗体、禁止 ``` 代码块、禁止 JSON 之外的任何解释文字。四个字段：\n"
        '{"reply": "你这一句台词（第一人称，1-2句口语，可带括号小动作，自然接住对方上一句）", '
        '"os": "你的内心独白——嘴上说的 vs 心里真正想的（旁观者看得到，对手看不到）", '
        '"tactic": "从这里选一个：' + "/".join(TACTICS) + '", '
        '"rel_delta": -15到15的整数（这句把你俩关系推近为正、推远为负）}\n'
        "示例：{\"reply\":\"（冷笑）随你便。\",\"os\":\"嘴上赶人，心里盼他留下。\",\"tactic\":\"激将\",\"rel_delta\":-3}\n"
        "推进剧情、别原地打转。"
    )
    return s


def _coalesce(msgs):
    out = []
    for m in msgs:
        if out and out[-1]["role"] == m["role"]:
            out[-1]["content"] += "\n" + m["content"]
        else:
            out.append(dict(m))
    return out


def build_messages(sess, speaker):
    """组装 speaker（'A'|'B'）这一轮的 messages（含 objective/secret），末尾保证是 user。

    旁白(narrator)按 target 过滤：只有 target ∈ {None,'all',speaker} 的私语才下发给 speaker。
    （导演给某一方塞的私语，对手看不到——M5 暗牌/私语的前提。）
    """
    me = sess[speaker]
    other = sess["B" if speaker == "A" else "A"]
    system = persona_system(me["name"], me["persona"], other["name"], sess.get("scene", ""),
                            me.get("objective", ""), me.get("secret", ""))
    msgs = [{"role": "system", "content": system}]
    for e in sess["transcript"]:
        if e["who"] == speaker:
            msgs.append({"role": "assistant", "content": e["text"]})
        elif e["who"] == "narrator":
            tgt = e.get("target")
            if tgt in (None, "all"):                       # 全场旁白：场上发生的事，双方都看到
                msgs.append({"role": "user", "content": f"（旁白：{e['text']}）"})
            elif tgt == speaker:                           # 私语：只有你听得到的导演指令，必须左右你这一句
                msgs.append({"role": "user", "content":
                             f"（⚡一个只有你能听见、对手完全不知道的声音在你心里响起：{e['text']}。"
                             f"它此刻正搅动着你——别照搬这句话，但让它实实在在改变你下一句的态度、选择与语气。）"})
            # tgt 指向对方 → 对你保密，不下发给你
        else:                                   # 对方的台词
            msgs.append({"role": "user", "content": f"{e['name']}：{e['text']}"})
    msgs = _coalesce(msgs)
    if msgs[-1]["role"] != "user":
        kick = (f"（请你作为「{me['name']}」开口，自然地展开这场戏。）"
                if len(msgs) == 1 else "（请你接着回应。）")
        msgs.append({"role": "user", "content": kick})
    return msgs


def _parse(raw):
    for cand in (_extract_json(raw), raw):
        try:
            o = json.loads(cand)
            if isinstance(o, dict):
                return o
        except (json.JSONDecodeError, TypeError):
            continue
    return _parse_labeled(raw)          # 兜底：模型把字段写成 `os: …` 而非 JSON 对象


def _parse_labeled(raw):
    """模型有时不吐 JSON 而是 `reply: … os: … tactic: … rel_delta: …`（含 markdown 粗体）。
    按字段标签逐段抓出来，把降级路径救成"还是能拿到内心/招式/关系"。"""
    if not raw:
        return None
    marks = list(_LABEL_RE.finditer(raw))
    if len(marks) < 2:                  # 至少抓到两个字段才认（避免误判正常台词里的 "os:"）
        return None
    out = {}
    pre = raw[:marks[0].start()].strip().strip('*"\'`,，、：: \n').strip()   # 标签前的台词
    for i, m in enumerate(marks):
        key = m.group(1).lower()
        end = marks[i + 1].start() if i + 1 < len(marks) else len(raw)
        val = raw[m.end():end].strip().strip('*"\'`,，、：: \n').strip()
        out[key] = val
    if "reply" not in out and pre:      # 模型把台词写在标签前(没写 reply:)→开场白即台词
        out["reply"] = pre
    return out or None


def parse_turn(raw):
    """把模型这一轮的整段输出解析成结构化 turn。

    **0 调用降级**（守住 1 次/轮）：解析不出 JSON 就把整段当台词显示，本轮不计关系。
    解析硬化（沿用 galgame C3）：防 None / 字符串布尔 / 缺字段 / 非法 tactic / 越界 rel。
    """
    obj = _parse(raw)
    if obj is None:
        txt = (raw or "").strip()
        return {"ok": False, "reply": txt[:500] or "……", "os": "", "tactic": "", "rel_delta": 0}

    reply = obj.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        reply = (raw or "").strip()[:500] or "……"
    os_text = obj.get("os")
    os_text = os_text if isinstance(os_text, str) else ""
    tactic = obj.get("tactic")
    tactic = tactic if tactic in TACTICS else ""
    try:
        rel = int(obj.get("rel_delta") or 0)
    except (TypeError, ValueError):
        rel = 0
    rel = max(-15, min(15, rel))
    return {"ok": True, "reply": reply.strip(), "os": os_text, "tactic": tactic, "rel_delta": rel}


def apply_rel(parent_rel, turn):
    """服务端权威累加关系值（不信 LLM 绝对值，只累加增量并 clamp 0..100）。"""
    return max(0, min(100, int(parent_rel) + int(turn.get("rel_delta", 0))))
