"""平台路径配置层：自动扫描 + 本地持久化。

设计取舍（软件化但不引入安装器）：
- 不在"安装时"申请权限扫描（那是发布打包阶段的事，现在做是推测性设计）。
- 首次运行时自动扫描常见安装位置，扫到的写入 config.json；
  扫不到的留空，前端打开时提示"未配置路径，点击此处设置"。
- config.json 放在用户家目录的 .ai-dashboard/ 下，跨项目可移植。

只存"程序可执行文件路径"，不存会话/项目等运行时数据。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# 配置目录与文件
CONFIG_DIR = Path.home() / ".ai-dashboard"
CONFIG_FILE = CONFIG_DIR / "config.json"

# 各平台配置键 -> 默认 exe 文件名（用于扫描时的文件名匹配）
_PLATFORM_EXE = {
    "zcode": "ZCode.exe",
    "cursor": "Cursor.exe",
    "pycharm": "pycharm64.exe",
    "idea": "idea64.exe",
    "goland": "goland64.exe",
    "clion": "clion64.exe",
    "rustrover": "rustrover64.exe",
    "codex": "codex.cmd",   # Codex CLI
    "claude": "claude.cmd",  # Claude CLI
}

# 自动扫描的根目录（覆盖本机常见的安装盘/目录）
_SCAN_ROOTS = [
    r"D:\AppGallery",
    r"D:\JetBrains",
    r"D:\Clion",
    r"D:\Goland",
    r"D:\nodejs",
    r"C:\Program Files\JetBrains",
    r"C:\Program Files (x86)\JetBrains",
    r"D:\miniconda3\Scripts",
    Path.home() / "AppData" / "Local" / "Programs",
    Path.home() / "AppData" / "Roaming",
    Path.home() / ".zcode",
    Path.home() / ".codex",
]
# 注：不扫整个 D:\ 根（目录过宽，BFS 限深内命中率低且耗时）。
# 直接装在盘根的 IDE（如 D:\PyCharm 2024.2.3\）由用户手动配置补充。


def load() -> dict:
    """读取配置，不存在则返回空字典。"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}


def save(config: dict) -> None:
    """写入配置到 ~/.ai-dashboard/config.json。"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8")


def scan() -> dict:
    """扫描常见安装位置，返回 {platform: exe_path}。

    扫描是近似匹配：在已知根目录下递归找匹配文件名的 exe/cmd。
    为控制耗时，限制递归深度。扫不到的键不出现（保持空）。
    """
    found: dict[str, str] = {}
    for platform, exe in _PLATFORM_EXE.items():
        path = _find(exe)
        if path:
            found[platform] = str(path)
    return found


def _find(filename: str) -> Path | None:
    """在所有扫描根目录里找指定文件名，返回第一个命中。

    用限深遍历（最多 3 层）而非 rglob，避免对 D:\ 这类大根目录全盘扫描耗时。
    IDE 安装结构通常在「盘根\\产品名\\bin\\exe」三层以内。
    """
    for root in _SCAN_ROOTS:
        root_path = Path(root)
        if not root_path.exists():
            continue
        for p in _walk_limited(root_path, filename, max_depth=3):
            return p
    return None


def _walk_limited(root: Path, filename: str, max_depth: int):
    """限深广度优先遍历，命中即返回。跳过缓存/资源类子目录。"""
    from collections import deque
    queue = deque([(root, 0)])
    while queue:
        cur, depth = queue.popleft()
        try:
            entries = list(cur.iterdir())
        except (PermissionError, OSError):
            continue
        for entry in entries:
            if entry.is_file() and entry.name.lower() == filename.lower():
                lower = str(entry).lower()
                if any(s in lower for s in ("cache", "resources", "plugins", "node_modules")):
                    continue
                yield entry
                return
            elif entry.is_dir() and depth < max_depth:
                queue.append((entry, depth + 1))


def ensure_config() -> dict:
    """首次运行自动扫描：若配置文件不存在或某平台缺失，补扫一次并持久化。

    返回当前有效配置。已存在的路径不覆盖（用户手动设置优先）。
    """
    config = load()
    changed = False
    if not config:
        # 完全没有配置，全量扫描
        config = scan()
        changed = bool(config)
    else:
        # 已有配置，仅补扫缺失的键
        scanned = scan()
        for k, v in scanned.items():
            if k not in config:
                config[k] = v
                changed = True
    if changed:
        save(config)
    return config


def get_path(platform: str) -> str:
    """取某平台配置的 exe 路径，未配置返回空串。"""
    return load().get(platform, "")


def set_path(platform: str, path: str) -> None:
    """手动设置某平台路径（前端"自定义路径"入口用）。"""
    config = load()
    config[platform] = path
    save(config)


if __name__ == "__main__":
    print("config dir:", CONFIG_DIR)
    print("scanning...")
    result = scan()
    for k, v in sorted(result.items()):
        print(f"  {k}: {v}")
    missing = [k for k in _PLATFORM_EXE if k not in result]
    if missing:
        print("  未找到:", ", ".join(missing))
