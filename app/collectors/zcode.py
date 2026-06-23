"""ZCode 采集器：读取 ~/.zcode/cli/db/db.sqlite，汇总 ZCode 会话进展。

数据源（已实证 schema）：
- session 表：id/title/directory/path/task_type/time_created/time_updated
- message 表：按 session_id 计数得消息数
- tool_usage 表：按 session_id 计数得工具调用数
- part 表：消息正文与工具调用明细（结构复杂，只取摘要用途）
- session_target 表：本机为空，不依赖

设计取舍：
- subagent_child 类型的会话是子代理临时会话，不单独展示，避免污染主面板。
- session.status 在本机没有可靠来源（session_target 空），改用
  "进程是否在跑 + 最近活动时间" 推导 active/idle。
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Optional

from .base import BaseCollector, SessionInfo, LEVEL_SESSION

PLATFORM = "zcode"
PLATFORM_LABEL = "ZCode"

# ZCode 在跑视为"刚活动过"的窗口（分钟）。进程存活且窗口内有活动 => active。
ACTIVE_WINDOW_MIN = 10


def _db_path() -> Path:
    return Path(os.path.expanduser("~")) / ".zcode" / "cli" / "db" / "db.sqlite"


class ZCodeCollector(BaseCollector):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL

    def __init__(self, process_running: bool = False):
        # 进程探测结果由外部注入，采集器本身不感知系统状态
        self.process_running = process_running

    def collect(self) -> list[SessionInfo]:
        db = _db_path()
        if not db.exists():
            return []

        # 只读连接，且用 immutable=1 规避对正在写入的 WAL 的写锁争用
        uri = f"file:{db.as_posix()}?mode=ro&immutable=1"
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
        try:
            return self._query(conn)
        finally:
            conn.close()

    def _query(self, conn: sqlite3.Connection) -> list[SessionInfo]:
        # 预取计数，避免在主循环里逐会话查询
        msg_counts = self._counts(conn, "SELECT session_id, COUNT(*) c FROM message GROUP BY session_id")
        tool_counts = self._counts(conn, "SELECT session_id, COUNT(*) c FROM tool_usage GROUP BY session_id")

        rows = conn.execute(
            """
            SELECT id, title, directory, path, task_type,
                   time_created, time_updated
            FROM session
            WHERE time_archived IS NULL
            ORDER BY time_updated DESC
            """
        ).fetchall()

        infos: list[SessionInfo] = []
        now_ms = _now_ms()
        for r in rows:
            # 跳过子代理会话：它们是主会话派生的临时上下文，单独列出会噪声
            if r["task_type"] == "subagent_child":
                continue
            sid = r["id"]
            last_ms = r["time_updated"] or r["time_created"] or 0
            last_active_s = last_ms / 1000 if last_ms else None
            status = self._derive_status(last_ms, now_ms)
            preview = self._last_message_preview(conn, sid, last_ms)
            title = (r["title"] or "").strip() or "(无标题)"
            infos.append(
                SessionInfo(
                    platform=PLATFORM,
                    platform_label=PLATFORM_LABEL,
                    session_id=sid,
                    title=title,
                    project_path=r["directory"] or r["path"] or "",
                    status=status,
                    level=LEVEL_SESSION,
                    last_active_at=last_active_s,
                    last_message_preview=preview,
                    message_count=msg_counts.get(sid, 0),
                    tool_call_count=tool_counts.get(sid, 0),
                    process_running=self.process_running,
                )
            )
        return infos

    def _derive_status(self, last_ms: int, now_ms: int) -> str:
        """根据"进程是否存活 + 最近活动"推导状态。"""
        if not last_ms:
            return "unknown"
        age_min = (now_ms - last_ms) / 60000
        if self.process_running and age_min < ACTIVE_WINDOW_MIN:
            return "active"
        return "idle"

    @staticmethod
    def _counts(conn: sqlite3.Connection, sql: str) -> dict[str, int]:
        return {row["session_id"]: row["c"] for row in conn.execute(sql)}

    @staticmethod
    def _last_message_preview(conn: sqlite3.Connection, session_id: str, last_ms: int) -> str:
        """取该会话最新一条 message 的角色/模型作为轻量摘要。

        不深入 part 表解析正文：那需要处理 tool/text/step-start 等多种 part 类型，
        对"这个会话最后在干什么"的提示来说，role+model+时间已经够用，且更稳。
        """
        row = conn.execute(
            "SELECT data FROM message WHERE session_id=? ORDER BY time_created DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        if not row or not row["data"]:
            return ""
        try:
            d = json.loads(row["data"])
        except (ValueError, TypeError):
            return ""
        role = d.get("role", "")
        model = d.get("modelID", "")
        finish = d.get("finish", "")
        bits = [role] if role else []
        if model:
            bits.append(model)
        if finish == "tool-calls":
            bits.append("调用工具")
        return " · ".join(bits) if bits else ""


def _now_ms() -> int:
    import time
    return int(time.time() * 1000)


if __name__ == "__main__":
    # 自检：打印当前 ZCode 会话概览
    coll = ZCodeCollector(process_running=True)
    for info in coll.collect():
        print(f"- [{info.status}] {info.title[:40]}  msgs={info.message_count} tools={info.tool_call_count}  preview={info.last_message_preview!r}")
