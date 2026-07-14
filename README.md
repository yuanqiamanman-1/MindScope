# 思镜 MindScope · AI Agent 时间旅行调试器

> 人工智能基础（A）综合大作业 · 选题一：AI Agent 框架搭建
> 一台从零实现、玻璃盒可视化的 AI Agent「时间旅行调试器」——
> 回到 agent 推理的任意一步、改一行系统提示词、从该步重跑，当场看它走出不同结果。
> **"提示词即程序"，可交互地演示出来。**

## ✨ 功能一览

**核心（选题一硬性要求，全部自写、不用 LangChain/LlamaIndex）**
- 从零的 ReAct 循环：Thought→Action(JSON)→Observation，JSON 解析容错、最大轮数护栏、上下文管理
- 6 个工具：计算器、维基搜索、文件读/写（沙箱）、python_exec（隔离）、长期记忆

**主角（差异化）**
- ⏪ **时间旅行调试器**：逐步快照 / 回退 / 改提示词或观察值 / fork 重跑 / 分支树对照 / 分支副作用隔离

**进阶四项 + 额外**
- 流式输出 · 短期+长期记忆（**自动召回**，跨会话）· 自定义玻璃盒 Web 界面 · 多 Agent 协作（Planner→Executor→Reflector）
- 💾 会话持久化：多会话留存 / 列表 / 重新打开 / 历史回放 / 可继续 fork
- 🛡️ 提示词注入攻防 · 🕵️ 神探破案（DemoModel 确定复现）

## 🚀 运行

```bash
pip install -r requirements.txt
cp .env.example .env        # 填入 LLM API key（ModelScope/DeepSeek 等 OpenAI 兼容端点）

# 单元测试（确定性核心，不需要 key）
python -m pytest -q

# CLI
python cli.py "查爱因斯坦活了多少岁"      # 多步任务
python cli.py --debug                     # 时间旅行闭环演示
python cli.py --memory                    # 跨会话长期记忆演示

# 玻璃盒 Web 界面（含时间旅行控件 + 演示按钮）
python -m uvicorn server:app --port 8770
# 浏览器打开 http://127.0.0.1:8770/
```

## 🎮 Web 界面怎么玩

1. 底部输入任务 → **RUN** → 中间「推理步流」逐步冒出 Thought/Action/Observation，左侧「分支树」长出 checkpoint。
2. 点左侧任意 **checkpoint** → 右侧「时间旅行」面板亮起，显示那一步的系统提示词。
3. 在「追加系统规则」框写一条规则（如改语言/加防御）→ **从这步重跑** → 左侧 fork 出新分支，对照两条结果。
4. 一键演示：**🛡️ 注入攻防**（被劫持泄密 → 加防御重跑 → 识破）、**🕵️ 神探破案**（冤枉好人 → 加严谨规则 → 抓真凶）。
5. 左上 **SESSIONS** 侧栏：历史会话留存，点击重开/回放。

## 🔧 .env 配置

```
MODELSCOPE_API_KEY=...                       # 你的令牌
MS_BASE_URL=https://api-inference.modelscope.cn/v1
MS_MODEL=ZhipuAI/GLM-5.1                      # 以模型页"API 调用"显示的为准
```
（也兼容 DeepSeek：把 base_url/model 换成对应值即可。openai SDK 只是 HTTP 客户端，非 agent 框架。）

## 📁 结构

```
core/         引擎：llm / agent / prompt / checkpoint / isolation / timetravel
tools/        6 工具 + 注册表（含 CSO 沙箱加固）
orchestrator.py  多 Agent 编排
server.py     FastAPI + SSE + 时间旅行 API + 会话持久化
web/          玻璃盒前端（index.html / app.js / live.css）
demos/        injection / detective（DemoModel 确定复现）
report/       实验报告草稿
tests/        单元测试（确定性核心全绿）
openspec/     需求规范（proposal/design/specs/tasks）
docs/         施工图   research/  赛道调研
```

## ⚠️ 已知限制（诚实记录）
- `zh.wikipedia` 国内不可达 → search 优雅降级，演示用 golden trace 兜底
- python_exec 为**非生产级沙箱**（子进程隔离 + 剥离密钥环境 + 超时），生产化需容器级隔离
- 真 LLM 非确定性 → money shot 的稳定复现靠 DemoModel/golden trace
