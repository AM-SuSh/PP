// 前端逻辑：拉取聚合数据 -> 渲染卡片 -> 轮询刷新
// 状态：active 绿(脉冲) / idle 黄 / unknown 灰
// 活动级卡片(JetBrains/Cursor)淡化+虚线边框，与 session 级视觉区分

const STALE_MIN = 60; // 超过 60 分钟未活动标红，提示"可能被遗忘"
const POLL_MS = 5000; // 轮询间隔（准实时，配合后端 watchdog invalidate）

let lastData = null;

async function fetchSessions(force) {
  const url = "/api/sessions" + (force ? "?force=1" : "");
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function ago(iso) {
  if (!iso) return { text: "—", stale: false };
  const t = new Date(iso).getTime();
  if (isNaN(t)) return { text: "—", stale: false };
  const min = (Date.now() - t) / 60000;
  const stale = min > STALE_MIN;
  let text;
  if (min < 1) text = "刚刚";
  else if (min < 60) text = Math.floor(min) + " 分钟前";
  else if (min < 1440) text = Math.floor(min / 60) + " 小时前";
  else text = Math.floor(min / 1440) + " 天前";
  return { text, stale };
}

function render(data) {
  lastData = data;
  const board = document.getElementById("board");
  const empty = document.getElementById("empty");

  // 更新时间 + 运行中平台徽标
  document.getElementById("updated").textContent =
    "更新于 " + new Date(data.generated_at * 1000).toLocaleTimeString();
  const rb = document.getElementById("running-badges");
  rb.innerHTML = (data.platforms_running || [])
    .map((p) => `<span class="run-badge">${esc(p)} 在运行</span>`).join("");

  let sessions = data.sessions || [];

  // 筛选条件
  const q = document.getElementById("filter").value.trim().toLowerCase();
  if (q) {
    sessions = sessions.filter(
      (s) =>
        (s.title || "").toLowerCase().includes(q) ||
        (s.project_path || "").toLowerCase().includes(q)
    );
  }
  if (document.getElementById("only-active").checked) {
    sessions = sessions.filter((s) => s.status === "active");
  }

  if (sessions.length === 0) {
    board.innerHTML = "";
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  // 排序：active 优先，其次按活动时间倒序
  sessions.sort((a, b) => {
    if (a.status === "active" && b.status !== "active") return -1;
    if (b.status === "active" && a.status !== "active") return 1;
    return (b.last_active_at || "").localeCompare(a.last_active_at || "");
  });

  const groupByPlatform = document.getElementById("group-platform").checked;
  if (groupByPlatform) {
    const groups = {};
    for (const s of sessions) {
      const key = s.platform;
      (groups[key] = groups[key] || { label: s.platform_label, items: [] }).items.push(s);
    }
    // 按组内是否有 active 排序，active 组靠前
    const keys = Object.keys(groups).sort((a, b) => {
      const ax = groups[a].items.some((s) => s.status === "active") ? 0 : 1;
      const bx = groups[b].items.some((s) => s.status === "active") ? 0 : 1;
      return ax - bx;
    });
    board.innerHTML = keys
      .map(
        (k) => `
        <section class="platform-group">
          <div class="group-head">
            <span class="ptag">${esc(groups[k].label)}</span>
            <span class="gcount">${groups[k].items.length} 个</span>
          </div>
          <div class="cards">${groups[k].items.map(cardHtml).join("")}</div>
        </section>`
      )
      .join("");
  } else {
    board.innerHTML = `<div class="cards">${sessions.map(cardHtml).join("")}</div>`;
  }
}

function cardHtml(s) {
  const ag = ago(s.last_active_at);
  const isActivity = s.level === "activity";
  const stats = isActivity
    ? `<span class="stat">活动级</span>`
    : `<span class="stat">💬 <b>${s.message_count}</b></span>
       <span class="stat">🛠 <b>${s.tool_call_count}</b></span>`;
  return `
    <div class="card ${isActivity ? "activity" : ""}">
      <div class="card-top">
        <span class="status-dot ${s.status}"></span>
        <div class="card-title">${esc(s.title)}</div>
        ${isActivity ? '<span class="level-tag">活动</span>' : ""}
      </div>
      <div class="card-path" title="${esc(s.project_path)}">${esc(s.project_path || "—")}</div>
      <div class="card-preview">${esc(s.last_message_preview || "")}</div>
      <div class="card-foot">
        ${stats}
        <span class="ago ${ag.stale ? "stale" : ""}">${ag.text}</span>
      </div>
    </div>`;
}

async function refresh(force) {
  try {
    const data = await fetchSessions(force);
    render(data);
  } catch (e) {
    console.error("refresh failed", e);
  }
}

// 事件绑定
document.getElementById("refresh-btn").addEventListener("click", () => refresh(true));
["filter", "only-active", "group-platform"].forEach((id) => {
  document.getElementById(id).addEventListener("input", () => {
    if (lastData) render(lastData);
  });
});

// 初始渲染 + 定时轮询
refresh(true);
setInterval(() => refresh(false), POLL_MS);
