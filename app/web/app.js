// 前端逻辑：拉取聚合数据 -> 概览统计 + 分组卡片 -> 轮询刷新
// 状态语义：active 绿(脉冲) / idle 琥珀 / unknown 灰；>60min 无活动标红 = "可能被遗忘"
// 主题：data-theme=dark|light，记忆到 localStorage
// 图标：全部内联 SVG，不用 emoji（遵循 a11y/一致性）

const STALE_MIN = 60;   // 超过 60 分钟无活动 → "可能被遗忘"
const POLL_MS = 5000;

// 平台中文名（设置面板用）
const PLATFORM_LABELS = {
  zcode: "ZCode", cursor: "Cursor", pycharm: "PyCharm", idea: "IntelliJ IDEA",
  goland: "GoLand", clion: "CLion", rustrover: "RustRover",
  codex: "Codex CLI", claude: "Claude CLI",
};

let lastData = null;
let platformPaths = {};  // 各平台 exe 路径，用于判断是否可点击打开
const state = { onlyActive: false, onlyStale: false, group: true };

// ---------- 主题 ----------
const ICONS = {
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
};

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  document.getElementById("theme-icon").innerHTML = theme === "dark" ? ICONS.moon : ICONS.sun;
  try { localStorage.setItem("pp-theme", theme); } catch (e) {}
}

(function initTheme() {
  let t;
  try { t = localStorage.getItem("pp-theme"); } catch (e) {}
  applyTheme(t === "light" ? "light" : "dark");
})();

document.getElementById("theme-btn").addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme");
  applyTheme(cur === "dark" ? "light" : "dark");
});

