# 进度日志

## 2026-06-23 - Task: 构建多平台 AI 任务并行仪表盘（首版）

### What was done

构建了一个本地桌面仪表盘，并行展示本机 ZCode / Codex / Claude Code 三个 CLI 平台的会话进展（会话级，含对话与工具统计），以及 JetBrains 全家桶 / Cursor 的项目活动 + 进程状态（活动级）。采用 pywebview 渲染 HTML 前端 + Flask 后端 + watchdog 文件监听 + 兜底轮询的准实时刷新方案。通过 conda 创建专用环境 `pp`（Python 3.11）运行，此后本项目统一使用该环境。

功能要点：按平台分组展示卡片网格；状态灯（活跃/空闲）由进程存活+最近活动推导；超过 60 分钟无活动标红提醒"被遗忘的任务"；支持标题/路径筛选、仅看活跃、分组开关。

### Testing

- 环境与依赖：`conda run -n pp python -c "import webview,watchdog,flask,sqlite3,json"` 导入成功；flask 3.1.3。
- ZCode 采集器自检：当前会话(本对话)状态 active、85 消息/89 工具调用，子代理会话被正确过滤。✅
- Codex 采集器自检：20 个会话，cwd/消息数/工具调用数/最后消息摘要均正确（修复了 cwd 仅在 session_meta/turn_context 而非 response_item 的问题）。✅
- Claude 采集器自检：20 个会话，cwd 从行内字段取、标题取首条用户消息、tool_use 计数正确（含 1266 消息的大会话）。✅
- JetBrains 采集器自检：12 个项目跨 PyCharm/GoLand/IDEA/RustRover，IDE 归属、opened、激活时间正确。✅
- Cursor 采集器自检：8 个 workspace，file:/// URL 解码为本地路径正确。✅
- 聚合接口 HTTP 验证：`GET /api/sessions?force=1` 返回 77 个会话，8 个平台分组，HTTP 200。✅
- 静态文件验证：`/` `/style.css` `/app.js` 均正确返回。✅
- 缓存与 invalidate 链路验证：force 采集→缓存命中(generated_at 不变)→invalidate→重采(generated_at 改变)→多次 invalidate 仍数据有效。✅
- Watcher 启停验证：observer 与兜底轮询线程存活，干净停止。✅
- 完整 GUI 启动验证：`conda run -n pp python -m app.main` 启动后 API 响应 HTTP 200、stderr 无报错，pywebview 窗口正常弹出。

### Notes

改动文件清单（均为新建，未触碰既有 AGENTS.md）：

- `requirements.txt` — 依赖清单（pywebview/watchdog/flask）。
- `app/__init__.py`、`app/collectors/__init__.py` — 包标识空文件。
- `app/collectors/base.py` — 统一数据模型 SessionInfo 与采集器基类（含容错 _safe_collect）。
- `app/collectors/zcode.py` — 查 ~/.zcode/cli/db/db.sqlite 聚合 ZCode 会话。
- `app/collectors/codex.py` — 读 ~/.codex 索引与会话 jsonl 聚合 Codex 会话。
- `app/collectors/claude.py` — 读 ~/.claude/projects 会话 jsonl 聚合 Claude 会话。
- `app/collectors/jetbrains.py` — 解析 JetBrains recentProjects.xml 得项目活动。
- `app/collectors/cursor.py` — 读 Cursor workspaceStorage 得项目活动。
- `app/collectors/process_probe.py` — PowerShell Get-Process 进程探测。
- `app/server.py` — Flask 聚合后端 + /api/sessions + TTL 缓存 + invalidate + 静态服务。
- `app/watcher.py` — watchdog 文件监听（2s 去抖）+ 30s 兜底轮询，触发缓存失效。
- `app/main.py` — 入口：起 watcher + 后端线程 + pywebview 窗口。
- `app/web/index.html` — 面板骨架（顶栏/工具栏/分组卡片网格）。
- `app/web/style.css` — 深色卡片风，会话级与活动级视觉区分。
- `app/web/app.js` — 拉取渲染 + 筛选/分组 + 5s 轮询 + "多久以前"标红。
- `docs/design.md` — 架构、数据源、状态推导、实时机制、边界说明。
- `README.md` — 启动方式、功能、平台覆盖、排查。

环境：新建 conda 环境 `pp`（Python 3.11.15），位置 D:\miniconda3\envs\pp。

回滚方式：
- 删除环境：`conda env remove -n pp`
- 删除项目代码：移除 `app/`、`docs/`、`progress.md`、`README.md`、`requirements.txt`，仓库回到仅含 AGENTS.md 的初始状态。
- 如需停止正在运行的仪表盘：结束占用 7321 端口的 python 进程，或关闭 pywebview 窗口。

已知边界（非缺陷，设计取舍）：
- JetBrains/Cursor 为活动级，读不到 AI 对话内容（私有库无稳定接口）。
- 实时性为准实时（秒级到 30 秒级），不承诺纯实时（Windows 文件监听固有延迟）。
- Codex/Claude 进程作 node 子进程，单凭进程名不可靠区分，状态改由会话活动时间推导。
