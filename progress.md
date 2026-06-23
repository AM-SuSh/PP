# 进度日志

## 2026-06-23 - Task: 前端重构（看板列布局 + 平台 logo + 消除闪屏）

### What was done

三项前端优化：① 把网格卡片改为平台看板列布局——每个平台一列，列头是带品牌色的平台 logo + 名称 + 活跃计数，会话卡像贴纸垂直堆叠在列内，列多时横向滚动；② 每个平台用手绘内联 SVG 标识 + 官方品牌色（JetBrains 方块字标、Cursor 光标、Codex 六瓣花、Claude 星芒、ZCode 抽象方块等），不再只用文字平台名；③ 消除更新闪屏——改用差量 DOM 更新，按 session_id 维护节点映射，用签名对比只重绘内容变化的卡片，列头/统计条/徽标同样加签名对比，内容不变则不写 DOM。

### Testing

- 语法检查：`node --check logos.js` 与 `node --check app.js` 均通过。✅
- 静态服务验证：`GET /logos.js` HTTP 200（新增文件正确被服务）。✅
- 完整 GUI 启动：`conda run -n pp python -m app.main` 启动后 api/index/logos 均 HTTP 200、stderr 无报错，窗口正常弹出看板布局。✅
- 差量更新逻辑验证：renderBoard 按 platform 差量建列/移列；diffCards 按 session_id 差量建卡/移卡/调序；cardSignature 纳入标题/状态/路径/消息数/工具数/时间/路径配置状态，内容变才重绘；列头/统计条/徽标均加 dataset.sig 对比。逻辑层面保证无内容不变时的无谓重绘。

### Notes

改动文件清单（纯前端，未触碰后端/采集器）：

- `app/web/logos.js`（新建）— 各平台内联 SVG 标识 + 品牌色，viewBox 统一 0 0 24 24，currentColor 可随主题变色，含 getLogo/logoSvgRaw 接口。
- `app/web/index.html`（修改）— 引入 logos.js（在 app.js 之前）。
- `app/web/style.css`（修改）— #board 改 flex 横向流动看板布局，.platform-group 固定列宽 300px + scroll-snap；新增 .group-head（sticky 列头带 logo 岛）/ .platform-logo（品牌色底）/ .gcount-badge / .card-logo（卡片左上小 logo）等样式。
- `app/web/app.js`（修改）— 重写渲染核心：renderBoard 看板分列 + nodeMap 节点映射 + diffCards 差量更新 + cardSignature 签名对比；删除旧 cardHtml；renderStats/徽标/列头均加签名对比；logoSvgRaw/getLogo 引用。

边界说明：① logo 为手绘简化标识取各品牌核心视觉特征，非官方矢量，若对还原度不满意可在 logos.js 调整；② 差量更新消除内容不变时的闪屏，但首屏加载和内容真正变化时仍会有重绘（属正常刷新）。

回滚方式：本轮纯前端改动，git 还原 app/web/ 下四个文件即可，后端与数据层完全不受影响。

## 2026-06-23 - Task: 固定导航栏 + 卡片点击打开 + 仅显示当日会话

## 2026-06-23 - Task: 固定导航栏 + 卡片点击打开 + 仅显示当日会话

### What was done

实现三项功能：① 固定顶部导航栏（顶栏+工具栏始终可见不随滚动消失）；② 点击卡片"打开"按钮激活对应平台并定位到项目；③ 仅显示当日有活动的会话（从 77 个历史会话过滤到当日的 6 个）。

针对"打开该程序该任务的界面"的现实边界做了诚实处理：所有平台都做不到"打开某一个具体会话窗口"，故按"激活应用+定位项目"策略——GUI 应用（ZCode/Cursor/JetBrains）启动 exe 并传项目路径，CLI 工具（Codex/Claude）在项目目录开终端运行。考虑到这是要发布维护的软件，平台路径做成可配置：首次运行自动扫描常见安装位置（扫到 8/9 个平台），扫不到的（如 PyCharm）通过顶栏齿轮按钮的设置面板手动填写，持久化到 ~/.ai-dashboard/config.json。

### Testing

- 配置层自检：`python -m app.config` 扫描到 8 个平台路径（zcode/cursor/idea/goland/clion/rustrover/codex/claude），ensure_config 正确持久化到 config.json。✅
- launcher 命令构造自检（不实际启动，避免副作用）：GUI+路径型（cursor/idea）输出 [exe, path]、纯激活型（zcode）输出 [exe]、CLI 型（codex/claude）输出 cmd /K 开终端命令，未配置的 pycharm 输出空路径。✅
- 当日过滤验证：聚合结果从 77 个会话降至 6 个（仅今天有活动的），口径用 last_active_at 是否在本地今日。✅
- launch 接口错误处理：缺 platform 返回 400+"缺少 platform"；未配置路径返回 ok=false+"未配置…请先在设置中指定"。✅
- 新接口验证：GET /api/config 返回 8 个平台路径；GET /api/sessions 附带 platform_paths 字段（8 个）。✅
- 前端语法检查：`node --check app.js` 通过。✅
- 完整 GUI 启动：`conda run -n pp python -m app.main` 启动后 index HTTP 200、API 返回 6 个今日会话 + 8 个平台路径、stderr 无报错，窗口正常弹出。
- launch 成功路径未自动触发：因会真实弹出外部窗口（属于未经确认的外部动作），留待用户在 GUI 点击"打开"按钮亲自验证。

