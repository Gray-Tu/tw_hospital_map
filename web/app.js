/* 台灣醫院經營版圖 — 前端邏輯 */
(() => {
"use strict";

const FAMILY_COLOR = {
  "企業財團": "#e0563f",
  "宗教團體": "#e6a417",
  "大學醫療體系": "#2f6fd0",
  "公立醫療": "#16a085",
  "私人醫療法人": "#8e5bd0",
  "其他公益法人": "#6b7f99",
  "獨立醫院": "#98a2b3",
};
const LEVELS = ["醫學中心", "區域醫院", "地區醫院"];
const LEVEL_RADIUS = { "醫學中心": 9, "區域醫院": 6.5, "地區醫院": 4.5 };

const S = {           // 篩選狀態
  q: "", county: "", families: new Set(), levels: new Set(), tags: new Set(),
  group: null, showLinks: false,
};
let DATA, map, markerLayer, linkLayer, highlight, markers = new Map();
let countyLayer, countyShapes = new Map();

// 台灣本島視野（外島仍可平移過去，但預設不佔版面）
const MAIN_ISLAND = [[21.85, 119.95], [25.35, 122.05]];
const TW_BOUNDS = [[20.5, 117.5], [26.6, 123.0]];

const $ = (sel) => document.querySelector(sel);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
// 搜尋用正規化：台/臺 通用、英數不分大小寫（使用者常打「台大」找「臺灣大學」）
const norm = (s) => String(s ?? "").replace(/台/g, "臺").toLowerCase();

/* ── 啟動 ─────────────────────────────────────────── */
fetch("data/app_data.json")
  .then((r) => r.json())
  .then((d) => { DATA = d; init(); })
  .catch((e) => { $("#subtitle").textContent = "資料載入失敗：" + e.message; });

function init() {
  const m = DATA.meta;
  $("#subtitle").textContent =
    `全台 ${m.hospital_count} 家健保特約醫院 · ${Object.keys(DATA.group_stats).length} 個經營體系 · 資料更新 ${m.generated}`;

  map = L.map("map", {
    zoomControl: true, preferCanvas: true,
    minZoom: 7, maxZoom: 12,   // 底圖只有縣市界，再放大也沒有更多資訊
    maxBounds: TW_BOUNDS, maxBoundsViscosity: .7,
    attributionControl: true,
  }).fitBounds(MAIN_ISLAND);
  map.attributionControl.addAttribution(
    "縣市界：內政部（g0v/twgeojson）｜醫院資料：衛福部中央健康保險署");
  // 縣市底圖放進獨立 pane，zIndex 低於 overlayPane(400)，
  // 否則它會畫在同一張 canvas 上把醫院點蓋掉。
  map.createPane("counties");
  map.getPane("counties").style.zIndex = 350;
  countyLayer = L.layerGroup().addTo(map);
  linkLayer = L.layerGroup().addTo(map);
  markerLayer = L.layerGroup().addTo(map);

  window.__map = map;   // 供除錯查詢
  // CSS grid 版面在 Leaflet 初始化時尚未定案，容器尺寸會被讀成 0，
  // 造成之後 fitBounds 算出錯誤縮放；改用 ResizeObserver 持續校正。
  new ResizeObserver(() => map.invalidateSize()).observe($("#mapWrap"));
  loadCounties();
  buildMarkers();
  buildChips();
  buildCountySelect();
  buildGroupList();
  buildLegend();
  bindUI();
  apply();
}

/* ── 底圖：只畫台灣縣市界，不用外部圖磚 ─────────────── */
function loadCounties() {
  fetch("data/tw_counties.geojson")
    .then((r) => r.json())
    .then((geo) => {
      L.geoJSON(geo, {
        pane: "counties",
        renderer: L.canvas({ pane: "counties" }),
        style: countyStyle,
        onEachFeature: (ft, lyr) => {
          const name = ft.properties.name;
          countyShapes.set(name, lyr);
          const n = DATA.county_counts[name] || 0;
          const c = DATA.county_center_counts[name] || 0;
          lyr.bindTooltip(
            `${name}<br><small>${n} 家醫院${c ? "・醫學中心 " + c : ""}</small>`,
            { sticky: true });
          lyr.on("click", () => {
            S.county = S.county === name ? "" : name;
            $("#county").value = S.county;
            apply();
            zoomToCounty();
          });
        },
      }).addTo(countyLayer);
      paintCounties();
    })
    .catch(() => { /* 底圖載不到不影響資料點 */ });
}

function countyStyle(ft) {
  const on = S.county && ft.properties.name === S.county;
  return {
    color: on ? "#7d8a9e" : "#b6c1d1",
    weight: on ? 1.8 : 1,
    fillColor: on ? "#dfe7f4" : "#eef1f5",
    fillOpacity: 1,
  };
}

function paintCounties() {
  countyShapes.forEach((lyr, name) =>
    lyr.setStyle(countyStyle({ properties: { name } })));
}

/* ── 圖層 ─────────────────────────────────────────── */
function buildMarkers() {
  DATA.hospitals.forEach((h) => {
    if (h.lat == null) return;
    const mk = L.circleMarker([h.lat, h.lon], {
      radius: LEVEL_RADIUS[h.lv] || 5,
      color: "#fff", weight: 1.2,
      fillColor: FAMILY_COLOR[h.fam] || "#98a2b3", fillOpacity: .88,
    });
    mk.bindTooltip(`${h.n}<br><small>${h.lv}・${groupLabel(h)}</small>`,
      { direction: "top", offset: [0, -4] });
    mk.on("click", () => showHospital(h));
    mk._h = h;
    markers.set(h.id, mk);
  });
}

function groupLabel(h) {
  const gid = h.pg || h.og;
  if (gid && DATA.groups[gid]) return DATA.groups[gid].short || DATA.groups[gid].name;
  return h.ik || "獨立醫院";
}

/* ── 篩選 UI ──────────────────────────────────────── */
function buildChips() {
  const famBox = $("#familyChips");
  DATA.family_order.forEach((f) => {
    const c = el("div", "chip",
      `<span class="dot" style="background:${FAMILY_COLOR[f]}"></span>${f}`);
    c.onclick = () => { toggle(S.families, f); c.classList.toggle("on"); apply(); };
    famBox.appendChild(c);
  });

  const lvBox = $("#levelChips");
  LEVELS.forEach((l) => {
    const c = el("div", "chip", l);
    c.onclick = () => { toggle(S.levels, l); c.classList.toggle("on"); apply(); };
    lvBox.appendChild(c);
  });

  const counts = {};
  DATA.hospitals.forEach((h) => h.tg.forEach((t) => counts[t] = (counts[t] || 0) + 1));
  const tagBox = $("#tagChips");
  Object.entries(counts).sort((a, b) => b[1] - a[1]).forEach(([t, n]) => {
    const c = el("div", "chip", `${t}<span class="muted">${n}</span>`);
    c.onclick = () => { toggle(S.tags, t); c.classList.toggle("on"); apply(); };
    tagBox.appendChild(c);
  });
}

function toggle(set, v) { set.has(v) ? set.delete(v) : set.add(v); }

function buildCountySelect() {
  const sel = $("#county");
  Object.entries(DATA.county_counts).sort((a, b) => b[1] - a[1]).forEach(([c, n]) => {
    const o = document.createElement("option");
    o.value = c; o.textContent = `${c}（${n}）`;
    sel.appendChild(o);
  });
  sel.onchange = () => { S.county = sel.value; apply(); zoomToCounty(); };
}

function zoomToCounty() {
  map.stop();
  const pts = DATA.hospitals.filter((h) => h.lat != null && (!S.county || h.ct === S.county))
    .map((h) => [h.lat, h.lon]);
  if (!pts.length) return;
  map.fitBounds(L.latLngBounds(pts).pad(.15), {
    maxZoom: 11, paddingTopLeft: [20, 20],
    paddingBottomRight: [drawerWidth() + 20, 20],
  });
}

function buildGroupList() {
  const list = $("#groupList");
  const rows = Object.entries(DATA.group_stats)
    .map(([gid, s]) => ({ gid, s, g: DATA.groups[gid] }))
    .filter((r) => r.g)
    .sort((a, b) => b.s.count - a.s.count || a.g.name.localeCompare(b.g.name, "zh-Hant"));
  $("#groupCount").textContent = `(${rows.length})`;
  rows.forEach(({ gid, s, g }) => {
    const item = el("div", "group-item");
    item.dataset.gid = gid;
    item.innerHTML =
      `<span class="bar" style="background:${FAMILY_COLOR[g.family]}"></span>` +
      `<span class="gname">${esc(g.name)}<small>${esc(g.backer || g.kind)}</small></span>` +
      `<span class="gcount">${s.count}</span>`;
    item.onclick = () => selectGroup(S.group === gid ? null : gid);
    list.appendChild(item);
  });
}

const LEGEND_KEY = "twhm.legendHidden";

function buildLegend() {
  const box = $("#legendItems");
  DATA.family_order.forEach((f) => {
    box.appendChild(el("div", null,
      `<i style="background:${FAMILY_COLOR[f]}"></i>${f}`));
  });
  box.appendChild(el("div", "sizes", "圈越大＝層級越高（醫學中心 ▸ 區域 ▸ 地區）"));

  let hidden = false;
  try { hidden = localStorage.getItem(LEGEND_KEY) === "1"; } catch (e) { /* 無痕模式等情境 */ }
  setLegend(!hidden);
  $("#legendClose").onclick = () => setLegend(false);
  $("#legendShow").onclick = () => setLegend(true);
}

function setLegend(show) {
  $("#legend").hidden = !show;
  $("#legendShow").hidden = show;
  try { localStorage.setItem(LEGEND_KEY, show ? "0" : "1"); } catch (e) { /* 忽略 */ }
}

function bindUI() {
  let t;
  $("#q").oninput = (e) => {
    clearTimeout(t);
    t = setTimeout(() => { S.q = e.target.value.trim(); apply(); }, 180);
  };
  $("#showLinks").onchange = (e) => { S.showLinks = e.target.checked; drawLinks(); };
  $("#btnReset").onclick = () => {
    S.q = ""; S.county = ""; S.families.clear(); S.levels.clear(); S.tags.clear();
    $("#q").value = ""; $("#county").value = "";
    document.querySelectorAll(".chip.on").forEach((c) => c.classList.remove("on"));
    selectGroup(null);
    map.stop();
    map.fitBounds(MAIN_ISLAND);
  };
  $("#btnAnalysis").onclick = showAnalysis;
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") $("#detailClose").click();
  });
  $("#detailClose").onclick = () => {
    $("#detail").classList.add("closed");
    document.body.classList.remove("drawer-open");
    if (highlight) { map.removeLayer(highlight); highlight = null; }
  };
}

