"""Record the MindScope demo storyboard with Playwright video capture.

The script assumes the FastAPI server is already running at 127.0.0.1:8770.
It records a silent WebM with in-video Chinese title/subtitle cards so the raw
capture is usable even before manual narration/editing.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets" / "video"
OUT_FILE = OUT_DIR / "mindscope-demo.webm"
BASE_URL = "http://127.0.0.1:8770"


def wait(page: Page, ms: int) -> None:
    page.wait_for_timeout(ms)


def title_card(page: Page, title: str, subtitle: str, foot: str = "") -> None:
    page.set_content(
        f"""
        <!doctype html><html lang="zh-CN"><meta charset="utf-8">
        <style>
          html,body{{margin:0;width:100%;height:100%;background:#05070b;color:#e8f2ff;
            font-family:"Microsoft YaHei",system-ui,sans-serif;overflow:hidden;}}
          body::before{{content:"";position:fixed;inset:0;background:
            linear-gradient(rgba(44,255,214,.08) 1px,transparent 1px),
            linear-gradient(90deg,rgba(44,255,214,.08) 1px,transparent 1px);
            background-size:42px 42px;mask-image:radial-gradient(circle at center,#000 0 55%,transparent 78%);}}
          main{{position:relative;height:100%;display:flex;align-items:center;justify-content:center;
            flex-direction:column;text-align:center;letter-spacing:0;}}
          h1{{font-size:82px;margin:0 0 22px;text-shadow:0 0 28px rgba(77,255,226,.28);}}
          p{{font-size:32px;margin:0;color:#9fd7ff;}}
          small{{position:absolute;bottom:64px;font-size:22px;color:#6f8da8;}}
        </style>
        <main><h1>{title}</h1><p>{subtitle}</p><small>{foot}</small></main>
        </html>
        """
    )


def install_overlay(page: Page) -> None:
    page.evaluate(
        """
        () => {
          if (document.querySelector('#record-overlay-style')) return;
          const style = document.createElement('style');
          style.id = 'record-overlay-style';
          style.textContent = `
            .record-caption {
              position: fixed; left: 48px; right: 48px; bottom: 58px; z-index: 99999;
              padding: 18px 24px; border: 1px solid rgba(126, 242, 255, .45);
              background: rgba(3, 9, 18, .76); color: #e9fbff; font: 700 28px/1.45 "Microsoft YaHei", sans-serif;
              box-shadow: 0 0 28px rgba(44, 255, 214, .16); backdrop-filter: blur(8px);
              pointer-events: none;
            }
            .record-caption small { display:block; margin-top:6px; color:#9fb7c9; font-size:19px; font-weight:500; }
            .record-badge {
              position: fixed; top: 88px; left: 50%; transform: translateX(-50%); z-index: 99999;
              padding: 10px 18px; border-radius: 4px; background: rgba(4, 12, 22, .82);
              border: 1px solid rgba(255,255,255,.2); color: #fff; font: 700 22px "Microsoft YaHei", sans-serif;
              pointer-events: none;
            }
            .record-badge.warn { border-color: rgba(255,91,91,.9); color:#ffb7b7; }
            .record-badge.good { border-color: rgba(73,255,162,.9); color:#b7ffd8; }
          `;
          document.head.appendChild(style);
        }
        """
    )


def caption(page: Page, text: str, sub: str = "", seconds: float = 2.0) -> None:
    page.evaluate(
        """
        ({ text, sub }) => {
          document.querySelectorAll('.record-caption').forEach((n) => n.remove());
          const el = document.createElement('div');
          el.className = 'record-caption';
          el.textContent = text;
          if (sub) {
            const small = document.createElement('small');
            small.textContent = sub;
            el.appendChild(small);
          }
          document.body.appendChild(el);
        }
        """,
        {"text": text, "sub": sub},
    )
    wait(page, int(seconds * 1000))


def badge(page: Page, text: str, tone: str = "", seconds: float = 1.5) -> None:
    page.evaluate(
        """
        ({ text, tone }) => {
          document.querySelectorAll('.record-badge').forEach((n) => n.remove());
          const el = document.createElement('div');
          el.className = `record-badge ${tone || ''}`;
          el.textContent = text;
          document.body.appendChild(el);
        }
        """,
        {"text": text, "tone": tone},
    )
    wait(page, int(seconds * 1000))


def clear_badges(page: Page) -> None:
    page.evaluate("() => document.querySelectorAll('.record-badge,.record-caption').forEach((n) => n.remove())")


def wait_run_button(page: Page, timeout: int = 150_000) -> None:
    page.wait_for_function("() => !document.querySelector('#run')?.disabled", timeout=timeout)


def wait_complete(page: Page, timeout: int = 90_000) -> None:
    page.wait_for_function(
        "() => document.querySelector('#status-text')?.textContent === 'COMPLETE'",
        timeout=timeout,
    )


def click_l1_d0(page: Page) -> None:
    page.evaluate(
        """
        () => {
          const grid = document.querySelector('.heat-grid');
          const rowHeaders = [...document.querySelectorAll('.heat-rowh')];
          const colHeaders = [...document.querySelectorAll('.heat-colh')];
          const row = rowHeaders.findIndex((el) => el.textContent.includes('L1'));
          const col = colHeaders.findIndex((el) => el.textContent.includes('D0'));
          if (!grid || row < 0 || col < 0) throw new Error('L1 x D0 cell not found');
          const cols = colHeaders.length;
          const index = 1 + cols + row * (1 + cols) + 1 + col;
          grid.children[index].click();
        }
        """
    )


def record() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(OUT_DIR),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        title_card(
            page,
            "思镜 MindScope",
            "Agent 时间旅行调试器 · 选题一",
            "从零实现 · 禁用 LangChain",
        )
        wait(page, 3200)

        page.goto(BASE_URL, wait_until="networkidle")
        install_overlay(page)
        caption(page, "现场真跑：DeepSeek-V4-Pro + 自写 ReAct 循环", "思考 → 调工具 → 观察 → 最终答案", 2.0)
        page.locator("#task").fill("用 calculator 算 1955-1879，再用一句话告诉我他活了多少岁")
        page.locator("#run").click()
        try:
            wait_run_button(page)
        except PlaywrightTimeoutError:
            caption(page, "live 等待超时，继续录制后续确定性演示", "可重跑脚本覆盖这一段", 2.0)
        caption(page, "6 个工具：计算器、搜索、文件、Python、长期记忆等", "工具调用过程在玻璃盒中逐步可见", 3.0)
        wait(page, 1500)

        page.locator(".demo-btn[data-demo='injection']").click()
        wait_complete(page)
        badge(page, "被劫持：FINAL 泄露 dummy 密钥", "warn", 1.8)
        caption(page, "提示词注入：工具返回夹带恶意指令", "这一幕为确定性复现剧本，用于稳定演示", 3.2)
        page.locator("button.cp").filter(has_text="cp0").first.click()
        wait(page, 1200)
        caption(page, "时间旅行：回到 cp0，追加一条系统规则", "回退 → 改提示词 → 从 checkpoint 重跑 → fork", 3.0)
        page.locator("#rerun").click()
        wait_complete(page)
        badge(page, "新分支识破并拒绝注入", "good", 1.6)
        page.locator("#compare-btn").click()
        wait(page, 1500)
        caption(page, "同一输入，只改一行提示词，结果反转", "提示词即程序", 4.2)

        page.goto(f"{BASE_URL}/lab.html", wait_until="networkidle")
        install_overlay(page)
        caption(page, "提示词注入攻防实验室：攻击 × 防御 ASR 热力图", "真实模型多次运行，统计外泄成功率与置信区间", 2.2)
        click_l1_d0(page)
        wait(page, 1200)
        badge(page, "真实外泄案例：通行码被抄送攻击者", "warn", 1.8)
        caption(page, "D3 权限隔离整列接近 0%", "不要赌检测，要限权。热力图实验模型为 GLM-5.1，N 较小。", 5.0)

        page.goto(BASE_URL, wait_until="networkidle")
        install_overlay(page)
        page.locator("#task").fill("用 calculator 算 (12+8)*5 并总结")
        page.locator(".demo-btn[data-mode='multi']").click()
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('.step').length >= 1 || document.querySelector('#status-text')?.textContent === 'COMPLETE'",
                timeout=30_000,
            )
            wait(page, 8_000)
        except PlaywrightTimeoutError:
            caption(page, "多 Agent live 等待超时，已录到角色流过程", "Planner / Executor / Reflector", 2.0)
        caption(page, "多 Agent：规划器、执行器、反思器协作", "会话可持久化、回放、继续 fork", 3.0)

        title_card(
            page,
            "从零 ReAct 引擎",
            "6 工具 · 时间旅行调试器 · 真实注入攻防实验",
            "代码 / 实验报告 / 调研见仓库",
        )
        wait(page, 3200)

        video = page.video
        context.close()
        if video is None:
            raise RuntimeError("Playwright did not create a video")
        video.save_as(str(OUT_FILE))
        browser.close()
    return OUT_FILE


if __name__ == "__main__":
    out = record()
    temp_files = [p for p in OUT_DIR.glob("*.webm") if p.resolve() != out.resolve()]
    for temp in temp_files:
        try:
            temp.unlink()
        except OSError:
            pass
    print(out)
