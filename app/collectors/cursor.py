"""Cursor 采集器：读取 workspaceStorage 下的 workspace.json。

数据源（已实证）：
- %APPDATA%/Cursor/User/workspaceStorage/<id>/workspace.json
- 内容形如 {"folder": "file:///d%3A/pythonproject/OS/..."}
- folder 是 URL 编码的 file:// 路径，解码即项目路径
- 活动时间用 workspaceStorage 子目录的 mtime（无显式时间戳字段）

边界说明（诚实降级，同 JetBrains）：
- Cursor 的 AI 对话存私有 LevelDB，读不到。只给出"最近 workspace + 进程状态"，
  属活动级别（LEVEL_ACTIVITY），不显示消息/工具调用数。
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from .base import BaseCollector, SessionInfo, LEVEL_ACTIVITY

PLATFORM = "cursor"
PLATFORM_LABEL = "Cursor"

DEFAULT_RECENT_LIMIT = 8


def _storage_dir() -> Path:
    return Path(os.path.expandvars(r"%APPDATA%")) / "Cursor" / "User" / "workspaceStorage"


class CursorCollector(BaseCollector):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL

    def __init__(self, process_running: bool = False, recent_limit: int = DEFAULT_RECENT_LIMIT):
        self.process_running = process_running
        self.recent_limit = recent_limit

    def collect(self) -> list[SessionInfo]:
        root = _storage_dir()
        if not root.exists():
            return []
        items: list[SessionInfo] = []
        for d in root.iterdir():
            if not d.is_dir():
                continue
            info = self._build(d)
            if info:
                items.append(info)
        items.sort(key=lambda i: i.last_active_at or 0, reverse=True)
        return items[: self.recent_limit]

    def _build(self, ws_dir: Path) -> SessionInfo | None:
        ws_json = ws_dir / "workspace.json"
        if not ws_json.exists():
            return None
        import json
        try:
            data = json.loads(ws_json.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        folder = data.get("folder", "")
        path = _decode_folder(folder)
        if not path:
            return None
        last_active_s = ws_dir.stat().st_mtime
        status = "active" if self.process_running else "idle"
        return SessionInfo(
            platform=PLATFORM,
            platform_label=PLATFORM_LABEL,
            session_id=f"cursor:{ws_dir.name}",
            title=Path(path).name or path,
            project_path=path,
            status=status,
            level=LEVEL_ACTIVITY,
            last_active_at=last_active_s,
            last_message_preview="",
            message_count=0,
            tool_call_count=0,
            process_running=self.process_running,
        )


def _decode_folder(folder: str) -> str:
    """file:///d%3A/pythonproject/... -> d:\\pythonproject\\..."""
    if not folder:
        return ""
    parsed = urlparse(folder)
    # file:// 的路径在 Windows 是 /d:/... 形式
    netloc = parsed.netloc
    p = unquote(parsed.path)
    if p.startswith("/") and len(p) > 2 and p[2] == ":":
        # /d:/x/y -> d:\x\y
        p = p[1:].replace("/", "\\")
    elif netloc:
        p = (netloc + p).replace("/", "\\")
    return p


if __name__ == "__main__":
    for info in CursorCollector(process_running=False).collect():
        print(f"- [{info.status}] {info.title}  path={info.project_path}")