/* ── 套用篩選 ─────────────────────────────────────── */
function match(h) {
  if (S.group && (h.pg || h.og) !== S.group) return false;
  if (S.county && h.ct !== S.county) return false;
  if (S.families.size && !S.families.has(h.fam)) return false;
  if (S.levels.size && !S.levels.has(h.lv)) return false;
  if (S.tags.size && ![...S.tags].every((t) => h.tg.includes(t))) return false;
  if (S.q) {
    const hay = norm(`${h.n} ${h.ad} ${h.ct}${h.tw} ${h.dp.join("")} ${h.tg.join("")} ${groupLabel(h)}`);
    if (!hay.includes(norm(S.q))) return false;
  }
  return true;
}

function apply() {
  markerLayer.clearLayers();
  let shown = 0, noGeo = 0;
  DATA.hospitals.forEach((h) => {
    const mk = markers.get(h.id);
    if (!match(h)) return;
    shown++;
    if (!mk) { noGeo++; return; }
    markerLayer.addLayer(mk);
  });
  paintCounties();
  $("#counter").innerHTML =
    `${shown} 家醫院 <span>／ 全台 ${DATA.meta.hospital_count} 家` +
    (noGeo ? `・${noGeo} 家未定位` : "") + `</span>`;
  drawLinks();
}