// ---------- 数据 ----------
async function fetchSessions(force) {
  const url = "/api/sessions" + (force ? "?force=1" : "");
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

function esc(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function ago(iso) {
  if (!iso) return { text: "—", stale: false, min: Infinity };
  const t = new Date(iso).getTime();
  if (isNaN(t)) return { text: "—", stale: false, min: Infinity };
  const min = (Date.now() - t) / 60000;
  let text;
  if (min < 1) text = "刚刚";
  else if (min < 60) text = Math.floor(min) + " 分钟前";
  else if (min < 1440) text = Math.floor(min / 60) + " 小时前";
  else text = Math.floor(min / 1440) + " 天前";
  return { text, stale: min > STALE_MIN, min };
}

// ---------- 渲染 ----------
function render(data) {
  lastData = data;
  // 缓存平台路径，用于判断卡片能否点击打开
  platformPaths = data.platform_paths || {};
  document.getElementById("updated").textContent =
    "更新于 " + new Date(data.generated_at * 1000).toLocaleTimeString();

  // 运行中平台徽标（签名对比，平台集合不变则不重绘）
  const rb = document.getElementById("running-badges");
  const rbSig = (data.platforms_running || []).join(",");
  if (rb.dataset.sig !== rbSig) {
    rb.dataset.sig = rbSig;
    rb.innerHTML = (data.platforms_running || [])
      .map((p) => `<span class="run-badge"><span style="width:6px;height:6px;border-radius:50%;background:currentColor;display:inline-block"></span>${esc(p)}</span>`).join("");
  }

  let sessions = data.sessions || [];
  renderStats(sessions);

  // 筛选
  const q = document.getElementById("filter").value.trim().toLowerCase();
  if (q) {
    sessions = sessions.filter((s) =>
      (s.title || "").toLowerCase().includes(q) || (s.project_path || "").toLowerCase().includes(q));
  }
  if (state.onlyActive) sessions = sessions.filter((s) => s.status === "active");
  if (state.onlyStale) sessions = sessions.filter((s) => ago(s.last_active_at).stale);

  const board = document.getElementById("board");
  const empty = document.getElementById("empty");
  if (sessions.length === 0) {
    // 差量：清空时移除所有列，而非 innerHTML（保持过渡）
    diffClear(board);
    empty.classList.remove("hidden");
    return;
  }
  empty.classList.add("hidden");

  // 排序：active 优先 → 非 stale 优先 → 活动时间倒序
  sessions.sort((a, b) => {
    const sa = a.status === "active" ? 0 : 1, sb = b.status === "active" ? 0 : 1;
    if (sa !== sb) return sa - sb;
    return (b.last_active_at || "").localeCompare(a.last_active_at || "");
  });

  // 差量绘制：按平台分列，列内按 session_id 差量更新
  renderBoard(board, sessions);
}

// ---------- 差量绘制核心 ----------
// 维护 DOM 节点映射，只更新变化的卡片，避免整屏重绘闪屏。
// 列结构按 platform key 差量；列内卡片按 session_id 差量。
const nodeMap = {}; // key="platform|sessionId" -> card DOM node

function renderBoard(board, sessions) {
  // 分组（保留顺序：有活跃的平台排前）
  const groups = {};
  for (const s of sessions) (groups[s.platform] = groups[s.platform] || { label: s.platform_label, items: [] }).items.push(s);
  const platKeys = Object.keys(groups).sort((a, b) => {
    const ax = groups[a].items.some((s) => s.status === "active") ? 0 : 1;
    const bx = groups[b].items.some((s) => s.status === "active") ? 0 : 1;
    return ax - bx;
  });

  // 1) 移除消失的平台列
  for (const col of [...board.querySelectorAll(".platform-group")]) {
    if (!platKeys.includes(col.dataset.platform)) col.remove();
  }

  // 2) 按顺序更新/创建平台列
  let prevCol = null;
  const seenKeys = new Set();
  for (const pk of platKeys) {
    const g = groups[pk];
    let col = board.querySelector(`.platform-group[data-platform="${cssEscape(pk)}"]`);
    if (!col) {
      col = document.createElement("section");
      col.className = "platform-group";
      col.dataset.platform = pk;
      col.innerHTML = `<div class="group-head"></div><div class="cards"></div>`;
    }
    // 调整列顺序（按 platKeys）
    if (prevCol ? prevCol.nextSibling !== col : board.firstChild !== col) {
      board.insertBefore(col, prevCol ? prevCol.nextSibling : board.firstChild);
    }
    prevCol = col;

    // 更新列头（签名对比：活跃状态/数量变化才重绘，避免列头闪烁）
    const logo = getLogo(pk);
    const live = g.items.some((s) => s.status === "active");
    const activeCount = g.items.filter((s) => s.status === "active").length;
    const headSig = `${logo.brand}|${g.label}|${live ? 1 : 0}|${activeCount}|${g.items.length}`;
    const headEl = col.querySelector(".group-head");
    if (headEl.dataset.sig !== headSig) {
      headEl.dataset.sig = headSig;
      headEl.innerHTML = `
        <span class="platform-logo" style="--brand-color:${logo.brand}">${logo.svg}</span>
        <div><div class="gname">${esc(g.label)}</div>
        <div class="gstatus">${live ? `<span class="live-dot"></span>${activeCount} 活跃 / ${g.items.length}` : `今日 ${g.items.length} 个`}</div></div>
        <span class="gcount-badge ${live ? "active-badge" : ""}">${g.items.length}</span>`;
    }

    // 列内卡片差量
    const cardsBox = col.querySelector(".cards");
    diffCards(cardsBox, pk, g.items, seenKeys);
  }

  // 3) 移除本次未出现的卡片节点（已不属于任何列）
  for (const k of Object.keys(nodeMap)) {
    if (!seenKeys.has(k) && nodeMap[k].isConnected) nodeMap[k].remove();
    if (!seenKeys.has(k)) delete nodeMap[k];
  }
}

function diffCards(cardsBox, platform, items, seenKeys) {
  let prev = null;
  for (const s of items) {
    const key = `${platform}|${s.session_id}`;
    seenKeys.add(key);
    let node = nodeMap[key];
    if (!node) {
      node = document.createElement("div");
      node.dataset.key = key;
      nodeMap[key] = node;
    }
    // 内容变化才更新（用签名对比，避免无谓 DOM 写入）
    const sig = cardSignature(s);
    if (node.dataset.sig !== sig) {
      node.className = `card ${s.status} ${s.level === "activity" ? "activity" : ""}`;
      node.innerHTML = cardInner(s);
      node.dataset.sig = sig;
    }
    // 顺序调整
    if (prev ? prev.nextSibling !== node : cardsBox.firstChild !== node) {
      cardsBox.insertBefore(node, prev ? prev.nextSibling : cardsBox.firstChild);
    }
    prev = node;
  }
}

// 卡片内容签名：内容变才重绘。platform_paths 变化（按钮文字）也纳入。
function cardSignature(s) {
  const hasPath = platformPaths[s.platform] ? 1 : 0;
  return [s.title, s.status, s.project_path, s.last_message_preview,
          s.message_count, s.tool_call_count, s.last_active_at, s.level, hasPath].join("|");
}

function cardInner(s) {
  const ag = ago(s.last_active_at);
  const isActivity = s.level === "activity";
  const logo = getLogo(s.platform);
  const stats = isActivity
    ? `<span class="stat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>活动级</span>`
    : `<span class="stat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg><b>${s.message_count}</b></span>
       <span class="stat"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg><b>${s.tool_call_count}</b></span>`;
  const hasPath = !!platformPaths[s.platform];
  const openBtn = hasPath
    ? `<button class="open-btn" data-platform="${esc(s.platform)}" data-path="${esc(s.project_path)}" title="打开 ${esc(s.platform_label)}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><path d="M15 3h6v6"/><path d="M10 14 21 3"/></svg>打开</button>`
    : `<button class="open-btn ghost" data-platform="${esc(s.platform)}" data-path="${esc(s.project_path)}" title="未配置路径，点击设置"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>设置</button>`;
  return `
    <div class="card-top">
      <span class="card-logo" style="--brand-color:${logo.brand}">${logoSvgRaw(logo, 18)}</span>
      <span class="status-dot"></span>
      <div class="card-title">${esc(s.title)}</div>
      ${isActivity ? '<span class="level-tag">活动</span>' : ""}
    </div>
    <div class="card-path" title="${esc(s.project_path)}"><span class="pmarker">▸</span> ${esc(s.project_path || "—")}</div>
    <div class="card-preview">${esc(s.last_message_preview || "")}</div>
    <div class="card-foot">
      ${stats}
      ${openBtn}
      <span class="ago ${ag.stale ? "stale" : ""}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>${ag.text}</span>
    </div>`;
}

function logoSvgRaw(logo, size) {
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}">${logo.svg}</svg>`;
}

function diffClear(board) {
  for (const k of Object.keys(nodeMap)) delete nodeMap[k];
  // 渐隐而非瞬间清空，避免突兀
  const cols = board.querySelectorAll(".platform-group");
  cols.forEach((c) => c.remove());
}

// CSS.escape 兜底（老 WebView2 可能无）
function cssEscape(s) {
  if (window.CSS && CSS.escape) return CSS.escape(s);
  return String(s).replace(/["\\]/g, "\\$&");
}

function renderStats(sessions) {
  const active = sessions.filter((s) => s.status === "active").length;
  const idle = sessions.filter((s) => s.status !== "active").length;
  const stale = sessions.filter((s) => ago(s.last_active_at).stale).length;
  // 签名对比：只有数字变化才重绘，避免每轮轮询闪烁
  const sig = `${active}|${idle}|${stale}|${sessions.length}`;
  const bar = document.getElementById("stats-bar");
  if (bar.dataset.sig === sig) return;
  bar.dataset.sig = sig;
  const cards = [
    { cls: "active", val: active, label: "活跃中", icon: '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4 12 14.01l-3-3"/>' },
    { cls: "idle", val: idle, label: "空闲/已停", icon: '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>' },
    { cls: "stale", val: stale, label: "可能被遗忘", icon: '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><path d="M12 9v4M12 17h.01"/>' },
    { cls: "total", val: sessions.length, label: "总会话数", icon: '<path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/>' },
  ];
  bar.innerHTML = cards.map((c) =>
    `<div class="stat-card ${c.cls}">
      <span class="sicon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${c.icon}</svg></span>
      <div><div class="sval">${c.val}</div><div class="slabel">${c.label}</div></div>
    </div>`).join("");
}

// ---------- 事件 ----------
async function refresh(force) {
  try { render(await fetchSessions(force)); } catch (e) { console.error("refresh failed", e); }
}

document.getElementById("refresh-btn").addEventListener("click", () => refresh(true));
document.getElementById("filter").addEventListener("input", () => lastData && render(lastData));

function bindChip(id, key) {
  const el = document.getElementById(id);
  el.addEventListener("click", () => {
    state[key] = !state[key];
    el.classList.toggle("on", state[key]);
    if (lastData) render(lastData);
  });
}
bindChip("chip-active", "onlyActive");
bindChip("chip-stale", "onlyStale");
document.getElementById("chip-group").addEventListener("click", () => {
  state.group = !state.group;
  document.getElementById("chip-group").classList.toggle("on", state.group);
  if (lastData) render(lastData);
});

// ---------- 卡片"打开"按钮（事件委托，避免每个卡片单独绑定）----------
document.getElementById("board").addEventListener("click", (e) => {
  const btn = e.target.closest(".open-btn");
  if (!btn) return;
  const platform = btn.dataset.platform;
  const path = btn.dataset.path;
  if (!platformPaths[platform]) {
    // 未配置路径 → 打开设置面板并定位到该平台
    openSettings(platform);
    return;
  }
  launchPlatform(platform, path, btn);
});

async function launchPlatform(platform, path, btn) {
  const oldHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="animation:spin 0.8s linear infinite"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></svg>';
  try {
    const r = await fetch("/api/launch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ platform, project_path: path }),
    });
    const d = await r.json();
    toast(d.ok ? `✓ ${d.message}` : `✗ ${d.message}`, d.ok);
  } catch (err) {
    toast("✗ 打开失败：" + err.message, false);
  } finally {
    btn.disabled = false;
    btn.innerHTML = oldHtml;
  }
}

// ---------- 轻量 toast ----------
let toastTimer = null;
function toast(msg, ok) {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = "toast show " + (ok ? "ok" : "err");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.className = "toast", 3000);
}

// ---------- 设置面板（路径配置）----------
document.getElementById("settings-btn").addEventListener("click", () => openSettings());

function openSettings(focusPlatform) {
  let panel = document.getElementById("settings-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "settings-panel";
    panel.className = "modal-overlay";
    panel.innerHTML = `
      <div class="modal">
        <div class="modal-head">
          <h2>平台路径设置</h2>
          <button class="icon-btn" id="settings-close" aria-label="关闭"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></svg></button>
        </div>
        <div class="modal-body" id="settings-fields"></div>
        <div class="modal-foot">
          <span class="modal-hint">首次运行已自动扫描。未找到的可在此手动填写程序路径。</span>
        </div>
      </div>`;
    document.body.appendChild(panel);
    panel.addEventListener("click", (e) => {
      if (e.target === panel || e.target.closest("#settings-close")) panel.className = "modal-overlay";
    });
  }
  // 填充各平台输入框
  const fields = document.getElementById("settings-fields");
  fields.innerHTML = Object.keys(PLATFORM_LABELS).map((k) => {
    const v = platformPaths[k] || "";
    const status = v ? '<span class="path-ok">已配置</span>' : '<span class="path-miss">未配置</span>';
    return `<label class="field">
      <div class="field-row"><span>${PLATFORM_LABELS[k]}</span>${status}</div>
      <div class="field-input">
        <input type="text" data-platform="${k}" value="${esc(v)}" placeholder="程序 exe / cmd 完整路径" />
        <button class="save-btn" data-platform="${k}">保存</button>
      </div>
    </label>`;
  }).join("");
  // 保存按钮
  fields.querySelectorAll(".save-btn").forEach((b) => {
    b.addEventListener("click", async () => {
      const k = b.dataset.platform;
      const v = fields.querySelector(`input[data-platform="${k}"]`).value.trim();
      const r = await fetch("/api/config", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: k, path: v }),
      });
      const d = await r.json();
      if (d.ok) { platformPaths[k] = v; toast(`✓ ${PLATFORM_LABELS[k]} 路径已保存`, true); b.closest(".field").querySelector(".path-miss,.path-ok")?.replaceWith(v ? el("span","path-ok","已配置") : el("span","path-miss","未配置")); }
      else toast(`✗ ${d.message}`, false);
    });
  });
  panel.className = "modal-overlay show";
  if (focusPlatform) {
    const inp = fields.querySelector(`input[data-platform="${focusPlatform}"]`);
    if (inp) setTimeout(() => inp.focus(), 50);
  }
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  e.className = cls; e.textContent = text; return e;
}

// 初始 + 轮询
refresh(true);
setInterval(() => refresh(false), POLL_MS);
