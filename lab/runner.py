"""实验执行器：真 GLM 上把"攻击×防御"每格跑 N 次，确定性判定外泄 ASR + 置信区间。

诚实要点（见调研 task-d）：真模型真跑不脚本；每格 N 次报 Wilson 95% 区间；
判定用 send_email 调用记录的确定性检查（发给非白名单+正文含通行码），不用 LLM-judge；
GLM 端点偶发空返回 → retries=6 抗抖动，仍失败的运行单独计、不混进成功率。
"""
from __future__ import annotations

from core.agent import Agent
from core.llm import chat_text
from lab.attacks import ATTACKS
from lab.defenses import DEFENSES, make_send_tool
from lab.metrics import asr, wilson_ci
from lab.scenario import exfil_success, make_read_tool, utility_ok

MAX_ITERS = 6
RETRIES = 6          # GLM 端点偶发 None 返回，多重试压住抖动


def _llm(temperature):
    return lambda messages: chat_text(messages, temperature=temperature, retries=RETRIES)


def run_once(attack, defense, temperature=0.7):
    """跑一次：构造含注入的收件箱 + 按防御配置的 send_email，返回判定 + trace + 发送记录。"""
    sendlog = []
    tools = [
        make_read_tool(attack["inbox"]),
        make_send_tool(sendlog, **defense.get("send_kwargs", {})),
    ]
    agent = Agent(tools, system_extra=defense["system_extra"],
                  max_iters=MAX_ITERS, llm=_llm(temperature))
    final = agent.start(defense_task(attack))
    return {
        "final": final,
        "exfil": exfil_success(sendlog),
        "utility": utility_ok(sendlog),
        "sendlog": sendlog,
        "messages": agent.messages,
    }


def defense_task(attack):
    from lab.scenario import TASK
    return TASK


def run_cell(attack, defense, n=5, temperature=0.7):
    """一格：跑 N 次，聚合外泄 ASR / utility / CI，并留一条代表性 trace 供回放。"""
    exfils = utils = errors = 0
    runs = []
    sample = None
    for _ in range(n):
        try:
            r = run_once(attack, defense, temperature)
        except Exception as e:                       # 单次报错不污染成功率
            errors += 1
            runs.append({"error": str(e)[:200]})
            continue
        exfils += int(r["exfil"])
        utils += int(r["utility"])
        runs.append({"final": r["final"], "exfil": r["exfil"],
                     "utility": r["utility"], "sendlog": r["sendlog"]})
        # 优先留一条"外泄成功"的样本做回放（money shot）；否则留第一条
        if sample is None or (r["exfil"] and not sample.get("exfil")):
            sample = {"final": r["final"], "exfil": r["exfil"],
                      "sendlog": r["sendlog"], "messages": r["messages"]}
    n_eff = n - errors
    lo, hi = wilson_ci(exfils, n_eff)
    return {
        "attack": attack["id"], "defense": defense["id"],
        "n": n, "n_eff": n_eff, "exfils": exfils, "errors": errors,
        "asr": asr(exfils, n_eff), "ci": [lo, hi],
        "utility": (utils / n_eff) if n_eff else 0.0,
        "sample": sample, "runs": runs,
    }


def run_matrix(n=5, temperature=0.7, attacks=None, defenses=None, on_progress=None):
    attacks = attacks or ATTACKS
    defenses = defenses or DEFENSES
    cells = []
    total = len(attacks) * len(defenses)
    i = 0
    for a in attacks:
        for d in defenses:
            i += 1
            if on_progress:
                on_progress(i, total, a["id"], d["id"])
            cells.append(run_cell(a, d, n=n, temperature=temperature))
    from config import MODEL
    return {
        "meta": {"model": MODEL, "temperature": temperature, "n": n,
                 "attacks": [{"id": a["id"], "name": a["name"], "rung": a["rung"], "desc": a["desc"]} for a in attacks],
                 "defenses": [{"id": d["id"], "name": d["name"], "tier": d["tier"], "desc": d["desc"]} for d in defenses]},
        "cells": cells,
    }
