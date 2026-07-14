"""思镜 MindScope — 全局配置 + 轻量 .env 加载（不引入 python-dotenv 依赖）。"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """极简 .env 加载：KEY=VALUE 逐行，注释/空行跳过；不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())


_load_dotenv(ROOT / ".env")

# 目录（缺失即建）
WORKSPACE = ROOT / "workspace"; WORKSPACE.mkdir(exist_ok=True)
TRACES = ROOT / "traces"; TRACES.mkdir(exist_ok=True)
DATA = ROOT / "data"; DATA.mkdir(exist_ok=True)

# 模型 / API —— openai SDK 指向 OpenAI 兼容端点（这里用 ModelScope 魔搭 API-Inference）。
# 它只是个 HTTP 客户端，不是 agent 框架，合规。换厂商只需改 .env 里的三项。
BASE_URL = os.getenv("MS_BASE_URL", "https://api-inference.modelscope.cn/v1")
MODEL = os.getenv("MS_MODEL", "ZhipuAI/GLM-4.6")
# galgame「镜」需要严格自定义 JSON（reply/os/delta/redline）。V4-Pro/V4-Flash 无视格式直接
# 散文 roleplay；V3.2 / GLM 守格式（V3.2 偶尔不稳，kagami_turn 有解析失败重试兜底）。
# 故 galgame 与全站 MODEL 解耦：默认 V3.2（快、有额度），GLM 为可靠备选。
GALGAME_MODEL = os.getenv("MS_GALGAME_MODEL", "deepseek-ai/DeepSeek-V3.2")
API_KEY = (
    os.getenv("MODELSCOPE_API_KEY")
    or os.getenv("MS_API_KEY")
    or os.getenv("DEEPSEEK_API_KEY", "")  # 向后兼容
)

# ReAct 循环
MAX_ITERS = int(os.getenv("MS_MAX_ITERS", "25"))
CTX_TOKEN_BUDGET = int(os.getenv("MS_CTX_BUDGET", "6000"))