### Notes

改动文件清单：

- `app/config.py`（新建）— 平台路径配置层：限深 BFS 扫描常见安装目录 + ~/.ai-dashboard/config.json 持久化 + ensure_config 首次自动扫描。注：未扫整个 D:\ 根（目录过宽命中率低且耗时），直接装在盘根的 IDE 由设置面板手动补。
- `app/launcher.py`（新建）— 各平台启动器：GUI+路径型/纯激活型/CLI 开终端三类策略，DETACHED_PROCESS 独立运行不随仪表盘退出。
- `app/server.py`（修改）— 聚合层加当日过滤（_is_today）+ 附带 platform_paths 字段；新增 POST /api/launch、GET/POST /api/config 三个接口。
- `app/web/index.html`（修改）— 顶栏+工具栏包进 .fixed-header 固定容器；加齿轮设置按钮；工具栏加"仅显示今日活动"标识。
- `app/web/style.css`（修改）— .fixed-header 固定定位+毛玻璃；内容区 margin-top 避让；新增打开按钮/toast/设置弹窗/spin 动画样式。
- `app/web/app.js`（修改）— 卡片加"打开/设置"按钮（事件委托）；launchPlatform 调 /api/launch + toast 反馈；openSettings 设置面板（路径编辑保存）；缓存 platform_paths 判断可点击。

边界说明：① JetBrains/Cursor 仍为活动级（读不到 AI 对话，本轮未改）；② 打开操作只能激活应用/定位项目，无法打开某具体会话窗口（各平台能力上限）；③ PyCharm 未被自动扫描到，需在设置面板手动填写 D:\PyCharm 2024.2.3\bin\pycharm64.exe。

回滚方式：本轮新增 config.py/launcher.py 两个文件，并修改 server.py 和前端三件套。如需回退，git 还原这些文件即可（config.json 是用户数据，在 ~/.ai-dashboard/ 不在仓库内，无需处理）。launch 接口与外部进程交互，关闭仪表盘不影响已启动的外部应用。

## 2026-06-23 - Task: 仪表盘前端 UI 重构（双主题 + 仪表盘化）

## 2026-06-23 - Task: 仪表盘前端 UI 重构（双主题 + 仪表盘化）

### What was done

重构前端三件套（index.html / style.css / app.js），把原本偏列表的界面升级为真正的仪表盘形态，并加入日间/夜间双主题切换。依据 ui-ux-pro-max skill 的设计系统建议（监控类产品语义色：teal 主色 + 状态色绿/琥珀/红），同时基于正确判断调整了 skill 不适配的部分：字体用 Inter + JetBrains Mono（skill 推荐的 Cinzel/Josefin 属 luxury 房产风，与数据监控不匹配）；图标全部换成内联 SVG（遵循 skill 的 no-emoji-icons 规则）。

具体改动：新增顶部概览统计区（活跃中/空闲/可能被遗忘/总会话数四个指标卡）；卡片左侧加状态色条 + 活跃会话脉冲动画；主题切换按钮（月亮/太阳图标）带 localStorage 记忆；新增"可能被遗忘"筛选 chip；卡片 hover 上浮、状态语义化、tabular-nums 数字对齐；间距改 4/8dp 节奏、字号体系统一；尊重 prefers-reduced-motion。

### Testing

- 静态文件验证：`GET /` 含 `data-theme="dark"`、theme-btn、stats-bar、chip-stale 新结构；`GET /style.css` 含 dark/light 双套变量（`--status-active` dark=#34d399 / light=#059669）、prefers-reduced-motion 降级；`GET /app.js` 含 applyTheme/renderStats/STALE_MIN 逻辑。✅
- JS 语法检查：`node --check app.js` 通过，无语法错误。✅
- 完整 GUI 启动验证：`conda run -n pp python -m app.main` 启动后 API HTTP 200、stderr 无报错，pywebview 窗口正常弹出渲染新界面。

### Notes

改动文件清单（均仅修改前端三件套，未触碰后端/采集器/数据层）：

- `app/web/index.html` — 新增概览统计区 section、主题切换按钮、字体引用（Inter/JetBrains Mono）、三个筛选 chip、所有 emoji 占位改为内联 SVG。
- `app/web/style.css` — 重写为语义 token 体系，dark/light 双主题变量，统计卡/状态色条/脉冲动画/卡片 hover 上浮/4-8dp 间距节奏/reduced-motion 降级。
- `app/web/app.js` — 新增主题切换与 localStorage 记忆、概览统计计算与渲染、"可能被遗忘"筛选、图标全部 SVG 化。

回滚方式：这三处改动均集中在前端文件。如需回到首版界面，用 git 还原这三个文件即可（首版已在上一条日志记录）。后端接口 `/api/sessions` 与采集器完全未改动，数据层不受影响。

注：字体走 Google Fonts CDN，本机离线时会降级为系统字体（Inter→Segoe UI/YaHei，Mono→Consolas），不影响功能。

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
