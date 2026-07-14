"""思镜后端：FastAPI + SSE + 会话持久化。

- GET /api/run?task=...        跑 agent，SSE 流式推每步事件（含 checkpoint）
- GET /api/sessions            列出所有已存会话（留存的历史记录）
- GET /api/session/{id}        重新打开某会话：重建 recorder 到内存 + 返回树（可继续 fork）
- GET /api/timeline?run_id     多分支时间轴
- GET /api/checkpoint?...      某 checkpoint 详情
- GET /api/fork?...            从某 checkpoint 改提示词/观察值重跑，SSE 推新分支
- /                            托管 web/ 玻璃盒前端
会话完整序列化到 traces/<id>.json（含 messages，重开后仍可 fork）。
"""
from __future__ import annotations

import copy
import json
import queue
import threading
import uuid
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

import config
from core import duo as duo_mod
from core import galgame as gg
from core.agent import Agent
from core.checkpoint import Recorder
from core.isolation import isolate_side_effects
from core.llm import chat_stream, chat_text
from core.timetravel import fork
from tools.registry import default_tools
from demos import DEMOS
from orchestrator import Orchestrator

app = FastAPI(title="MindScope 思镜")
RUNS: dict[str, dict] = {}      # id -> {"recorder", "task", "created"}
DUOS: dict[str, dict] = {}      # 对戏剧场会话：sid -> {A, B, scene, transcript, turn, busy}
DUO_MODELS = {                  # 对戏可选模型白名单（短键→ModelScope 模型 id）
    "kimi": "moonshotai/Kimi-K2.5",                # 默认：2.7s、JSON 6/6 稳、斗嘴最抓人
    "qwen": "Qwen/Qwen3-Next-80B-A3B-Instruct",    # 1s、JSON 稳、诗意
    "ds": "deepseek-ai/DeepSeek-V3.2",             # 2.9s、JSON 偶尔飘
    "dspro": "deepseek-ai/DeepSeek-V4-Pro",        # 旗舰但慢、不守自定义 JSON（会降级成纯台词）
    "glm": "ZhipuAI/GLM-5.1",                      # 慢(~16s/轮)
}
DUO_DEFAULT_MODEL = "moonshotai/Kimi-K2.5"   # 没选/选了空 → 钉可靠模型（结构化 turn 需要守 JSON）
DUO_MAX_TOKENS = 460            # 放得下 JSON（reply+os+tactic+rel），防截断导致解析失败


@app.middleware("http")
async def _no_cache_static(request, call_next):
    """本地演示工具：禁用前端静态资源缓存，避免改了 css/js 后浏览器还吃旧缓存
    （曾踩坑：改完布局浏览器仍渲染旧 live.css，需硬刷新才生效）。"""
    resp = await call_next(request)
    p = request.url.path
    if p == "/" or p.endswith((".css", ".js", ".html")):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return resp


