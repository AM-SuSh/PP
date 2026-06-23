"""文件监听 + 兜底轮询的混合刷新。

设计依据（已实证 Windows 边界）：
- watchdog 在 Windows 上对持续追加的 jsonl 和 SQLite-WAL 可能漏触发或延迟。
- 因此采用"watchdog 事件去抖触发 + 定时兜底轮询"双保险：
  1. watchdog 监听到任一数据源变化 => 去抖后 invalidate 缓存
  2. 每 FALLBACK_SEC 秒兜底 invalidate 一次，弥补漏触发
- 准实时（秒级到 30 秒级），不承诺纯实时。

去抖：连续变化会合并，避免高频写入（如大模型流式输出刷写 jsonl）刷爆采集。
"""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# 监听的目录：各平台会话存储根目录（监父目录，靠 pattern 过滤减少噪音）
_WATCH_TARGETS = [
    (Path.home() / ".zcode" / "cli" / "db", None),        # ZCode sqlite
    (Path.home() / ".codex", "session_index.jsonl"),       # Codex 索引
    (Path.home() / ".claude" / "projects", ".jsonl"),      # Claude 会话
    (Path(os.path.expandvars(r"%APPDATA%")) / "JetBrains", "recentProjects.xml"),
    (Path(os.path.expandvars(r"%APPDATA%")) / "Cursor" / "User" / "workspaceStorage", "workspace.json"),
]

DEBOUNCE_SEC = 2.0       # 文件变化去抖窗口
FALLBACK_SEC = 30.0      # 兜底轮询周期（弥补 watchdog 漏触发）


class _Handler(FileSystemEventHandler):
    def __init__(self, on_change, pattern):
        self._on_change = on_change
        self._pattern = pattern

    def _maybe(self, src_path: str | None):
        if not src_path:
            return
        if self._pattern and not src_path.endswith(self._pattern):
            return
        self._on_change()

    def on_modified(self, event):
        if not event.is_directory:
            self._maybe(event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._maybe(event.src_path)


class Watcher:
    def __init__(self, aggregator):
        self._agg = aggregator
        self._observer = Observer()
        self._debounce_timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._fallback_thread: threading.Thread | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        for path, pattern in _WATCH_TARGETS:
            if not path.exists():
                continue
            handler = _Handler(self._schedule_invalidate, pattern)
            # 监听目录本身，pattern 在 handler 内过滤
            self._observer.schedule(handler, str(path), recursive=True)
        self._observer.start()

        self._fallback_thread = threading.Thread(
            target=self._fallback_loop, name="dashboard-fallback", daemon=True
        )
        self._fallback_thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._observer.stop()
        self._observer.join(timeout=2)

    def _schedule_invalidate(self) -> None:
        """去抖：合并 DEBOUNCE_SEC 窗口内的多次变化为一次 invalidate。"""
        with self._lock:
            if self._debounce_timer is not None:
                self._debounce_timer.cancel()
            self._debounce_timer = threading.Timer(DEBOUNCE_SEC, self._do_invalidate)
            self._debounce_timer.daemon = True
            self._debounce_timer.start()

    def _do_invalidate(self) -> None:
        try:
            self._agg.invalidate()
        except Exception as e:  # noqa: BLE001
            print(f"[watcher] invalidate failed: {e}")

    def _fallback_loop(self) -> None:
        """兜底：每 FALLBACK_SEC 秒 invalidate 一次。"""
        while not self._stop.wait(FALLBACK_SEC):
            self._do_invalidate()


if __name__ == "__main__":
    # 自检：监听 30 秒，打印每次 invalidate 触发
    from .server import aggregator

    w = Watcher(aggregator)
    w.start()
    print("watching for 30s, try editing a watched file...")
    deadline = time.time() + 30
    n = 0
    while time.time() < deadline:
        time.sleep(1)
    w.stop()
    print("done")
