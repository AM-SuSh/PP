"""仪表盘入口：启动 watcher + Flask 后端 + pywebview 窗口。

启动顺序：
1. 起 watcher 线程（监听各平台存储变化，触发后端缓存失效）
2. 起 Flask 后端（daemon 线程，提供 /api/sessions 与静态文件）
3. 主线程开 pywebview 窗口，加载 http://127.0.0.1:PORT/
4. 窗口关闭 => 进程退出，daemon 线程随之结束

端口 7321 写死，避免引入配置文件（最小化）。如被占用会启动失败并提示。
"""
from __future__ import annotations

import sys
import threading

import webview

from .server import aggregator, run
from .watcher import Watcher

HOST = "127.0.0.1"
PORT = 7321
TITLE = "AI 任务并行仪表盘"
WIDTH = 1280
HEIGHT = 860


def main() -> int:
    watcher = Watcher(aggregator)
    watcher.start()

    backend = threading.Thread(
        target=run, args=(HOST, PORT), name="dashboard-backend", daemon=True
    )
    backend.start()

    # 给后端一点启动时间，避免窗口先于服务打开
    import time
    time.sleep(0.8)

    webview.create_window(
        TITLE,
        f"http://{HOST}:{PORT}/",
        width=WIDTH,
        height=HEIGHT,
        min_size=(900, 560),
    )
    try:
        webview.start()
    finally:
        watcher.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
