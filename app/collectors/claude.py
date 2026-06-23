"""Claude Code 采集器：读取 ~/.claude/projects/ 下的会话 jsonl。

数据源（已实证）：
- projects/<编码项目路径>/<sessionId>.jsonl：每个文件=一个会话，文件名=sessionId
- 项目目录名编码：D:\\pythonproject\\AAIC -> D--pythonproject-AAIC（分隔符替换为-）
- 每行 JSON：{type, message, cwd, sessionId, timestamp, uuid, ...}
  type=user/assistant 为消息行；type=queue-operation 为队列操作（非消息）
- user/assistant 行的 message.content 可能是字符串或数组（含 text/tool_use 块）

设计取舍：
- 无全局索引，按文件 mtime 排序取最近 N 个会话。
- 标题取首条用户消息文本；项目路径优先用行内 cwd（更可靠），回退到目录名反编码。
- 工具调用数 = assistant 消息里 tool_use 块的数量。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .base import BaseCollector, SessionInfo, LEVEL_SESSION

PLATFORM = "claude"
PLATFORM_LABEL = "Claude Code"

DEFAULT_RECENT_LIMIT = 20
ACTIVE_WINDOW_MIN = 10


def _projects_dir() -> Path:
    return Path(os.path.expanduser("~")) / ".claude" / "projects"


class ClaudeCollector(BaseCollector):
    platform = PLATFORM
    platform_label = PLATFORM_LABEL

    def __init__(self, process_running: bool = False, recent_limit: int = DEFAULT_RECENT_LIMIT):
        self.process_running = process_running
        self.recent_limit = recent_limit

    def collect(self) -> list[SessionInfo]:
        root = _projects_dir()
        if not root.exists():
            return []
        # 收集所有会话文件，按 mtime 降序，取最近 N 个
        files = sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
        files = files[: self.recent_limit]

        infos: list[SessionInfo] = []
        for f in files:
            info = self._build(f)
            if info:
                infos.append(info)
        return infos

    def _build(self, path: Path) -> SessionInfo | None:
        session_id = path.stem
        project_dir_name = path.parent.name
        fallback_cwd = _decode_project_dir(project_dir_name)

        msg_count = 0
        tool_count = 0
        last_ts: float | None = None
        last_role = ""
        last_text = ""
        title = ""
        cwd = ""

        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    rtype = o.get("type")
                    # cwd 行内字段比目录名编码更准，优先取
                    if not cwd and o.get("cwd"):
                        cwd = o["cwd"]
                    ts = _parse_ts(o.get("timestamp"))
                    if ts is not None and (last_ts is None or ts > last_ts):
                        last_ts = ts
                    if rtype in ("user", "assistant"):
                        msg_count += 1
                        msg = o.get("message", {})
                        role = msg.get("role", rtype)
                        last_role = role
                        text, n_tools = _scan_content(msg.get("content"))
                        tool_count += n_tools
                        if not text:
                            continue
                        # 首条用户消息作为标题
                        if not title and rtype == "user":
                            title = text.strip().replace("\n", " ")
                        last_text = text
        except OSError:
            return None

        if not cwd:
            cwd = fallback_cwd
        if not title:
            title = session_id
        title = (title[:80] + "…") if len(title) > 80 else title
        preview = _make_preview(last_role, last_text)
        status = self._derive_status(last_ts)

        return SessionInfo(
            platform=PLATFORM,
            platform_label=PLATFORM_LABEL,
            session_id=session_id,
            title=title,
            project_path=cwd,
            status=status,
            level=LEVEL_SESSION,
            last_active_at=last_ts,
            last_message_preview=preview,
            message_count=msg_count,
            tool_call_count=tool_count,
            process_running=self.process_running,
        )

    def _derive_status(self, last_ts: float | None) -> str:
        if last_ts is None:
            return "unknown"
        import time
        age_min = (time.time() - last_ts) / 60
        if self.process_running and age_min < ACTIVE_WINDOW_MIN:
            return "active"
        return "idle"


def _scan_content(content) -> tuple[str, int]:
    """解析 message.content，返回 (文本, 工具调用数)。

    content 可能是 str，或 list[dict]（含 text / tool_use / thinking 等块）。
    """
    if isinstance(content, str):
        return content, 0
    if not isinstance(content, list):
        return "", 0
    texts: list[str] = []
    n_tools = 0
    for item in content:
        if not isinstance(item, dict):
            continue
        btype = item.get("type")
        if btype == "text" and item.get("text"):
            texts.append(str(item["text"]))
        elif btype == "tool_use":
            n_tools += 1
    return " ".join(texts), n_tools


def _make_preview(role: str, text: str) -> str:
    role_cn = {"user": "用户", "assistant": "助手"}.get(role, role)
    if not text:
        return role_cn
    snippet = text.strip().replace("\n", " ")
    if len(snippet) > 80:
        snippet = snippet[:80] + "…"
    return f"{role_cn}: {snippet}" if role_cn else snippet


def _parse_ts(ts) -> float | None:
    """Claude 的 ISO8601（如 2026-06-13T07:21:20.112Z）转 Unix 秒。"""
    if not ts or not isinstance(ts, str):
        return None
    import datetime as dt
    s = ts.replace("Z", "+00:00")
    try:
        return dt.datetime.fromisoformat(s).timestamp()
    except ValueError:
        return None


def _decode_project_dir(name: str) -> str:
    """反编码 Claude 项目目录名为路径。

    编码规则：把路径分隔符 : \\ / 全替换成 -。
    仅作 cwd 缺失时的回退，简单按首段盘符还原（如 D--x-y -> D:\\x\\y）。
    """
    if not name:
        return ""
    parts = name.split("-")
    parts = [p for p in parts if p != ""]
    if not parts:
        return name
    # 形如 ["D","pythonproject","AAIC"] -> D:\pythonproject\AAIC
    if len(parts[0]) == 1 and parts[0].isalpha():
        return "\\".join(parts)
    return "\\".join(parts) if len(parts) > 1 else name


if __name__ == "__main__":
    for info in ClaudeCollector(process_running=True).collect():
        print(
            f"- [{info.status}] {info.title[:40]}  cwd={info.project_path}  "
            f"msgs={info.message_count} tools={info.tool_call_count}  preview={info.last_message_preview[:50]!r}"
        )
