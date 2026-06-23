// 各平台品牌标识（内联 SVG）+ 品牌主色。
// 取各平台公开 logo 的核心视觉特征简化重绘，配官方品牌色。
// 所有 logo 用 currentColor，可随主题/状态变色；brand 色用于列头底色点缀。
// viewBox 统一 0 0 24 24，stroke/fill 风格统一。

const LOGOS = {
  zcode: {
    brand: "#6366f1",
    // ZCode：抽象重叠方块（呼应其多平台聚合的定位）
    svg: '<rect x="3" y="3" width="8" height="8" rx="1.5" fill="currentColor"/><rect x="13" y="3" width="8" height="5" rx="1.5" fill="currentColor" opacity="0.7"/><rect x="13" y="12" width="8" height="9" rx="1.5" fill="currentColor" opacity="0.7"/><rect x="3" y="15" width="8" height="6" rx="1.5" fill="currentColor" opacity="0.7"/>',
  },
  cursor: {
    brand: "#14b8a6",
    // Cursor：光标/箭头形（呼应"光标"语义）
    svg: '<path d="M5 3 19 12 12 13 9 20z" fill="currentColor"/>',
  },
  codex: {
    brand: "#10a37f",
    // Codex (OpenAI)：六瓣花
    svg: '<circle cx="12" cy="12" r="3" fill="currentColor"/><g fill="currentColor"><ellipse cx="12" cy="5" rx="2" ry="3.2"/><ellipse cx="12" cy="19" rx="2" ry="3.2"/><ellipse cx="5" cy="12" rx="3.2" ry="2"/><ellipse cx="19" cy="12" rx="3.2" ry="2"/><ellipse cx="7" cy="7" rx="2" ry="2.6" transform="rotate(-45 7 7)"/><ellipse cx="17" cy="7" rx="2" ry="2.6" transform="rotate(45 17 7)"/><ellipse cx="7" cy="17" rx="2" ry="2.6" transform="rotate(45 7 17)"/><ellipse cx="17" cy="17" rx="2" ry="2.6" transform="rotate(-45 17 17)"/></g>',
  },
  claude: {
    brand: "#d97757",
    // Claude (Anthropic)：星芒放射（呼应 Anthropic 的星形标识）
    svg: '<g fill="currentColor"><path d="M12 2 13.8 9 21 12 13.8 15 12 22 10.2 15 3 12 10.2 9z"/></g><g fill="currentColor" opacity="0.5"><path d="M12 5 13 9 12 10 11 9z"/></g>',
  },
  pycharm: {
    brand: "#21d789",
    // PyCharm (JetBrains)：方块内 PC 字样抽象
    svg: '<rect x="3" y="3" width="18" height="18" rx="3" fill="currentColor"/><rect x="6.5" y="6.5" width="11" height="11" rx="1.5" fill="none" stroke="#fff" stroke-width="1.4"/><path d="M8.5 16V8h3.2a2 2 0 0 1 0 4H10" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/><path d="M13.5 16V8" stroke="#fff" stroke-width="1.3" stroke-linecap="round"/>',
  },
  idea: {
    brand: "#f47fff",
    // IntelliJ IDEA (JetBrains)：方块内 I 字
    svg: '<rect x="3" y="3" width="18" height="18" rx="3" fill="currentColor"/><path d="M8 8h8M12 8v8" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/><path d="M9.5 17h5" stroke="#fff" stroke-width="1.5" stroke-linecap="round"/>',
  },
  goland: {
    brand: "#ff6b9d",
    // GoLand (JetBrains)：方块内 GO
    svg: '<rect x="3" y="3" width="18" height="18" rx="3" fill="currentColor"/><circle cx="10" cy="13" r="2.3" fill="none" stroke="#fff" stroke-width="1.3"/><path d="M12.3 11v4h2.2" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>',
  },
  clion: {
    brand: "#f472b6",
    // CLion (JetBrains)：方块内 CL
    svg: '<rect x="3" y="3" width="18" height="18" rx="3" fill="currentColor"/><path d="M8 8v8M8 12h3" stroke="#fff" stroke-width="1.4" stroke-linecap="round"/><path d="M14 8v8M14 8h2.5a2 2 0 0 1 0 4H14" fill="none" stroke="#fff" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/>',
  },
  rustrover: {
    brand: "#ff7043",
    // RustRover (JetBrains)：方块内齿轮抽象
    svg: '<rect x="3" y="3" width="18" height="18" rx="3" fill="currentColor"/><circle cx="12" cy="12" r="3" fill="none" stroke="#fff" stroke-width="1.3"/><g stroke="#fff" stroke-width="1.3" stroke-linecap="round"><path d="M12 5v2M12 17v2M5 12h2M17 12h2M7 7l1.4 1.4M15.6 15.6 17 17M7 17l1.4-1.4M15.6 8.4 17 7"/></g>',
  },
};

// 未知平台的兜底标识
const DEFAULT_LOGO = {
  brand: "#94a3b8",
  svg: '<rect x="3" y="3" width="18" height="18" rx="4" fill="none" stroke="currentColor" stroke-width="2"/><path d="M9 12h6M12 9v6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>',
};

function getLogo(platform) {
  return LOGOS[platform] || DEFAULT_LOGO;
}

// 返回带指定尺寸/颜色的 svg 字符串
function logoSvg(platform, size = 24, color = null) {
  const logo = getLogo(platform);
  const style = color ? `color:${color}` : "";
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" style="${style}" aria-hidden="true">${logo.svg}</svg>`;
}
