"""探活：逐个 ping ModelScope 上对戏用的模型，报告 可用/限流/无provider/延迟。

用法（项目根目录）：
    python -m tools.probe_models

V4-Pro 当前可能是 "no-provider"（魔搭暂无厂商托管）；provider 一恢复这里就会变 OK。
"""
import sys
import time

import config
from openai import OpenAI

try:                                   # Windows 控制台默认 GBK，强制 UTF-8 免得打印挂掉
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MODELS = {
    "DeepSeek-V4-Flash": "deepseek-ai/DeepSeek-V4-Flash",
    "DeepSeek-V4-Pro":   "deepseek-ai/DeepSeek-V4-Pro",
    "DeepSeek-V3.2":     "deepseek-ai/DeepSeek-V3.2",
    "GLM-5.1":           "ZhipuAI/GLM-5.1",
}


def classify(err: str) -> str:
    e = err.lower()
    if "no provider" in e:
        return "[无provider] 魔搭暂未托管，恢复即可用"
    if "quota" in e or "429" in e:
        return "[限流] 今日配额用完，明天再试"
    if "invalid model id" in e:
        return "[名字无效]"
    return "[错误] " + err[:70]


def main():
    c = OpenAI(api_key=config.API_KEY, base_url=config.BASE_URL)
    print(f"端点 {config.BASE_URL}\n探活对戏可用模型：\n")
    for label, mid in MODELS.items():
        t = time.time()
        try:
            out = ""
            for ch in c.chat.completions.create(
                model=mid, messages=[{"role": "user", "content": "用一个字回应"}],
                max_tokens=8, stream=True):
                if ch.choices and ch.choices[0].delta and ch.choices[0].delta.content:
                    out += ch.choices[0].delta.content
            print(f"  [OK {time.time()-t:4.1f}s] {label:18s} {mid}")
        except Exception as e:  # noqa
            print(f"  {classify(str(e)):34s} {label:18s} {mid}")
    print()


if __name__ == "__main__":
    sys.exit(main())
