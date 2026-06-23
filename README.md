# PP: Parallel Pasture

多平台 AI 任务并行仪表盘

并行操作多个 AI 编码助手（ZCode / Codex / Claude Code / JetBrains 全家桶 / Cursor）时，
一眼看清每个会话在做什么、停了多久、是否被遗忘。

## 快速启动

> 需要本机已装 conda（首次创建专用环境）。

```bat
:: 首次：创建专用环境 pp（Python 3.11）并装依赖
conda create -n pp python=3.11 -y
conda run -n pp pip install pywebview watchdog flask

:: 以后每次启动：在项目根目录执行
conda run -n pp python -m app.main
```

启动后会弹出一个桌面窗口，展示当前本机所有 AI 会话的并行进展。

> 国内若 conda/pip 走代理失败，加镜像源：
> `-c https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main --override-channels`
> 与 `-i https://pypi.tuna.tsinghua.edu.cn/simple`，并先 `unset HTTP_PROXY HTTPS_PROXY ALL_PROXY`。

## 它能展示什么

每个工作项卡片包含：

- **状态灯**：绿(活跃) / 黄(空闲) / 灰(未知)；超过 60 分钟无活动，时间标红提醒
- **标题**：会话首条用户消息 / 项目名
- **项目路径**：所在仓库目录
- **最后消息摘要**：最近一次对话的角色与内容片段（仅 CLI 三家）
- **消息数 / 工具调用数**：工作量量化（仅 CLI 三家）

顶部工具栏支持：按标题/路径筛选、仅看活跃、按平台分组。

## 平台覆盖与边界

| 平台 | 级别 | 说明 |
|---|---|---|
| ZCode | 会话级 | 读 `db.sqlite`，含对话与工具统计 |
| Codex | 会话级 | 读会话索引与明细 jsonl |
| Claude Code | 会话级 | 读 projects 下的会话 jsonl |
| JetBrains 全家桶 | 活动级 | 读 recentProjects.xml，**仅项目+进程，读不到 AI 对话** |
| Cursor | 活动级 | 读 workspaceStorage，**仅项目+进程，读不到 AI 对话** |

JetBrains / Cursor 的 AI 对话存私有库，无稳定读取接口，明确降级为活动级（卡片用虚线边框淡化区分），不做不可靠的硬解析。

## 实时性

文件变化监听（watchdog）+ 30 秒兜底轮询双保险，准实时刷新（秒级到 30 秒级）。
不承诺纯实时——Windows 对持续写入的 jsonl/SQLite-WAL 的监听存在固有延迟。

## 目录结构

```
app/
├── main.py              入口：pywebview 窗口 + watcher + 后端
├── server.py            Flask 聚合后端 + /api/sessions
├── watcher.py           watchdog 监听 + 兜底轮询
├── collectors/          各平台采集器（统一返回 SessionInfo）
│   ├── base.py          数据模型与基类
│   ├── zcode.py / codex.py / claude.py     会话级
│   ├── jetbrains.py / cursor.py            活动级
│   └── process_probe.py                    进程探测
└── web/                 前端（index.html / style.css / app.js）
docs/design.md           架构与数据源说明
progress.md              进度日志
```

## 排查

- **窗口空白**：确认后端已起，浏览器访问 `http://127.0.0.1:7321/` 看是否有数据。
- **端口 7321 被占用**：结束占用进程，或修改 `app/main.py` 与 `app/server.py` 的 `PORT`。
- **某平台没数据**：该平台目录可能不存在（未安装/未使用），属正常。
- **代理导致 conda/pip 失败**：见上方"快速启动"中的镜像源说明。

详见 `docs/design.md`。
