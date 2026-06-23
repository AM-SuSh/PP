"""聚合后端：运行所有采集器，提供 HTTP 接口给前端。

职责：
- 进程探测一次（有开销），结果注入各 IDE 采集器
- 聚合 ZCode/Codex/Claude(session 级) + JetBrains/Cursor(activity 级)
- /api/sessions 返回聚合 JSON
- 静态服务 web/ 目录
- 缓存最近一次采集结果；watcher 检测到变化时调 invalidate() 使下次请求重采
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from flask import Flask, jsonify, send_from_directory

from .collectors.claude import ClaudeCollector
from .collectors.codex import CodexCollector
from .collectors.cursor import CursorCollector
from .collectors.jetbrains import (
    JetBrainsCollector,
    _IDE_DIRS,
)
from .collectors.process_probe import is_platform_running, probe_running_processes
from .collectors.zcode import ZCodeCollector

WEB_DIR = Path(__file__).parent / "web"


class Aggregator:
    """采集聚合器，带线程安全的缓存。"""

    def __init__(self):
        self._lock = threading.Lock()
        self._cache: dict | None = None
        self._cache_ts: float = 0.0
        # 缓存有效期：watcher 即时 invalidate 后置 0，兜底则用这个 TTL 自动过期
        self._ttl = 5.0

    def invalidate(self) -> None:
        """watcher 检测到文件变化时调用，使下次 get_sessions() 重新采集。"""
        with self._lock:
            self._cache = None

    def get_sessions(self, force: bool = False) -> dict:
        now = time.time()
        with self._lock:
            if self._cache is not None and not force and (now - self._cache_ts) < self._ttl:
                return self._cache
        data = self._collect_all()
        with self._lock:
            self._cache = data
            self._cache_ts = now
        return data

    def _collect_all(self) -> dict:
        # 进程探测一次，分发到各采集器
        running = probe_running_processes()
        jetbrains_running = {
            key: is_platform_running(key, running) for key, _ in _IDE_DIRS.values()
        }
        cursor_running = is_platform_running("cursor", running)
        zcode_running = is_platform_running("zcode", running)

        collectors = [
            ZCodeCollector(process_running=zcode_running),
            CodexCollector(process_running=False),
            ClaudeCollector(process_running=False),
            JetBrainsCollector(process_running_map=jetbrains_running),
            CursorCollector(process_running=cursor_running),
        ]

        sessions = []
        for c in collectors:
            sessions.extend(c._safe_collect())

        # 默认只保留今日有活动的会话（用户需求：不要读取全部历史会话）
        sessions = [s for s in sessions if _is_today(s.last_active_at)]

        # 附带各平台路径配置状态，前端据此判断"该平台能否点击打开"
        from . import config as config_mod
        paths = config_mod.load()

        return {
            "generated_at": time.time(),
            "platforms_running": sorted(running),
            "platform_paths": paths,
            "sessions": [s.to_dict() for s in sessions],
        }


def _is_today(ts) -> bool:
    """时间戳（秒）是否在今天（本地时区）。无时间戳视为不在今日。"""
    import datetime as _dt
    if ts is None:
        return False
    try:
        d = _dt.datetime.fromtimestamp(float(ts))
    except (TypeError, ValueError, OSError):
        return False
    return d.date() == _dt.datetime.now().date()


aggregator = Aggregator()
app = Flask(__name__, static_folder=None)


@app.get("/api/sessions")
def api_sessions():
    force = _bool_arg("force")
    return jsonify(aggregator.get_sessions(force=force))


@app.get("/api/invalidate")
def api_invalidate():
    aggregator.invalidate()
    return jsonify({"ok": True})


@app.post("/api/launch")
def api_launch():
    """点击卡片打开对应平台。body: {platform, project_path}。"""
    from flask import request
    from . import launcher
    body = request.get_json(silent=True) or {}
    platform = (body.get("platform") or "").strip()
    project_path = (body.get("project_path") or "").strip()
    if not platform:
        return jsonify({"ok": False, "message": "缺少 platform"}), 400
    return jsonify(launcher.launch(platform, project_path))


@app.get("/api/config")
def api_config_get():
    """返回当前平台路径配置。"""
    from . import config as config_mod
    return jsonify(config_mod.load())


@app.post("/api/config")
def api_config_set():
    """手动设置某平台路径。body: {platform, path}。"""
    from flask import request
    from . import config as config_mod
    body = request.get_json(silent=True) or {}
    platform = (body.get("platform") or "").strip()
    path = (body.get("path") or "").strip()
    if not platform or not path:
        return jsonify({"ok": False, "message": "需要 platform 和 path"}), 400
    config_mod.set_path(platform, path)
    return jsonify({"ok": True})


@app.get("/")
def index():
    return send_from_directory(WEB_DIR, "index.html")


@app.get("/<path:filename>")
def static_files(filename: str):
    return send_from_directory(WEB_DIR, filename)


def _bool_arg(name: str) -> bool:
    from flask import request
    return request.args.get(name, "").lower() in ("1", "true", "yes")


def run(host: str = "127.0.0.1", port: int = 7321) -> None:
    """启动后端（后台线程调用）。"""
    app.run(host=host, port=port, debug=False, use_reloader=False, threaded=True)


if __name__ == "__main__":
    # 自检：打印聚合结果摘要
    data = aggregator.get_sessions(force=True)
    print(f"generated at: {time.strftime('%H:%M:%S', time.localtime(data['generated_at']))}")
    print(f"platforms running: {data['platforms_running']}")
    print(f"total sessions: {len(data['sessions'])}")
    from collections import Counter
    by_platform = Counter(s["platform"] for s in data["sessions"])
    for k, v in by_platform.most_common():
        print(f"  {k}: {v}")
