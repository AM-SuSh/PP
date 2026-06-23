"""Codex 采集器：读取 ~/.codex/ 会话索引与会话 jsonl。

数据源（已实证）：
- session_index.jsonl：每行 {id, thread_name, updated_at}，全局会话索引
- sessions/YYYY/MM/DD/rollout-*.jsonl：单会话明细，文件名含 session id；
  每行 {timestamp, type, payload}，type∈{session_meta, response_item, event_msg...}
- response_item 的 payload.type 决定记录种类：
  message=对话消息(含 payload.role=user/assistant/developer)
  function_call/custom_tool_call=工具调用
  reasoning=思考(不计入消息)
  *_output=工具返回(不计入调用)

设计取舍：
- 索引只有标题和时间，cwd/计数/摘要必须逐个打开会话文件聚合，成本较高。
  因此默认只处理最近 N 个会话，避免每次刷新全量扫描。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .base import BaseCollector, SessionInfo, LEVEL_SESSION

PLATFORM = "codex"
PLATFORM_LABEL = "Codex"

# 工具调用类型
_TOOL_TYPES = {"function_call", "custom_tool_call"}
# 默认只聚合最近的会话数（旧会话多为 idle，全量扫描收益低、成本高）
DEFAULT_RECENT_LIMIT = 20
ACTIVE_WINDOW_MIN = 10


def _codex_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".codex"


def _index_path() -> Path:
    return _codex_dir() / "session_index.jsonl"


def _sessions_dir() -> Path:
    return _codex_dir() / "sessions"


def _find_session_file(session_id: str) -> Path | None:
    """按 session id 在 sessions/ 树里定位会话文件（文件名包含该 id）。"""
    root = _sessions_dir()
    if not root.exists():
        return None
    for p in root.rglob(f"*{session_id}*.jsonl"):
        return p
    return None


class CodexCollector(BaseCollector):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL

    def __init__(self, process_running: bool = False, recent_limit: int = DEFAULT_RECENT_LIMIT):
        self.process_running = process_running
        self.recent_limit = recent_limit

    def collect(self) -> list[SessionInfo]:
        idx = _index_path()
        if not idx.exists():
            return []
        # 索引按 updated_at 排序后取最近 N 个
        entries = []
        with open(idx, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except ValueError:
                    continue
        entries.sort(key=lambda e: e.get("updated_at", ""), reverse=True)
        entries = entries[: self.recent_limit]

        infos: list[SessionInfo] = []
        for e in entries:
            info = self._build(e)
            if info:
                infos.append(info)
        return infos

    def _build(self, entry: dict) -> SessionInfo | None:
        sid = entry.get("id", "")
        if not sid:
            return None
        title = (entry.get("thread_name") or "").strip() or "(无标题)"
        updated_at = entry.get("updated_at", "")
        last_active_s = _iso_to_ts(updated_at)
        detail = self._read_detail(sid)
        status = self._derive_status(last_active_s)
        return SessionInfo(
            platform=PLATFORM,
            platform_label=PLATFORM_LABEL,
            session_id=sid,
            title=title,
            project_path=detail["cwd"],
            status=status,
            level=LEVEL_SESSION,
            last_active_at=last_active_s,
            last_message_preview=detail["preview"],
            message_count=detail["msg_count"],
            tool_call_count=detail["tool_count"],
            process_running=self.process_running,
        )

    def _read_detail(self, session_id: str) -> dict:
        """打开单会话 jsonl，聚合 cwd / 消息数 / 工具调用数 / 最后消息摘要。"""
        f = _find_session_file(session_id)
        empty = {"cwd": "", "msg_count": 0, "tool_count": 0, "preview": ""}
        if not f:
            return empty
        cwd = ""
        msg_count = 0
        tool_count = 0
        last_role = ""
        last_text = ""
        try:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    rtype = o.get("type")
                    payload = o.get("payload", {})
                    # cwd 在 session_meta / turn_context 里，不在 response_item 里
                    if not cwd and rtype in ("session_meta", "turn_context") and payload.get("cwd"):
                        cwd = payload["cwd"]
                    if rtype != "response_item":
                        continue
                    ptype = payload.get("type")
                    if ptype == "message":
                        msg_count += 1
                        role = payload.get("role", "")
                        last_role = role
                        last_text = _extract_message_text(payload)
                        continue
                    if ptype in _TOOL_TYPES:
                        tool_count += 1
                        continue
        except OSError:
            return empty
        preview = _make_preview(last_role, last_text)
        return {"cwd": cwd, "msg_count": msg_count, "tool_count": tool_count, "preview": preview}

    def _derive_status(self, last_active_s: float | None) -> str:
        if last_active_s is None:
            return "unknown"
        import time
        age_min = (time.time() - last_active_s) / 60
        if self.process_running and age_min < ACTIVE_WINDOW_MIN:
            return "active"
        return "idle"


def _extract_message_text(payload: dict) -> str:
    """从 message payload 提取纯文本（content 可能是字符串或数组）。"""
    content = payload.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                t = item.get("text") or item.get("input_text")
                if t:
                    parts.append(str(t))
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _make_preview(role: str, text: str) -> str:
    role_cn = {"user": "用户", "assistant": "助手", "developer": "系统"}.get(role, role)
    if not text:
        return role_cn
    snippet = text.strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = snippet[:80] + "…"
    return f"{role_cn}: {snippet}" if role_cn else snippet


def _iso_to_ts(iso: str) -> float | None:
    """Codex 的 ISO8601（如 2026-06-22T13:49:01.000000Z）转 Unix 秒。"""
    if not iso:
        return None
    import datetime as dt
    s = iso.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


if __name__ == "__main__":
    for info in CodexCollector(process_running=True).collect():
        print(
            f"- [{info.status}] {info.title[:40]}  cwd={info.project_path}  "
            f"msgs={info.message_count} tools={info.tool_call_count}  preview={info.last_message_preview[:50]!r}"
        )