/* 布點連線：由體系重心拉線到各院區，凸顯版圖擴張路徑 */
function drawLinks() {
  linkLayer.clearLayers();
  if (!S.showLinks) return;
  const byGroup = new Map();
  DATA.hospitals.forEach((h) => {
    if (h.lat == null || !match(h)) return;
    const gid = h.pg || h.og;
    if (!gid) return;
    if (!byGroup.has(gid)) byGroup.set(gid, []);
    byGroup.get(gid).push(h);
  });
  byGroup.forEach((hs, gid) => {
    if (hs.length < 2) return;
    const g = DATA.groups[gid];
    const cx = hs.reduce((a, h) => a + h.lat, 0) / hs.length;
    const cy = hs.reduce((a, h) => a + h.lon, 0) / hs.length;
    hs.forEach((h) => {
      linkLayer.addLayer(L.polyline([[cx, cy], [h.lat, h.lon]], {
        color: FAMILY_COLOR[g ? g.family : "獨立醫院"],
        weight: 1, opacity: .45, dashArray: "3,4", interactive: false,
      }));
    });
    linkLayer.addLayer(L.circleMarker([cx, cy], {
      radius: 3, color: FAMILY_COLOR[g ? g.family : "獨立醫院"],
      weight: 1, fillOpacity: 1, interactive: false,
    }));
  });
}

