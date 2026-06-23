"""进程探测：判断各 AI/IDE 平台当前是否在运行。

在 Windows 上用 PowerShell 的 Get-Process（比 tasklist+findstr 在本机更稳，
findstr 多词参数会被 MSYS 误解析）。一次调用拿到所有目标进程名集合，
各采集器据此判定 process_running。

边界说明（已实证）：
- ZCode.exe / 各 JetBrains IDE 的 *.exe / Cursor.exe 能靠进程名可靠识别。
- Codex / Claude CLI 以 node 子进程形式运行，单凭进程名分不出。
  本期不单独探测这两个进程，其状态改由会话最近活动时间推导，足够用。
"""
from __future__ import annotations

import subprocess

# 用进程名能可靠识别的平台
_TARGET_PROCESSES = {
    "zcode": ["ZCode"],
    "pycharm": ["pycharm64"],
    "idea": ["idea64"],
    "webstorm": ["webstorm64"],
    "goland": ["goland64"],
    "clion": ["clion64"],
    "rustrover": ["rustrover64"],
    "cursor": ["Cursor"],
}


def probe_running_processes() -> set[str]:
    """返回当前正在运行的目标进程名集合（小写）。

    失败时返回空集，调用方据此把 process_running 视为 False，
    不让进程探测失败拖垮整个仪表盘。
    """
    names = ",".join(
        proc for procs in _TARGET_PROCESSES.values() for proc in procs
    )
    ps = (
        "Get-Process -Name " + names + " -ErrorAction SilentlyContinue "
        "| Select-Object -ExpandProperty Name"
    )
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (subprocess.SubprocessError, OSError):
        return set()
    running = {line.strip().lower() for line in out.stdout.splitlines() if line.strip()}
    return running


def is_platform_running(platform: str, running: set[str]) -> bool:
    """某平台是否在运行。platform 用 collector 的 platform key。"""
    procs = _TARGET_PROCESSES.get(platform, [])
    return any(p.lower() in running for p in procs)


if __name__ == "__main__":
    running = probe_running_processes()
    print("running:", running)
    for plat in _TARGET_PROCESSES:
        print(f"  {plat}: {is_platform_running(plat, running)}")
