# 仪表盘架构设计

## 目标

并行操作多个 AI 编码助手时，一眼看清每个会话"在做什么、停了多久、是否被遗忘"。

## 整体架构

```
┌─────────────────────────────────────────────┐
│  pywebview 桌面窗口 (WebView2 渲染 HTML)      │
│  ┌─────────────────────────────────────┐    │
│  │  index.html / style.css / app.js     │    │
│  │  每 5s 轮询 GET /api/sessions 渲染    │    │
│  └─────────────────────────────────────┘    │
└──────────────────┬──────────────────────────┘
                   │ HTTP (127.0.0.1:7321)
┌──────────────────▼──────────────────────────┐
│  Flask 后端 (app/server.py)                  │
│  - /api/sessions 聚合所有采集器               │
│  - 带 TTL 缓存 + invalidate 触发重采          │
└──────────┬──────────────────────┬───────────┘
           │                      │
   ┌───────▼────────┐    ┌────────▼─────────┐
   │  Watcher 线程   │    │  采集器层         │
   │  (watchdog +    │    │  ZCode/Codex/     │
   │   兜底轮询)      │    │  Claude(session)  │
   │  文件变化→失效缓存│    │  JetBrains/Cursor │
   └────────────────┘    │  (activity)       │
                         └──────────────────┘
```

## 数据源与采集器

每个采集器返回统一的 `SessionInfo` 列表（见 `app/collectors/base.py`）。

### 会话级（LEVEL_SESSION）—— 能读到 AI 对话与进展

| 平台 | 数据源 | 读取字段 | 采集器 |
|---|---|---|---|
| ZCode | `~/.zcode/cli/db/db.sqlite` | session(title/directory/time_*)、message/tool_usage 计数 | `zcode.py` |
| Codex | `~/.codex/session_index.jsonl` + `sessions/**/*.jsonl` | thread_name/updated_at、cwd、message/function_call 计数 | `codex.py` |
| Claude Code | `~/.claude/projects/*/*.jsonl` | cwd/sessionId/timestamp、user/assistant 消息、tool_use 计数 | `claude.py` |

### 活动级（LEVEL_ACTIVITY）—— 只有项目活动 + 进程，读不到 AI 对话

| 平台 | 数据源 | 读取字段 | 采集器 |
|---|---|---|---|
| JetBrains 全家桶 | `%APPDATA%/JetBrains/*/options/recentProjects.xml` | 项目路径、activationTimestamp、opened、IDE 归属 | `jetbrains.py` |
| Cursor | `%APPDATA%/Cursor/User/workspaceStorage/*/workspace.json` | folder(项目路径)、目录 mtime | `cursor.py` |

> **诚实边界**：JetBrains 的 AI 对话存私有库、Cursor 的存私有 LevelDB，无稳定接口，随版本失效。本期明确降级为活动级，前端用虚线边框 + 淡化样式区分，避免误导。

## 状态推导

各平台都没有"会话正在思考中"的可靠标志，状态由「进程是否在跑 + 最近活动时间」推导：

- `active`：平台进程存活 **且** 最近 10 分钟内有活动
- `idle`：进程未跑，或超过 10 分钟无活动
- 超过 60 分钟无活动的卡片，前端把"多久以前"标红，提示可能被遗忘

进程探测见 `process_probe.py`，用 PowerShell `Get-Process`（本机比 tasklist+findstr 稳）。

## 实时刷新机制

Watcher（`watcher.py`）采用双保险：

1. **watchdog 监听**：监听各数据源目录，文件变化 → 2 秒去抖 → invalidate 后端缓存
2. **兜底轮询**：每 30 秒无条件 invalidate 一次，弥补 Windows 上 watchdog 对 WAL/持续追加 jsonl 的漏触发

> **边界**：Windows 文件监听非纯实时。本方案做到准实时（秒级到 30 秒级），不承诺纯实时。前端另每 5 秒轮询接口取最新缓存。

## 关键决策与取舍

- **pywebview + HTML**：用 WebView2 渲染正常网页技术写的前端，观感优于 Tkinter/Qt Widgets，启动快。
- **端口写死 7321**：不引入配置文件，最小化。如占用会启动失败。
- **采集器各自容错**：单个平台采集抛异常只返回空列表，不拖垮整个仪表盘（`BaseCollector._safe_collect`）。
- **SQLite 只读连接**：`mode=ro&immutable=1`，避免对正在写入的 ZCode 数据库争锁。
- **去抖**：大模型流式输出会高频刷写 jsonl，去抖窗口合并为一次重采。

## 性能考量

- Codex/Claude 无全局索引，逐个打开会话 jsonl 聚合，成本较高。默认只处理最近 20 个会话。
- 进程探测（PowerShell）有开销，每次聚合只调一次，结果分发到各采集器。

## 回滚

全部为新建文件 + 新建 conda 环境 `pp`，不触碰任何既有文件（`AGENTS.md` 保持不变）。

- 删环境：`conda env remove -n pp`
- 删代码：移除 `app/` `docs/` `progress.md` `README.md` `requirements.txt`，仓库回到初始状态。