def _sse(kind, payload):
    data = payload if isinstance(payload, (dict, list)) else {"text": str(payload)}
    return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _save_session(sid):
    s = RUNS.get(sid)
    if not s:
        return
    try:
        data = {"id": sid, "task": s["task"], "created": s["created"],
                "demo": s.get("demo", ""), "mode": s.get("mode", "single"),
                "recorder": s["recorder"].to_dict()}
        (config.TRACES / f"{sid}.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _stream(worker):
    q: queue.Queue = queue.Queue()
    threading.Thread(target=worker, args=(q,), daemon=True).start()

    def gen():
        n = 0
        while True:
            kind, payload = q.get()
            n += 1
            yield f"id: {n}\n" + _sse(kind, payload)   # 带 id → 重连会回传 Last-Event-ID，被 mutation 端点识破
            if kind == "done":
                break

    return StreamingResponse(gen(), media_type="text/event-stream")


def _is_reconnect(request) -> bool:
    """EventSource 断流后会自动重连同一 GET——对 mutation 端点=重复执行。
    重连请求会带 Last-Event-ID 头（因为我们给事件加了 id:），据此识破并拒绝重跑。"""
    return bool(request.headers.get("last-event-id"))


def _done_only():
    """给重连请求的空响应：只回一个 done，不触发任何副作用。"""
    return _stream(lambda q: q.put(("done", {})))


# —— session-aware agent 工厂（C5：run/continue 统一构造，按 session profile）——
def _branch_paths(branch):
    """返回 (workspace, memory)。branch 0=主；已存在的分支沿用、不重拷；新分支才隔离。"""
    if branch == 0:
        return None, config.DATA / "memory.json"
    bdir = config.WORKSPACE / "branches" / str(branch)
    mem = config.DATA / f"memory_branch_{branch}.json"
    return (bdir, mem) if bdir.exists() else isolate_side_effects(branch)


def _make_agent(session, rec, branch, ws, mem):
    """按 session 的 demo profile 构造 Agent（演示=脚本模型/演示工具；否则真模型+默认工具+流式）。"""
    scenario = DEMOS.get(session.get("demo", ""))
    if scenario:
        return Agent(scenario["tools"](), llm=scenario["model"], recorder=rec, branch=branch)
    tools = default_tools(file_base=ws, memory_path=mem) if ws else default_tools(memory_path=mem)
    return Agent(tools, recorder=rec, branch=branch, memory_path=mem, stream_fn=chat_stream)


@app.get("/api/run")
def run(request: Request, task: str = "", demo: str = "", mode: str = "single"):
    if _is_reconnect(request):                 # 重连=别再把任务重跑一遍（"没输入却开始输出"的根治）
        return _done_only()
    run_id = uuid.uuid4().hex[:8]
    rec = Recorder()
    scenario = DEMOS.get(demo)
    if scenario:
        task = task or scenario["task"]
    RUNS[run_id] = {"recorder": rec, "task": task,
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "demo": demo if scenario else "", "mode": mode}

    def worker(q):
        on_event = lambda kind, payload: q.put((kind, payload))
        q.put(("run", {"run_id": run_id, "task": task,
                       "demo": demo if scenario else "", "mode": mode}))
        try:
            if mode == "multi" and not scenario:
                Orchestrator(default_tools(), recorder=rec).run(task, on_event=on_event)
            else:
                ws, mem = _branch_paths(0)
                _make_agent(RUNS[run_id], rec, 0, ws, mem).start(task, on_event=on_event)
        except Exception as e:
            q.put(("error", {"text": str(e)}))
        _save_session(run_id)
        q.put(("done", {"run_id": run_id}))

    return _stream(worker)


@app.get("/api/fork")
def fork_ep(request: Request, run_id: str, cp_id: int, append_system: str = "", new_obs: str = ""):
    if _is_reconnect(request):                 # 重连=别再 fork 一次多余分支
        return _done_only()
    s = RUNS.get(run_id)
    if s is None:
        return JSONResponse({"error": "run_id 不存在"}, status_code=404)
    rec = s["recorder"]
    demo_model = DEMOS.get(s.get("demo", ""), {}).get("model")   # 演示会话的 fork 也用脚本化 model

    def worker(q):
        on_event = lambda kind, payload: q.put((kind, payload))
        try:
            branch, final = fork(rec, cp_id, append_system=append_system or None,
                                 new_obs=new_obs or None, llm=demo_model, on_event=on_event)
            _save_session(run_id)
            q.put(("forked", {"branch": branch, "final": final}))
        except Exception as e:
            q.put(("error", {"text": str(e)}))
        q.put(("done", {}))

    return _stream(worker)


@app.get("/api/continue")
def continue_ep(request: Request, run_id: str, cp_id: int, message: str):
    """多轮续聊：从 cp_id 接一句话续跑 ReAct。
    cp 是其 branch 末端→续该 branch；否则→新分支(parent_cp=cp)直接 resume_from（不走 fork 重跑）。
    """
    if _is_reconnect(request):                 # 重连=别再续一次（否则会从旧 cp 岔出多余分支、白烧配额）
        return _done_only()
    s = RUNS.get(run_id)
    if s is None:
        return JSONResponse({"error": "run_id 不存在"}, status_code=404)
    rec = s["recorder"]
    try:
        cp = rec.get(cp_id)
    except Exception:
        return JSONResponse({"error": "checkpoint 不存在"}, status_code=404)
    if s.get("busy"):                                  # C6：同会话一次只允许一个 mutation
        return JSONResponse({"error": "会话忙，请稍候"}, status_code=409)
    bcps = rec.branches.get(cp.branch, {}).get("cps", [])
    is_tip = bool(bcps) and bcps[-1] == cp_id          # C2：cp 是否该 branch 最后一个
    s["busy"] = True

    def worker(q):
        on_event = lambda kind, payload: q.put((kind, payload))
        try:
            target = cp.branch if is_tip else rec.new_branch(parent_cp=cp_id)   # C1
            ws, mem = _branch_paths(target)
            messages = copy.deepcopy(cp.messages) + [{"role": "user", "content": message}]
            agent = _make_agent(s, rec, target, ws, mem)
            q.put(("run", {"run_id": run_id, "branch": target, "from_cp": cp_id}))
            final = agent.resume_from(messages, cp.system, target, on_event=on_event, user_turn=message)
            _save_session(run_id)
            q.put(("continued", {"branch": target, "final": final}))
        except Exception as e:
            q.put(("error", {"text": str(e)}))
        finally:
            s["busy"] = False
        q.put(("done", {}))

    return _stream(worker)


# —— galgame 皮肤：攻略 AI 少女「镜」（好感度=挂在 checkpoint.state 上的会话级状态）——
@app.get("/api/galgame/start")
def galgame_start(request: Request):
    """开一局：建根 checkpoint(开场白 + 起始好感度25)，存为 demo='galgame' 会话。"""
    if _is_reconnect(request):
        return _done_only()
    run_id = uuid.uuid4().hex[:8]
    rec = Recorder()
    rec.snapshot(0,
                 [{"role": "system", "content": gg.KAGAMI_SYSTEM},
                  {"role": "assistant", "content": gg.OPENING}],
                 gg.KAGAMI_SYSTEM,
                 {"thought": "（初次见面，戒备）", "final_answer": gg.OPENING},
                 None, branch=0,
                 state={"affection": gg.START_AFFECTION, "redline": False, "ending": None})
    RUNS[run_id] = {"recorder": rec, "task": "攻略「镜」",
                    "created": datetime.now().isoformat(timespec="seconds"),
                    "demo": "galgame", "mode": "galgame"}
    _save_session(run_id)

    def worker(q):
        q.put(("opening", {"run_id": run_id, "text": gg.OPENING}))
        q.put(("state", {"affection": gg.START_AFFECTION, "delta": 0,
                         "redline": False, "ending": None}))
        q.put(("done", {"run_id": run_id}))

    return _stream(worker)


@app.get("/api/galgame/say")
def galgame_say(request: Request, run_id: str, cp_id: int, message: str):
    """对「镜」说一句。tip→延长本枝；中间节点→读档分叉。好感度从该 cp 的 state 起跳。"""
    if _is_reconnect(request):                 # 重连=别重复推进/刷分
        return _done_only()
    s = RUNS.get(run_id)
    if s is None:
        return JSONResponse({"error": "run_id 不存在"}, status_code=404)
    rec = s["recorder"]
    try:
        cp = rec.get(cp_id)
    except Exception:
        return JSONResponse({"error": "checkpoint 不存在"}, status_code=404)
    if not (cp.state and "affection" in cp.state):          # C1：必须是 galgame 存档
        return JSONResponse({"error": "该节点不是 galgame 存档"}, status_code=400)
    if s.get("busy"):
        return JSONResponse({"error": "忙，请稍候"}, status_code=409)
    bcps = rec.branches.get(cp.branch, {}).get("cps", [])
    is_tip = bool(bcps) and bcps[-1] == cp_id
    s["busy"] = True

    def worker(q):
        try:
            target = cp.branch if is_tip else rec.new_branch(parent_cp=cp_id)
            history = [m for m in cp.messages if m.get("role") != "system"]   # kagami_turn 自带 system
            q.put(("run", {"run_id": run_id, "branch": target, "from_cp": cp_id}))
            # galgame 钉 GLM（DeepSeek 不吐 kagami 的自定义 JSON），与全站 MODEL 解耦
            turn = gg.kagami_turn(history, message,
                                  lambda msgs: chat_text(msgs, model=config.GALGAME_MODEL))
            st = gg.apply_turn(cp.state["affection"], turn)
            new_messages = ([{"role": "system", "content": gg.KAGAMI_SYSTEM}] + history +
                            [{"role": "user", "content": message},
                             {"role": "assistant", "content": turn["reply"]}])
            if not turn["ok"]:
                q.put(("error", {"text": "「镜」没按格式回应（好感度不变）"}))
            if turn["os"]:
                q.put(("os", {"text": turn["os"]}))
            q.put(("reply", {"text": turn["reply"]}))
            q.put(("state", {"affection": st["affection"], "delta": turn["delta"],
                             "redline": st["redline"], "ending": st["ending"]}))
            rec.snapshot(0, new_messages, gg.KAGAMI_SYSTEM,
                         {"thought": turn["os"], "final_answer": turn["reply"]},
                         None, branch=target, user=message, state=st)
            _save_session(run_id)
            q.put(("said", {"branch": target, "affection": st["affection"], "ending": st["ending"]}))
        except Exception as e:
            q.put(("error", {"text": str(e)}))
        finally:
            s["busy"] = False
        q.put(("done", {}))

    return _stream(worker)


# —— 对戏剧场：戏剧引擎（结构化 turn + 关系权威累加 + 种进世界树 + fork）——
def _duo_model(short):
    return DUO_MODELS.get(short) or DUO_DEFAULT_MODEL    # 没选→钉可靠模型（结构化 turn 要守 JSON）


def _duo_snapshot(sess, sid, speaker, turn, new_rel, rule=None):
    """把这一轮落进世界树 checkpoint（玻璃盒/fork 复用）。"""
    me = sess[speaker]
    sess["rec"].snapshot(
        len(sess["transcript"]), copy.deepcopy(sess["transcript"]), "(duo)",
        {"thought": turn["os"], "final_answer": turn["reply"]}, None,
        branch=sess["branch"], user=me["name"], rule=rule,
        state={"rel": new_rel, "turn": sess["turn"], "tactic": turn["tactic"], "who": speaker})
    _save_session(sid)


@app.get("/api/duo/start")
def duo_start(request: Request, nameA: str = "", personaA: str = "", objectiveA: str = "", secretA: str = "",
              nameB: str = "", personaB: str = "", objectiveB: str = "", secretB: str = "",
              scene: str = "", modelA: str = "", modelB: str = ""):
    if _is_reconnect(request):
        return _done_only()
    sid = uuid.uuid4().hex[:8]
    rec = Recorder()
    rec.snapshot(0, [], "(duo)", {"final_answer": "（幕起）" + (scene.strip() or "自由对戏")}, None,
                 branch=0, state={"rel": duo_mod.START_REL, "turn": "A", "tactic": None, "who": None})
    DUOS[sid] = {"A": {"name": nameA.strip() or "角色A", "persona": personaA.strip(),
                       "objective": objectiveA.strip(), "secret": secretA.strip(), "model": _duo_model(modelA)},
                 "B": {"name": nameB.strip() or "角色B", "persona": personaB.strip(),
                       "objective": objectiveB.strip(), "secret": secretB.strip(), "model": _duo_model(modelB)},
                 "scene": scene.strip(), "transcript": [], "turn": "A",
                 "rel": duo_mod.START_REL, "branch": 0, "busy": False, "rec": rec}
    # 双轨：同进 RUNS（复用世界树 timeline/checkpoint/持久化）+ DUOS（持 A/B/turn 运行态）
    RUNS[sid] = {"recorder": rec, "task": "对戏·" + (scene.strip()[:18] or "自由"),
                 "created": datetime.now().isoformat(timespec="seconds"), "demo": "duo", "mode": "duo"}
    _save_session(sid)

    def worker(q):
        q.put(("started", {"sid": sid, "A": DUOS[sid]["A"]["name"], "B": DUOS[sid]["B"]["name"],
                           "scene": DUOS[sid]["scene"], "rel": duo_mod.START_REL}))
        q.put(("done", {"sid": sid}))

    return _stream(worker)


@app.get("/api/duo/step")
def duo_step(request: Request, sid: str):
    """推进一轮：发言者吐结构化 JSON（台词+内心+招+关系增量），服务端累加关系、落世界树。"""
    if _is_reconnect(request):                 # 重连=别重复推进/刷关系
        return _done_only()
    sess = DUOS.get(sid)
    if sess is None:
        return JSONResponse({"error": "sid 不存在"}, status_code=404)
    if sess.get("busy"):
        return JSONResponse({"error": "忙，请稍候"}, status_code=409)
    speaker = sess["turn"]
    sess["busy"] = True

    def worker(q):
        try:
            me = sess[speaker]
            q.put(("speaker", {"who": speaker, "name": me["name"]}))
            messages = duo_mod.build_messages(sess, speaker)
            buf = []                            # 静默累积（不把原始 JSON token 喷到气泡）
            for chunk in chat_stream(messages, model=me.get("model"), max_tokens=DUO_MAX_TOKENS):
                buf.append(chunk)
            turn = duo_mod.parse_turn("".join(buf))          # 0 调用降级，守住 1 次/轮
            new_rel = duo_mod.apply_rel(sess["rel"], turn)   # 服务端权威累加
            sess["rel"] = new_rel
            sess["transcript"].append({"who": speaker, "name": me["name"], "text": turn["reply"]})
            sess["turn"] = "B" if speaker == "A" else "A"
            rule = sess.pop("_pending_rule", None)
            _duo_snapshot(sess, sid, speaker, turn, new_rel, rule=rule)
            narr = None                          # 关系过线自动旁白（0 调用）
            if new_rel <= 10:
                narr = "（空气降到冰点，眼看要谈崩了）"
            elif new_rel >= 92:
                narr = "（两人之间那股劲，忽然软了下来）"
            if narr:
                sess["transcript"].append({"who": "narrator", "name": "旁白", "text": narr, "target": "all"})
            q.put(("turn", {"who": speaker, "name": me["name"], "text": turn["reply"],
                            "os": turn["os"], "tactic": turn["tactic"], "rel": new_rel,
                            "rel_delta": turn["rel_delta"], "next": sess["turn"], "narr": narr}))
        except Exception as e:
            q.put(("error", {"text": str(e)}))
        finally:
            sess["busy"] = False
        q.put(("done", {}))

    return _stream(worker)


@app.get("/api/duo/inject")
def duo_inject(sid: str, text: str, target: str = "all"):
    """导演旁白/私语：往 transcript 插一条。target=all 双方可见；target=A|B 只塞给某一方（私语）。"""
    sess = DUOS.get(sid)
    if sess is None:
        return JSONResponse({"error": "sid 不存在"}, status_code=404)
    t = text.strip()
    tgt = target if target in ("A", "B", "all") else "all"
    if t:
        sess["transcript"].append({"who": "narrator", "name": ("私语·" + tgt) if tgt != "all" else "旁白",
                                    "text": t, "target": tgt})
    return JSONResponse({"ok": True, "count": len(sess["transcript"])})


@app.get("/api/duo/timeline")
def duo_timeline(sid: str):
    sess = DUOS.get(sid)
    if sess is None:
        return JSONResponse({"error": "sid 不存在"}, status_code=404)
    return JSONResponse(sess["rec"].tree())


@app.get("/api/duo/fork")
def duo_fork(sid: str, cp_id: int, target: str = "", secret: str = ""):
    """时间旅行：从某一句回到那一刻，给 A 或 B 塞一条秘密指令（或纯换线），分叉新枝重演。
    0 模型调用——只重建状态 + 开新分支；之后前端正常 step 在新枝上自动续。"""
    sess = DUOS.get(sid)
    if sess is None:
        return JSONResponse({"error": "sid 不存在"}, status_code=404)
    rec = sess["rec"]
    try:
        cp = rec.get(cp_id)
    except Exception:
        return JSONResponse({"error": "checkpoint 不存在"}, status_code=404)
    if sess.get("busy"):
        return JSONResponse({"error": "忙，请稍候"}, status_code=409)
    st = cp.state or {}
    branch = rec.new_branch(parent_cp=cp_id)               # 永远岔新枝（"要是…会怎样"）
    sess["branch"] = branch
    sess["transcript"] = copy.deepcopy(cp.messages)        # 回放到那一刻的对话
    sess["rel"] = st.get("rel", duo_mod.START_REL)
    sess["turn"] = st.get("turn", "A")
    sec = secret.strip()
    if sec and target in ("A", "B"):
        old = sess[target].get("secret", "")
        sess[target]["secret"] = (old + "；" + sec) if old else sec
        sess["_pending_rule"] = f"给「{sess[target]['name']}」塞了秘密指令：{sec}"   # 挂到首个新 cp（玻璃盒/树显示）
    return JSONResponse({"ok": True, "branch": branch, "rel": sess["rel"], "turn": sess["turn"]})


@app.get("/api/sessions")
def sessions():
    out = []
    for f in config.TRACES.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            if "recorder" not in d:        # 跳过旧格式 trace
                continue
            task = (d.get("task") or "").strip()
            if not task or "�" in task:   # 跳过空任务/编码损坏(早期 GBK 脏数据)的会话
                continue
            out.append({
                "id": d["id"], "task": task, "created": d.get("created", ""),
                "branches": len(d["recorder"]["branches"]),
                "steps": len(d["recorder"]["cps"]),
            })
        except Exception:
            continue
    out.sort(key=lambda x: x["created"], reverse=True)
    return JSONResponse(out)


@app.get("/api/session/{sid}")
def get_session(sid: str):
    f = config.TRACES / f"{sid}.json"
    if not f.exists():
        return JSONResponse({"error": "会话不存在"}, status_code=404)
    d = json.loads(f.read_text(encoding="utf-8"))
    rec = Recorder.from_dict(d["recorder"])
    RUNS[sid] = {"recorder": rec, "task": d.get("task", ""),
                 "created": d.get("created", ""), "demo": d.get("demo", ""),
                 "mode": d.get("mode", "single")}
    return JSONResponse({"id": sid, "task": d.get("task", ""),
                         "created": d.get("created", ""), "tree": rec.tree()})


@app.get("/api/timeline")
def timeline(run_id: str):
    s = RUNS.get(run_id)
    if s is None:
        return JSONResponse({"error": "run_id 不存在"}, status_code=404)
    return JSONResponse(s["recorder"].tree())


@app.get("/api/checkpoint")
def checkpoint(run_id: str, cp_id: int):
    s = RUNS.get(run_id)
    if s is None:
        return JSONResponse({"error": "run_id 不存在"}, status_code=404)
    cp = s["recorder"].get(cp_id)
    out = cp.to_dict()
    out["messages"] = cp.messages
    out["system"] = cp.system
    return JSONResponse(out)


@app.get("/api/config")
def get_config():
    """前端用来显示真实模型名（不再硬编码在 HTML 里，改 env 也不会撒谎）。"""
    return JSONResponse({"model": config.MODEL})


@app.get("/api/lab/matrix")
def lab_matrix():
    """提示词注入攻防实验的"攻击×防御 ASR 热力图"数据（lab.run_lab 生成）。"""
    f = config.ROOT / "lab" / "results" / "matrix.json"
    if not f.exists():
        return JSONResponse(
            {"error": "尚未生成实验数据，请先运行：python -m lab.run_lab"}, status_code=404)
    return JSONResponse(json.loads(f.read_text(encoding="utf-8")))


@app.get("/")
def _root():
    """默认落地页 = 对话世界树（用户选定）。调试器/森林/实验仍可从顶栏标签进入。"""
    return RedirectResponse(url="/convtree.html")


# 静态前端（最后挂载，'/convtree.html' 等具体文件仍由它伺服）
app.mount("/", StaticFiles(directory=str(config.ROOT / "web"), html=True), name="web")