function selectGroup(gid) {
  S.group = gid;
  document.querySelectorAll(".group-item").forEach((n) =>
    n.classList.toggle("on", n.dataset.gid === gid));
  apply();
  if (gid) {
    map.stop();
    const pts = DATA.hospitals.filter((h) => (h.pg || h.og) === gid && h.lat != null)
      .map((h) => [h.lat, h.lon]);
    // 右側詳情抽屜會蓋住地圖，縮放時預留空間
    if (pts.length) map.fitBounds(L.latLngBounds(pts).pad(.15), {
      maxZoom: 11, paddingTopLeft: [20, 20],
      paddingBottomRight: [drawerWidth() + 20, 20],
    });
    showGroup(gid);
  }
}

/* ── 詳情面板 ─────────────────────────────────────── */
function drawerWidth() {
  const d = $("#detail");
  return (d.classList.contains("closed") || window.innerWidth <= 860) ? 0 : d.offsetWidth;
}

function openDetail(html) {
  $("#detailBody").innerHTML = html;
  $("#detail").classList.remove("closed");
  document.body.classList.add("drawer-open");
  $("#detailBody").scrollTop = 0;
}

function ownerCard(gid, label) {
  const g = DATA.groups[gid];
  if (!g) return "";
  const color = FAMILY_COLOR[g.family];
  return `<div class="section-t">${label}</div>
    <div class="owner-card" style="border-left-color:${color}">
      <div class="oname">${esc(g.name)}</div>
      ${g.backer ? `<div class="obacker">背後主體：${esc(g.backer)}</div>` : ""}
      <div style="margin-top:6px">
        <span class="badge solid" style="background:${color}">${esc(g.family)}</span>
        <span class="badge">${esc(g.kind)}</span>
        ${g.founded ? `<span class="badge">創立 ${esc(g.founded)}</span>` : ""}
        <span class="badge">${(DATA.group_stats[gid] || {}).count || 0} 家院所</span>
      </div>
      ${g.note ? `<p>${esc(g.note)}</p>` : ""}
      <div class="links">
        ${g.website ? `<a href="${esc(g.website)}" target="_blank" rel="noopener">體系官方網站 ↗</a>` : ""}
        <a href="#" data-gid="${gid}" class="js-group">查看體系版圖 →</a>
      </div>
    </div>`;
}

