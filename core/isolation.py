"""分支本地副作用隔离（Codex 复审 #1/#12）。

fork 重跑时，给新分支一份独立的 workspace 副本 + branch-local 记忆文件，
使分支内的 file_write / memory_store 不污染原分支。
"""
from __future__ import annotations

import shutil

import config


def isolate_side_effects(branch):
    """返回 (branch_workspace_path, branch_memory_path)。"""
    bdir = config.WORKSPACE / "branches" / str(branch)
    bdir.mkdir(parents=True, exist_ok=True)

    # 把主 workspace 当前文件拷进分支目录（排除 branches/ 自身），作为分支起点
    for item in config.WORKSPACE.iterdir():
        if item.name == "branches":
            continue
        dest = bdir / item.name
        if item.is_dir():
            shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(item, dest)

    mem = config.DATA / f"memory_branch_{branch}.json"
    main_mem = config.DATA / "memory.json"
    if main_mem.exists() and not mem.exists():
        shutil.copy2(main_mem, mem)
    return bdir, mem
