"""JetBrains 全家桶采集器：解析各 IDE 的 recentProjects.xml。

数据源（已实证）：
- %APPDATA%/JetBrains/<IDE><版本>/options/recentProjects.xml
- 每个项目是一个 <entry key="项目路径">，内含 <RecentProjectMetaInfo>
- activationTimestamp：最后激活时间（Unix 毫秒）
- opened="true"：当前在该 IDE 中打开着
- productionCode：标识 IDE（PY=PyCharm, GO=GoLand, CL=CLion, IC/IU=IDEA, RR=RustRover...）

边界说明（诚实降级）：
- JetBrains 的 AI 对话存私有库，读不到。本采集器只能给出"最近项目 + 进程状态"，
  属活动级别（LEVEL_ACTIVITY），不显示消息/工具调用数。前端会用不同样式标注。
"""
from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from pathlib import Path

from .base import BaseCollector, SessionInfo, LEVEL_ACTIVITY

# IDE 目录前缀 -> (platform key, 中文标签)
_IDE_DIRS = {
    "PyCharm": ("pycharm", "PyCharm"),
    "IntelliJIdea": ("idea", "IntelliJ IDEA"),
    "GoLand": ("goland", "GoLand"),
    "CLion": ("clion", "CLion"),
    "RustRover": ("rustrover", "RustRover"),
    "WebStorm": ("webstorm", "WebStorm"),
}

DEFAULT_RECENT_LIMIT = 12


def _jetbrains_root() -> Path:
    return Path(os.path.expandvars(r"%APPDATA%")) / "JetBrains"


class JetBrainsCollector(BaseCollector):
    """聚合所有 JetBrains IDE 的最近项目。

    process_running_map: {platform_key: bool}，由进程探测注入，
    用于判定每个项目对应的 IDE 当前是否在运行。
    """

    def __init__(self, process_running_map: dict[str, bool] | None = None,
                 recent_limit: int = DEFAULT_RECENT_LIMIT):
        self.process_running_map = process_running_map or {}
        self.recent_limit = recent_limit
        self.platform = "jetbrains"
        self.platform_label = "JetBrains"

    def collect(self) -> list[SessionInfo]:
        root = _jetbrains_root()
        if not root.exists():
            return []
        entries: list[SessionInfo] = []
        for ide_dir in sorted(root.iterdir()):
            if not ide_dir.is_dir():
                continue
            ide_key, label = _match_ide(ide_dir.name)
            if not ide_key:
                continue
            xml_path = ide_dir / "options" / "recentProjects.xml"
            if not xml_path.exists():
                continue
            running = self.process_running_map.get(ide_key, False)
            entries.extend(self._parse(xml_path, ide_key, label, running))

        # 同路径可能在多个 IDE 打开过，保留最近激活的那个
        deduped = _dedup_by_path(entries)
        deduped.sort(key=lambda i: i.last_active_at or 0, reverse=True)
        return deduped[: self.recent_limit]

    def _parse(self, xml_path: Path, ide_key: str, label: str, running: bool) -> list[SessionInfo]:
        try:
            tree = ET.parse(xml_path)
        except ET.ParseError:
            return []
        infos: list[SessionInfo] = []
        for entry in tree.iter("entry"):
            path = entry.get("key", "")
            if not path:
                continue
            meta = entry.find(".//RecentProjectMetaInfo")
            if meta is None:
                continue
            opened = meta.get("opened") == "true"
            activation = _opt_int(meta, "activationTimestamp")
            frame_title = _opt_value(meta, "frameTitle") or ""
            last_active_s = (activation / 1000) if activation else None
            # 状态：IDE 在跑且该项目在该 IDE 打开着 => active，否则 idle
            status = "active" if (running and opened) else "idle"
            infos.append(
                SessionInfo(
                    platform=ide_key,
                    platform_label=label,
                    session_id=f"{ide_key}:{path}",
                    title=_title_from(path, frame_title),
                    project_path=path,
                    status=status,
                    level=LEVEL_ACTIVITY,
                    last_active_at=last_active_s,
                    last_message_preview="",
                    message_count=0,
                    tool_call_count=0,
                    process_running=running,
                    extra={"opened": opened, "frame_title": frame_title},
                )
            )
        return infos


def _match_ide(dirname: str) -> tuple[str, str] | tuple[None, None]:
    for prefix, (key, label) in _IDE_DIRS.items():
        if dirname.startswith(prefix):
            return key, label
    return None, None


def _opt_int(meta: ET.Element, name: str) -> int | None:
    node = meta.find(f"./option[@name='{name}']")
    if node is None:
        return None
    v = node.get("value")
    return int(v) if v and v.isdigit() else None


def _opt_value(meta: ET.Element, name: str) -> str | None:
    node = meta.find(f"./option[@name='{name}']")
    return node.get("value") if node is not None else None


def _title_from(path: str, frame_title: str) -> str:
    """项目展示名：优先 frame_title 里 "项目名 – 文件" 的项目名部分。"""
    if frame_title:
        # "project3136859-389070 – Task.md" -> "project3136859-389070"
        name = frame_title.split(" – ")[0].split(" - ")[0]
        if name:
            return name
    # 回退到路径末段
    return Path(path).name or path


def _dedup_by_path(infos: list[SessionInfo]) -> list[SessionInfo]:
    seen: dict[str, SessionInfo] = {}
    for info in infos:
        existing = seen.get(info.project_path)
        if existing is None or (info.last_active_at or 0) > (existing.last_active_at or 0):
            seen[info.project_path] = info
    return list(seen.values())


if __name__ == "__main__":
    from .process_probe import probe_running_processes, is_platform_running

    running = probe_running_processes()
    pr_map = {k: is_platform_running(k, running) for k in _IDE_DIRS.values()}
    for info in JetBrainsCollector(pr_map).collect():
        print(f"- [{info.status}] {info.platform_label}: {info.title}  path={info.project_path}  opened={info.extra.get('opened')}")