function showHospital(h) {
  const gid = h.pg || h.og;
  const delegated = h.dl && h.og && h.pg && h.og !== h.pg;
  let html = `<h3>${esc(h.n)}</h3>
    <div class="sub">${esc(h.ct)}${esc(h.tw)}・${esc(h.lv)}・${esc(h.kd)}</div>
    <div>${h.tg.map((t) => `<span class="badge">${esc(t)}</span>`).join("")}</div>
    <dl class="kv">
      <dt>地址</dt><dd>${esc(h.ad)}</dd>
      <dt>電話</dt><dd>${esc(h.ph)}</dd>
      <dt>經營體系</dt><dd>${esc(groupLabel(h))}</dd>
    </dl>`;

  if (delegated) {
    html += ownerCard(h.og, "產權／設立主體");
    html += ownerCard(h.pg, "受託經營團隊（公辦民營）");
    html += `<p class="note" style="margin-top:8px">院名登記之委託對象：${esc(h.dl)}</p>`;
  } else if (gid) {
    html += ownerCard(gid, "經營體系");
  } else {
    html += `<div class="section-t">經營型態</div>
      <div class="owner-card" style="border-left-color:${FAMILY_COLOR["獨立醫院"]}">
        <div class="oname">${esc(h.ik || "獨立醫院")}</div>
        <p>未隸屬於本專案已彙整的大型醫療體系，多為單一院區或家族經營。</p>
      </div>`;
  }

  if (h.note) html += `<div class="section-t">院方備註（健保署）</div><p class="note">${esc(h.note)}</p>`;

  html += `<div class="section-t">診療科別（${h.dp.length}）</div>
    <div>${h.dp.map((d) => `<span class="badge">${esc(d)}</span>`).join("")}</div>
    <div class="section-t">外部連結</div>
    <div class="links">
      ${h.web ? `<a href="${esc(h.web)}" target="_blank" rel="noopener">醫院官方網站 ↗</a>` : ""}
      <a href="${esc(h.mu)}" target="_blank" rel="noopener">Google 地圖 ↗</a>
      ${h.web ? "" : `<a href="${esc(h.su)}" target="_blank" rel="noopener">搜尋官方網站 ↗</a>`}
    </div>`;
  if (h.gm === "town-centroid")
    html += `<p class="note" style="margin-top:12px">※ 此點為鄉鎮市區概略中心，非精確門牌座標。</p>`;

  openDetail(html);
  bindDetailLinks();
  const mk = markers.get(h.id);
  if (mk) {
    map.setView(mk.getLatLng(), Math.max(map.getZoom(), 10));
    if (highlight) map.removeLayer(highlight);
    highlight = L.circleMarker(mk.getLatLng(), {
      radius: 15, color: FAMILY_COLOR[h.fam] || "#98a2b3", weight: 2,
      fill: false, dashArray: "4,3", interactive: false,
    }).addTo(map);
  }
}

function bars(entries, color, clickKind) {
  const max = Math.max(...entries.map((e) => e[1]), 1);
  const box = entries.map(([k, v]) =>
    `<div class="row${clickKind ? " js-" + clickKind : ""}" data-k="${esc(k)}">
       <span class="label">${esc(k)}</span>
       <span class="track"><span class="fill" style="width:${(v / max * 100).toFixed(1)}%;background:${color}"></span></span>
       <span class="num">${v}</span>
     </div>`).join("");
  return `<div class="bars">${box}</div>`;
}

