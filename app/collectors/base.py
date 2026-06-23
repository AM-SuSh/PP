"""统一数据模型与采集器基类。

所有平台采集器都返回 SessionInfo 列表，前端据此统一渲染。
这是整个仪表盘数据层的契约，字段一旦定下前端就会依赖，不要随意增删。
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Optional


# 会话级别（CLI 三家：能读到 AI 对话内容与真实进展）
LEVEL_SESSION = "session"
# 活动级别（JetBrains/Cursor：只有项目活动 + 进程，读不到 AI 对话）
LEVEL_ACTIVITY = "activity"


@dataclass
class SessionInfo:
    """单个工作项的统一表示。

    对 CLI 平台：一个 SessionInfo = 一个 AI 会话。
    对 IDE 平台：一个 SessionInfo = 一个最近打开的项目（活动级，无对话内容）。
    """

    platform: str                       # zcode / codex / claude / pycharm / cursor ...
    platform_label: str                 # 展示用名称：ZCode / Codex / Claude Code ...
    session_id: str                     # 各平台内的唯一标识
    title: str                          # 会话标题或项目名
    project_path: str = ""              # 所在仓库/目录路径
    status: str = "unknown"             # active / paused / complete / idle / running / unknown
    level: str = LEVEL_SESSION          # session 级还是 activity 级
    last_active_at: Optional[float] = None   # 最后活动 Unix 时间戳（秒）
    last_message_preview: str = ""      # 最后一条消息摘要（仅 session 级有）
    message_count: int = 0              # 消息数
    tool_call_count: int = 0            # 工具调用数
    process_running: bool = False       # 该平台进程当前是否存活
    extra: dict = field(default_factory=dict)  # 平台特有信息，前端不强依赖

    def to_dict(self) -> dict:
        d = dataclasses.asdict(self)
        # 时间戳转 ISO 字符串，方便前端直接渲染；None 保留
        d["last_active_at"] = (
            _ts_to_iso(self.last_active_at) if self.last_active_at is not None else None
        )
        return d


def _ts_to_iso(ts: float) -> str:
    """Unix 秒时间戳转 ISO8601 字符串（本地时区）。"""
    import datetime as _dt
    return _dt.datetime.fromtimestamp(ts).isoformat(timespec="seconds")


class BaseCollector:
    """采集器基类。子类实现 collect() 返回 SessionInfo 列表。"""

    platform: str = ""
    platform_label: str = ""

    def collect(self) -> list[SessionInfo]:
        raise NotImplementedError

    def _safe_collect(self) -> list[SessionInfo]:
        """带兜底的采集入口：采集出错时返回空列表而非抛异常。

        单个平台采集失败不应拖垮整个仪表盘。
        """
        try:
            return self.collect()
        except Exception as e:  # noqa: BLE001 - 采集层必须容错
            print(f"[collector:{self.platform}] collect failed: {e}")
            return []
