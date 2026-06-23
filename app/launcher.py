"""平台启动器：激活应用并定位到项目。

按"激活应用 + 定位项目"策略：
- GUI 应用（ZCode/Cursor/JetBrains）：启动 exe，能传项目路径的传路径
- CLI 工具（Codex/Claude）：在项目目录开一个终端窗口运行命令

注意：会真实启动外部进程/弹窗。本模块只提供启动能力，调用方（server 接口）
负责接收用户点击触发。
"""
from __future__ import annotations

import os
import subprocess

from .config import get_path

# GUI 类：能接受项目路径参数的 exe
_GUI_WITH_PATH = {"cursor", "pycharm", "idea", "goland", "clion", "rustrover"}
# GUI 类：只激活窗口，不接受项目参数
_GUI_PLAIN = {"zcode"}
# CLI 类：在项目目录开终端运行
_CLI = {"codex", "claude"}


def launch(platform: str, project_path: str = "") -> dict:
    """启动某平台，定位到项目。返回结果 dict（供前端展示）。

    返回 {ok, message}。未配置路径、路径不存在、启动失败都返回 ok=False + 原因。
    """
    exe = get_path(platform)
    if not exe:
        return {"ok": False, "message": f"未配置 {platform} 的程序路径，请先在设置中指定"}

    if platform in _GUI_WITH_PATH and project_path:
        return _start([exe, project_path], platform)
    if platform in _GUI_PLAIN:
        return _start([exe], platform)
    if platform in _CLI:
        return _open_terminal(exe, project_path, platform)
    # 未知类型，尽力直接启动
    return _start([exe], platform)


def _start(cmd: list[str], platform: str) -> dict:
    """启动 GUI 进程（脱离父进程独立运行）。"""
    try:
        # DETACHED_PROCESS 让子进程独立，不随本仪表盘关闭而退出
        subprocess.Popen(
            cmd,
            close_fds=True,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        )
    except (OSError, ValueError) as e:
        return {"ok": False, "message": f"启动 {platform} 失败：{e}"}
    return {"ok": True, "message": f"已激活 {platform}"}


def _open_terminal(cli_cmd: str, project_path: str, platform: str) -> dict:
    """在项目目录开一个终端窗口运行 CLI（Codex/Claude）。

    用 cmd /K 开一个新 cmd 窗口，cd 到项目目录后运行命令；窗口保持打开。
    """
    work_dir = project_path if project_path and os.path.isdir(project_path) else None
    # 构造: cmd /K "cd /d <dir> && <cli>"
    if work_dir:
        full = f'cmd /K "cd /d "{work_dir}" && "{cli_cmd}""'
    else:
        full = f'cmd /K "{cli_cmd}"'
    try:
        subprocess.Popen(full, shell=True, creationflags=subprocess.CREATE_NEW_CONSOLE)
    except (OSError, ValueError) as e:
        return {"ok": False, "message": f"打开 {platform} 终端失败：{e}"}
    return {"ok": True, "message": f"已在项目目录打开 {platform} 终端"}


if __name__ == "__main__":
    # 自检：只打印将执行的命令，不实际启动（避免副作用）
    from .config import ensure_config

    ensure_config()
    for plat in ["zcode", "cursor", "pycharm", "codex", "claude", "idea"]:
        exe = get_path(plat)
        sample_path = r"D:\pythonproject\PP"
        # 模拟 launch 逻辑构造命令，仅打印
        if plat in _GUI_WITH_PATH:
            cmd = [exe, sample_path]
        elif plat in _CLI:
            cmd = f'cmd /K "cd /d "{sample_path}" && "{exe}""'
        else:
            cmd = [exe]
        print(f"  {plat}: {cmd}")