function showGroup(gid) {
  const g = DATA.groups[gid], s = DATA.group_stats[gid];
  if (!g || !s) return;
  const color = FAMILY_COLOR[g.family];
  const hs = DATA.hospitals.filter((h) => (h.pg || h.og) === gid)
    .sort((a, b) => LEVELS.indexOf(a.lv) - LEVELS.indexOf(b.lv) || a.ct.localeCompare(b.ct, "zh-Hant"));

  let html = `<h3>${esc(g.name)}</h3>
    <div class="sub">${esc(g.kind)}${g.founded ? "・創立 " + esc(g.founded) : ""}</div>
    <div>
      <span class="badge solid" style="background:${color}">${esc(g.family)}</span>
      <span class="badge">${s.count} 家院所</span>
      <span class="badge">${Object.keys(s.county_counts).length} 個縣市</span>
    </div>`;
  if (g.backer) html += `<dl class="kv"><dt>背後主體</dt><dd>${esc(g.backer)}</dd></dl>`;
  if (g.note) html += `<p class="note">${esc(g.note)}</p>`;
  if (g.website) html += `<div class="links"><a href="${esc(g.website)}" target="_blank" rel="noopener">體系官方網站 ↗</a></div>`;

  html += `<div class="section-t">層級組成</div>` +
    bars(LEVELS.filter((l) => s.levels[l]).map((l) => [l, s.levels[l]]), color);
  html += `<div class="section-t">縣市布點</div>` +
    bars(Object.entries(s.county_counts).sort((a, b) => b[1] - a[1]), color);
  if (s.tags.length)
    html += `<div class="section-t">體系醫療特色</div><div>${s.tags.map((t) => `<span class="badge">${esc(t)}</span>`).join("")}</div>`;

  html += `<div class="section-t">院所清單</div>` + hs.map((h) =>
    `<div class="hosp-line js-hosp" data-id="${h.id}">${esc(h.n)}<br><small>${esc(h.ct)}${esc(h.tw)}・${esc(h.lv)}${h.dl ? "・公辦民營" : ""}</small></div>`).join("");

  openDetail(html);
  bindDetailLinks();
}

function showAnalysis() {
  const rows = Object.entries(DATA.group_stats)
    .map(([gid, s]) => [gid, s.count])
    .sort((a, b) => b[1] - a[1]).slice(0, 20);
  const famCount = {};
  DATA.hospitals.forEach((h) => famCount[h.fam] = (famCount[h.fam] || 0) + 1);

  let html = `<h3>經營版圖總覽</h3>
    <div class="sub">全台 ${DATA.meta.hospital_count} 家健保特約醫院的經營結構</div>
    <div class="section-t">經營型態占比</div>` +
    bars(DATA.family_order.filter((f) => famCount[f]).map((f) => [f, famCount[f]]), "#6b7f99");

  html += `<div class="section-t">體系規模 Top 20</div>` +
    `<div class="bars">` +
    rows.map(([gid, n]) => {
      const g = DATA.groups[gid];
      const max = rows[0][1];
      return `<div class="row js-group-row" data-gid="${gid}">
        <span class="label">${esc(g.short || g.name)}</span>
        <span class="track"><span class="fill" style="width:${(n / max * 100).toFixed(1)}%;background:${FAMILY_COLOR[g.family]}"></span></span>
        <span class="num">${n}</span></div>`;
    }).join("") + `</div>`;

  html += `<div class="section-t">各縣市醫院數</div>` +
    bars(Object.entries(DATA.county_counts).sort((a, b) => b[1] - a[1]), "#2f6fd0", "county");
  html += `<div class="section-t">醫學中心分布</div>` +
    bars(Object.entries(DATA.county_center_counts).sort((a, b) => b[1] - a[1]), "#e0563f");

  html += `<div class="section-t">資料來源</div><div class="links">` +
    DATA.meta.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)} ↗</a>`).join("<br>") +
    `</div><p class="note" style="margin-top:10px">經營體系歸屬依院所全名中的法人主體判定，並人工比對各體系公開資訊；「背後主體」為公開可查的創辦或出資方，僅供研究參考。</p>`;

  openDetail(html);
  bindDetailLinks();
}

function bindDetailLinks() {
  $("#detailBody").querySelectorAll(".js-hosp").forEach((n) => {
    n.onclick = () => {
      const h = DATA.hospitals.find((x) => x.id === n.dataset.id);
      if (h) showHospital(h);
    };
  });
  $("#detailBody").querySelectorAll(".js-county").forEach((n) => {
    n.onclick = () => {
      S.county = n.dataset.k; $("#county").value = S.county; apply(); zoomToCounty();
    };
  });
  $("#detailBody").querySelectorAll(".js-group, .js-group-row").forEach((n) => {
    n.onclick = (e) => { e.preventDefault(); selectGroup(n.dataset.gid); };
  });
}
})();
