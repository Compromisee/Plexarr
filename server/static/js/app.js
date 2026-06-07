/* Plexarr V2.1 — Frontend Application */
const socket = io({ transports: ["websocket", "polling"], reconnection: true });
let currentFilePath = "";
let currentFileRoot = "downloads";
let searchResults = [];
let animeResults = [];
let providers = [];
let screenActive = false;
let batchSelections = new Set();
let animeSelections = new Set();
let logCount = 0;

// ── Dot Matrix Background ──
(function initDotMatrix(){
  const canvas = document.getElementById("dotMatrix");
  if(!canvas) return;
  const ctx = canvas.getContext("2d");
  let w, h, dots = [];
  const DOT_COUNT = 120;
  const SPEED = 0.3;
  function resize(){
    w = canvas.width = window.innerWidth;
    h = canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener("resize", resize);
  for(let i=0;i<DOT_COUNT;i++){
    dots.push({
      x: Math.random()*w, y: Math.random()*h,
      vx: (Math.random()-0.5)*SPEED, vy: (Math.random()-0.5)*SPEED,
      r: Math.random()*1.5+0.5, a: Math.random()*0.5+0.1,
    });
  }
  function draw(){
    ctx.clearRect(0,0,w,h);
    for(const d of dots){
      d.x += d.vx; d.y += d.vy;
      if(d.x<0) d.x=w; if(d.x>w) d.x=0;
      if(d.y<0) d.y=h; if(d.y>h) d.y=0;
      ctx.beginPath();
      ctx.arc(d.x,d.y,d.r,0,Math.PI*2);
      ctx.fillStyle = `rgba(100,110,130,${d.a})`;
      ctx.fill();
    }
    requestAnimationFrame(draw);
  }
  draw();
})();

// ── SocketIO ──
socket.on("connect", () => {
  setConn(true);
  socket.emit("request_torrents");
  addLog("Connected to server");
});
socket.on("disconnect", () => setConn(false));
socket.on("torrent_list", (data) => {
  renderTorrents(data.torrents || []);
});
socket.on("screen_frame", (msg) => {
  const img = document.getElementById("screenView");
  if(img && msg.data) img.src = "data:image/jpeg;base64," + msg.data;
});

// ── Tabs ──
function showTab(id){
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-btn").forEach((b) => b.classList.remove("active"));
  const target = document.getElementById(id);
  if(target) target.classList.add("active");
  const btn = document.querySelector(`[data-tab="${id}"]`);
  if(btn) btn.classList.add("active");
  if(id === "files") loadFiles();
  if(id === "settings") loadSettings();
  if(id === "torrents") socket.emit("request_torrents");
  if(id === "search") { if(!providers.length) loadProviders(); }
  if(id === "anime") loadAnimeProviders();
}

// ── Connection Status ──
function setConn(ok){
  const dot = document.getElementById("conn-dot");
  const label = document.getElementById("conn-label");
  if(ok){ dot.className = "status-dot online"; label.textContent = "ONLINE"; }
  else{ dot.className = "status-dot offline"; label.textContent = "OFFLINE"; }
}

function addLog(msg){
  const el = document.getElementById("dash-log");
  if(!el) return;
  const line = document.createElement("div");
  line.textContent = `> ${msg}`;
  el.prepend(line);
  if(el.children.length > 50) el.lastChild.remove();
}

// ── Providers ──
async function loadProviders(){
  try{
    const r = await fetch("/api/providers");
    providers = await r.json();
    const sel = document.getElementById("searchProvider");
    sel.innerHTML = '<option value="">ALL</option>' + providers.filter(p => !p.requires_cloudflare || p.anime_only === false).map((p) => `<option value="${p.name}">${p.name.toUpperCase()}</option>`).join("");
  } catch(e){ toast("Failed to load providers", "error"); }
}

function loadAnimeProviders(){
  const sel = document.getElementById("animeCategory");
  if(!sel) return;
}

// ── Torrent Search ──
async function doSearch(){
  const q = document.getElementById("searchQuery").value.trim();
  const provider = document.getElementById("searchProvider").value;
  const type = document.getElementById("searchType").value;
  const enrich = document.getElementById("enrichMeta")?.checked;
  const out = document.getElementById("searchResults");
  if(!q) return;
  out.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">Searching...</div>';
  try{
    const url = new URL("/api/search", location.origin);
    url.searchParams.set("q", q);
    if(provider) url.searchParams.set("provider", provider);
    if(type) url.searchParams.set("type", type);
    if(enrich) url.searchParams.set("enrich", "true");
    const r = await fetch(url);
    const data = await r.json();
    searchResults = data.results || [];
    renderSearchResults();
    if(enrich) renderMeta(data);
  } catch(e){
    out.innerHTML = `<div style="color:var(--danger); font-size:11px;">SEARCH FAILED: ${e.message}</div>`;
  }
}

function renderSearchResults(){
  const out = document.getElementById("searchResults");
  const batchMode = document.getElementById("batchMode")?.checked;
  document.getElementById("batchActions").style.display = batchMode ? "block" : "none";
  if(!searchResults.length){ out.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">No results.</div>'; return; }
  out.innerHTML = searchResults.map((r, i) => {
    const s = r.seeders || "?";
    const l = r.leechers || "?";
    const sz = r.size || "?";
    const res = r.resolution ? `<span class="badge accent">${r.resolution}</span>` : "";
    const cat = r.category ? `<span class="badge">${r.category}</span>` : "";
    const cf = r.requires_cloudflare ? `<span class="badge danger">CF</span>` : "";
    const magnet = r.magnet ? `<button class="btn primary small" onclick="addMagnet(${i})"><span class="micon">add</span></button>` : "";
    const torrent = r.torrent ? `<a class="btn small" href="${r.torrent}" target="_blank">.TORRENT</a>` : "";
    const batchCheck = batchMode ? `<label class="toggle" style="margin-right:8px;" onclick="event.stopPropagation()"><input type="checkbox" onchange="toggleBatch(${i})" ${batchSelections.has(i) ? 'checked' : ''}><span class="slider"></span></label>` : "";
    const cover = r.metadata?.cover_url ? `<div style="margin-bottom:8px;"><img src="${r.metadata.cover_url}" style="max-height:120px; border:1px solid var(--border);" alt="cover"></div>` : "";
    return `
    <div class="result-card" data-idx="${i}">
      ${cover}
      <div class="row" style="align-items:center;">
        ${batchCheck}
        <div class="result-title">${esc(r.title)}</div>
      </div>
      <div class="result-meta">
        <span><span class="micon" style="font-size:11px;">trending_up</span> ${s}</span>
        <span><span class="micon" style="font-size:11px;">trending_down</span> ${l}</span>
        <span><span class="micon" style="font-size:11px;">save</span> ${sz}</span>
        <span>${esc(r.provider)}</span>
        ${res} ${cat} ${cf}
      </div>
      <div class="result-actions">
        ${magnet}
        ${torrent}
        <a class="btn small" href="${esc(r.page)}" target="_blank"><span class="micon">open_in_new</span> PAGE</a>
      </div>
    </div>`;
  }).join("");
}

function renderMeta(data){
  const el = document.getElementById("searchMeta");
  const out = document.getElementById("metaResults");
  if(!el || !out) return;
  el.style.display = "block";
  let html = "";
  if(data.tmdb_movies && data.tmdb_movies.length){
    html += data.tmdb_movies.slice(0,3).map(m => `<div style="margin-bottom:6px; font-size:11px; display:flex; gap:10px; align-items:center;">
      ${m.poster_path ? `<img src="${m.poster_path}" style="height:60px; border:1px solid var(--border);" alt="">` : ""}
      <div><strong>${esc(m.title || "?")}</strong> (${m.release_date || "?"})<br><span style="color:var(--text-3)">${(m.overview || "").substring(0,80)}...</span></div>
    </div>`).join("");
  }
  if(data.tmdb_tv && data.tmdb_tv.length){
    html += data.tmdb_tv.slice(0,3).map(m => `<div style="margin-bottom:6px; font-size:11px; display:flex; gap:10px; align-items:center;">
      ${m.poster_path ? `<img src="${m.poster_path}" style="height:60px; border:1px solid var(--border);" alt="">` : ""}
      <div><strong>${esc(m.name || "?")}</strong> (${m.first_air_date || "?"})<br><span style="color:var(--text-3)">${(m.overview || "").substring(0,80)}...</span></div>
    </div>`).join("");
  }
  if(!html) html = "No metadata found.";
  out.innerHTML = html;
}

function toggleBatch(idx){
  if(batchSelections.has(idx)) batchSelections.delete(idx);
  else batchSelections.add(idx);
  document.getElementById("batchCount").textContent = batchSelections.size + " selected";
}

function clearBatch(){
  batchSelections.clear();
  document.getElementById("batchCount").textContent = "0 selected";
  renderSearchResults();
}

async function addBatchSelected(){
  const indices = Array.from(batchSelections);
  for(const i of indices){
    await addMagnet(i);
  }
  batchSelections.clear();
  document.getElementById("batchCount").textContent = "0 selected";
  renderSearchResults();
  toast("Batch added: " + indices.length + " items", "success");
}

async function addMagnet(index){
  const r = searchResults[index];
  if(!r || !r.magnet) return;
  try{
    const body = new URLSearchParams();
    body.append("magnet", r.magnet);
    body.append("category", r.category || "downloads");
    body.append("media_type", r.category || "auto");
    const res = await fetch("/api/torrent/add", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
    const data = await res.json();
    if(data.success){ toast("Magnet added", "success"); addLog(`Added: ${r.title.substring(0, 60)}`); }
    else toast("Server rejected", "warn");
  } catch(e){ toast("Failed to add", "error"); }
}

// ── Anime Search ──
async function doAnimeSearch(){
  const q = document.getElementById("animeQuery").value.trim();
  const category = document.getElementById("animeCategory").value;
  const enrich = document.getElementById("animeEnrich")?.checked;
  const out = document.getElementById("animeResults");
  if(!q) return;
  out.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">Searching...</div>';
  try{
    const url = new URL("/api/search/anime", location.origin);
    url.searchParams.set("q", q);
    if(category) url.searchParams.set("category", category);
    if(enrich) url.searchParams.set("enrich", "true");
    const r = await fetch(url);
    const data = await r.json();
    animeResults = data.results || [];
    renderAnimeResults();
  } catch(e){
    out.innerHTML = `<div style="color:var(--danger); font-size:11px;">SEARCH FAILED: ${e.message}</div>`;
  }
}

function renderAnimeResults(){
  const out = document.getElementById("animeResults");
  if(!animeResults.length){ out.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">No results.</div>'; return; }
  out.innerHTML = animeResults.map((r, i) => {
    const s = r.seeders || "?";
    const l = r.leechers || "?";
    const sz = r.size || "?";
    const res = r.resolution ? `<span class="badge accent">${r.resolution}</span>` : "";
    const magnet = r.magnet ? `<button class="btn primary small" onclick="addAnimeMagnet(${i})"><span class="micon">add</span></button>` : "";
    const torrent = r.torrent ? `<a class="btn small" href="${r.torrent}" target="_blank">.TORRENT</a>` : "";
    const cover = r.metadata?.cover_url ? `<div style="margin-bottom:8px;"><img src="${r.metadata.cover_url}" style="max-height:120px; border:1px solid var(--border);" alt="cover"></div>` : "";
    return `
    <div class="result-card">
      ${cover}
      <div class="result-title">${esc(r.title)}</div>
      <div class="result-meta">
        <span><span class="micon" style="font-size:11px;">trending_up</span> ${s}</span>
        <span><span class="micon" style="font-size:11px;">trending_down</span> ${l}</span>
        <span><span class="micon" style="font-size:11px;">save</span> ${sz}</span>
        <span>${esc(r.provider)}</span>
        ${res}
      </div>
      <div class="result-actions">
        ${magnet}
        ${torrent}
        <a class="btn small" href="${esc(r.page)}" target="_blank"><span class="micon">open_in_new</span> PAGE</a>
      </div>
    </div>`;
  }).join("");
}

async function addAnimeMagnet(index){
  const r = animeResults[index];
  if(!r || !r.magnet) return;
  try{
    const body = new URLSearchParams();
    body.append("magnet", r.magnet);
    body.append("category", "anime");
    body.append("media_type", "anime");
    const res = await fetch("/api/torrent/add", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
    const data = await res.json();
    if(data.success){ toast("Anime magnet added", "success"); addLog(`Added: ${r.title.substring(0, 60)}`); }
    else toast("Server rejected", "warn");
  } catch(e){ toast("Failed to add", "error"); }
}

// ── Torrents Tab ──
function renderTorrents(list){
  const el = document.getElementById("torrent-list");
  const dashDown = document.getElementById("dash-down");
  const dashUp = document.getElementById("dash-up");
  const dashBar = document.getElementById("dash-down-bar");
  const statActive = document.getElementById("stat-active");
  const statDone = document.getElementById("stat-done");
  const qbBadge = document.getElementById("qb-badge");
  const vpnBadge = document.getElementById("vpn-badge");
  const cfBadge = document.getElementById("cf-badge");

  if(!el) return;
  if(!list.length){ el.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">No torrents.</div>'; }
  else{
    el.innerHTML = list.map((t) => {
      const pct = t.progress || 0;
      const state = (t.state || "").toUpperCase();
      const color = pct >= 100 ? "var(--ok)" : pct > 0 ? "var(--accent)" : "var(--warn)";
      const speed = t.speed_down > 0 ? `${(t.speed_down/1024/1024).toFixed(1)} MB/s` : "";
      return `
      <div class="torrent-item">
        <div class="name">${esc(t.name || "?")}</div>
        <div class="meta" style="min-width:180px;">
          <span style="color:${color}">${state}</span> ${speed}
        </div>
        <div class="progress-bar" style="width:120px; margin-right:8px;"><div class="progress-fill" style="width:${pct}%; background:${color};"></div></div>
        <div class="meta" style="min-width:60px; text-align:right;">${pct}%</div>
        <div class="actions">
          <button class="btn small" onclick="torrentAction('pause','${t.hash}')"><span class="micon">pause</span></button>
          <button class="btn small" onclick="torrentAction('resume','${t.hash}')"><span class="micon">play_arrow</span></button>
          <button class="btn small danger" onclick="torrentAction('delete','${t.hash}')"><span class="micon">delete</span></button>
        </div>
      </div>`;
    }).join("");
  }

  let totalDown=0,totalUp=0,active=0,done=0,totalRatio=0;
  list.forEach((t) => {
    totalDown += t.speed_down || 0;
    totalUp += t.speed_up || 0;
    if(t.progress>0 && t.progress<100) active++;
    if(t.progress>=100) done++;
    totalRatio += t.ratio || 0;
  });
  if(dashDown) dashDown.textContent = (totalDown/1024/1024).toFixed(1);
  if(dashUp) dashUp.textContent = (totalUp/1024/1024).toFixed(1);
  if(dashBar) dashBar.style.width = Math.min((totalDown/1024/1024/50)*100,100)+"%";
  if(statActive) statActive.textContent = active;
  if(statDone) statDone.textContent = done;
  if(qbBadge) qbBadge.style.display = list.length ? "inline-block" : "none";

  const status = document.getElementById("dash-status");
  if(status) status.innerHTML = `Torrents: <strong>${list.length}</strong> active<br>Down: <strong>${(totalDown/1024/1024).toFixed(1)}</strong> MB/s<br>Up: <strong>${(totalUp/1024/1024).toFixed(1)}</strong> MB/s`;

  // Check VPN status
  checkVpnStatus();
  checkCfStatus();
}

async function checkVpnStatus(){
  try{
    const r = await fetch("/api/vpn/status");
    const d = await r.json();
    const badge = document.getElementById("vpn-badge");
    const vpnStatus = document.getElementById("vpn-status");
    if(d.enabled === false){
      if(badge) badge.style.display = "none";
      if(vpnStatus) vpnStatus.textContent = "VPN not configured";
    } else if(d.connected){
      if(badge){ badge.style.display = "inline-block"; badge.textContent = "VPN"; badge.style.borderColor = "var(--ok)"; badge.style.color = "var(--ok)"; }
      if(vpnStatus) vpnStatus.textContent = `VPN: ${d.location || "connected"} (${d.ip || "?"})`;
    } else {
      if(badge){ badge.style.display = "inline-block"; badge.textContent = "VPN"; badge.style.borderColor = "var(--warn)"; badge.style.color = "var(--warn)"; }
      if(vpnStatus) vpnStatus.textContent = "VPN disconnected";
    }
  } catch(e){}
}

async function checkCfStatus(){
  try{
    const r = await fetch("/api/cloudflare/status");
    const d = await r.json();
    const badge = document.getElementById("cf-badge");
    if(d.enabled && d.installed){
      if(badge){ badge.style.display = "inline-block"; badge.textContent = "CF"; }
    } else {
      if(badge) badge.style.display = "none";
    }
  } catch(e){}
}

async function torrentAction(action, hash){
  try{
    const r = await fetch(`/api/torrent/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({ hash }),
    });
    const d = await r.json();
    if(d.success) toast(`${action.toUpperCase()} OK`, "success");
    else toast("Action failed", "error");
    socket.emit("request_torrents");
  } catch(e){ toast("Request failed", "error"); }
}

// ── File Browser ──
async function loadFiles(subpath="", root=currentFileRoot){
  currentFileRoot = root;
  currentFilePath = subpath;
  const el = document.getElementById("fileList");
  const crumbs = document.getElementById("fileCrumbs");
  el.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">Loading...</div>';
  try{
    const url = new URL("/api/files", location.origin);
    url.searchParams.set("root", root);
    if(subpath) url.searchParams.set("subpath", subpath);
    const r = await fetch(url);
    const data = await r.json();
    if(data.error) throw new Error(data.error);
    const parts = subpath.split("/").filter(Boolean);
    let bc = `<button class="btn small" onclick="loadFiles('','${root}')">${root.toUpperCase()}</button>`;
    let acc = "";
    parts.forEach((p) => { acc += (acc ? "/" : "") + p; bc += ` <span style="color:var(--text-3)">/</span> <button class="btn small" onclick="loadFiles('${acc}','${root}')">${esc(p)}</button>`; });
    crumbs.innerHTML = bc;
    if(!data.items.length){ el.innerHTML = '<div style="color:var(--text-3); font-size:11px; text-transform:uppercase;">Empty folder.</div>'; return; }
    el.innerHTML = data.items.map((it) => {
      const icon = it.is_dir ? "folder" : "insert_drive_file";
      const size = it.is_dir ? "" : hBytes(it.size);
      const onclick = it.is_dir ? `loadFiles('${(subpath ? subpath + "/" : "") + it.name}', '${root}')` : ``;
      const dl = !it.is_dir ? `<a class="btn small" href="/api/download?root=${root}&subpath=${encodeURIComponent(it.relative)}"><span class="micon">download</span></a>` : "";
      return `
      <div class="file-item" onclick="${onclick ? onclick : ''}">
        <span class="micon" style="font-size:14px; color:var(--text-3);">${icon}</span>
        <span class="name">${esc(it.name)}</span>
        <span class="size">${size}</span>
        ${dl}
      </div>`;
    }).join("");
  } catch(e){
    el.innerHTML = `<div style="color:var(--danger); font-size:11px; text-transform:uppercase;">ERROR: ${esc(e.message)}</div>`;
  }
}

function hBytes(n){
  if(!n) return "0 B";
  const k=1024; const s=["B","KB","MB","GB","TB"];
  const i=Math.floor(Math.log(n)/Math.log(k));
  return parseFloat((n/Math.pow(k,i)).toFixed(1))+" "+s[i];
}

// ── Upload ──
(function setupDragDrop(){
  const dz = document.getElementById("dropZone");
  if(!dz) return;
  ["dragenter","dragover","dragleave","drop"].forEach((ev) => {
    dz.addEventListener(ev, (e) => { e.preventDefault(); e.stopPropagation(); });
  });
  dz.addEventListener("dragenter", () => dz.classList.add("dragover"));
  dz.addEventListener("dragleave", () => dz.classList.remove("dragover"));
  dz.addEventListener("drop", (e) => {
    dz.classList.remove("dragover");
    for(const f of e.dataTransfer.files) uploadFile(f);
  });
  dz.addEventListener("click", () => document.getElementById("fileInput").click());
})();

function pickFiles(){
  const inp = document.getElementById("fileInput");
  if(!inp) return;
  inp.onchange = () => { for(const f of inp.files) uploadFile(f); inp.value = ""; };
  inp.click();
}

async function uploadFile(file){
  const dest = document.getElementById("uploadDest").value;
  const autoSort = document.getElementById("uploadSort").checked;
  const mediaType = document.getElementById("uploadMediaType").value;
  const status = document.getElementById("uploadStatus");
  status.textContent = `UPLOADING ${esc(file.name)}...`;
  try{
    const fd = new FormData();
    fd.append("file", file);
    fd.append("destination", dest);
    fd.append("sort", autoSort ? "true" : "false");
    fd.append("media_type", mediaType);
    const r = await fetch("/api/upload", { method: "POST", body: fd });
    const data = await r.json();
    if(data.success){
      toast(`UPLOADED: ${data.filename}`, "success");
      status.textContent = `DONE: ${data.filename}`;
      addLog(`Upload: ${data.filename}`);
    } else throw new Error(data.error || "Server rejected");
  } catch(e){
    toast(`UPLOAD FAILED: ${e.message}`, "error");
    status.textContent = "FAILED.";
  }
}

// ── URL Download ──
async function downloadUrl(){
  const url = document.getElementById("urlInput").value.trim();
  const category = document.getElementById("urlCategory").value;
  const status = document.getElementById("urlStatus");
  if(!url) return;
  status.textContent = "Starting download...";
  try{
    const body = new URLSearchParams();
    body.append("url", url);
    body.append("category", category);
    const r = await fetch("/api/download/url", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
    const data = await r.json();
    if(data.ok){
      toast(`Downloaded: ${data.filename}`, "success");
      status.textContent = `Done: ${data.filename}`;
      addLog(`URL download: ${data.filename}`);
    } else {
      toast(data.error || "Download failed", "error");
      status.textContent = data.error || "Failed";
    }
  } catch(e){
    toast(`Download failed: ${e.message}`, "error");
    status.textContent = "Failed.";
  }
}

// ── Remote ──
function startScreen(){
  fetch("/api/screen/start", { method: "POST" }).then(() => {
    screenActive = true;
    toast("Screen stream started", "success");
  }).catch((e) => toast("Screen start failed", "error"));
}
function stopScreen(){
  fetch("/api/screen/stop", { method: "POST" }).then(() => {
    screenActive = false;
    document.getElementById("screenView").src = "";
    toast("Screen stream stopped", "success");
  });
}
function toggleKeyboard(){
  const p = document.getElementById("keyboardPanel");
  p.style.display = p.style.display === "none" ? "block" : "none";
}
async function sendKeys(){
  const text = document.getElementById("kbInput").value;
  if(!text) return;
  try{
    await fetch("/api/remote/keyboard", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ text }) });
    toast("KEYS SENT", "success");
  } catch(e){ toast("Keyboard failed", "error"); }
}

// ── Settings ──
async function loadSettings(){
  try{
    const r = await fetch("/api/config");
    const cfg = await r.json();
    const set = (id, val) => { const el = document.getElementById(id); if(el) el.value = val !== undefined ? val : ""; };
    const chk = (id, val) => { const el = document.getElementById(id); if(el) el.checked = !!val; };

    set("cfgHost", cfg.server?.host);
    set("cfgPort", cfg.server?.port);
    chk("cfgDebug", cfg.server?.debug);
    chk("cfgVerbose", cfg.server?.verbose);
    set("cfgTv", cfg.paths?.tv);
    set("cfgMovies", cfg.paths?.movies);
    set("cfgAnime", cfg.paths?.anime);
    set("cfgMusic", cfg.paths?.music);
    set("cfgDownloads", cfg.paths?.downloads);
    set("cfgQbUrl", cfg.qbittorrent?.host);
    set("cfgQbUser", cfg.qbittorrent?.username);
    set("cfgQbPass", cfg.qbittorrent?.password ? "***" : "");
    chk("cfgQbEnabled", cfg.qbittorrent?.enabled);
    set("cfgTmdbKey", cfg.tmdb?.api_key ? "***" : "");
    set("cfgTvdbKey", cfg.tvdb?.api_key ? "***" : "");
    set("cfgDiscordHook", cfg.discord?.webhook_url ? "***" : "");
    chk("cfgScreen", cfg.screen_stream?.enabled);
    chk("cfgRemote", cfg.remote_control?.enabled);
    set("cfgFps", cfg.screen_stream?.fps);
    set("cfgQual", cfg.screen_stream?.quality);
    chk("cfgFFmpeg", cfg.ffmpeg?.enabled);
    set("cfgFFAudio", cfg.ffmpeg?.default_audio_lang);
    set("cfgFFSub", cfg.ffmpeg?.default_subtitle_lang);
    chk("cfgFFPost", cfg.ffmpeg?.post_process_downloads);
    chk("cfgVpnEnabled", cfg.vpn?.enabled);
    set("cfgVpnProvider", cfg.vpn?.provider);
    set("cfgVpnLocation", cfg.vpn?.location);
    chk("cfgCF", cfg.cloudflare_solver?.enabled);
  } catch(e){ toast("Could not load settings", "error"); }
}

async function saveSettings(){
  const payload = {};
  const val = (id) => { const el = document.getElementById(id); return el ? el.value : undefined; };
  const bool = (id) => { const el = document.getElementById(id); return el ? el.checked : false; };

  if(val("cfgHost") !== undefined) payload["server.host"] = val("cfgHost");
  if(val("cfgPort") !== undefined) payload["server.port"] = parseInt(val("cfgPort")) || 8080;
  payload["server.debug"] = bool("cfgDebug");
  payload["server.verbose"] = bool("cfgVerbose");
  if(val("cfgTv") !== undefined) payload["paths.tv"] = val("cfgTv");
  if(val("cfgMovies") !== undefined) payload["paths.movies"] = val("cfgMovies");
  if(val("cfgAnime") !== undefined) payload["paths.anime"] = val("cfgAnime");
  if(val("cfgMusic") !== undefined) payload["paths.music"] = val("cfgMusic");
  if(val("cfgDownloads") !== undefined) payload["paths.downloads"] = val("cfgDownloads");
  if(val("cfgQbUrl") !== undefined) payload["qbittorrent.host"] = val("cfgQbUrl");
  if(val("cfgQbUser") !== undefined) payload["qbittorrent.username"] = val("cfgQbUser");
  if(val("cfgQbPass") && val("cfgQbPass") !== "***") payload["qbittorrent.password"] = val("cfgQbPass");
  payload["qbittorrent.enabled"] = bool("cfgQbEnabled");
  if(val("cfgTmdbKey") && val("cfgTmdbKey") !== "***") payload["tmdb.api_key"] = val("cfgTmdbKey");
  if(val("cfgTvdbKey") && val("cfgTvdbKey") !== "***") payload["tvdb.api_key"] = val("cfgTvdbKey");
  if(val("cfgDiscordHook") && val("cfgDiscordHook") !== "***") payload["discord.webhook_url"] = val("cfgDiscordHook");
  payload["screen_stream.enabled"] = bool("cfgScreen");
  payload["remote_control.enabled"] = bool("cfgRemote");
  if(val("cfgFps") !== undefined) payload["screen_stream.fps"] = parseInt(val("cfgFps")) || 10;
  if(val("cfgQual") !== undefined) payload["screen_stream.quality"] = parseInt(val("cfgQual")) || 55;
  payload["ffmpeg.enabled"] = bool("cfgFFmpeg");
  if(val("cfgFFAudio") !== undefined) payload["ffmpeg.default_audio_lang"] = val("cfgFFAudio");
  if(val("cfgFFSub") !== undefined) payload["ffmpeg.default_subtitle_lang"] = val("cfgFFSub");
  payload["ffmpeg.post_process_downloads"] = bool("cfgFFPost");
  payload["vpn.enabled"] = bool("cfgVpnEnabled");
  if(val("cfgVpnProvider") !== undefined) payload["vpn.provider"] = val("cfgVpnProvider");
  if(val("cfgVpnLocation") !== undefined) payload["vpn.location"] = val("cfgVpnLocation");
  payload["cloudflare_solver.enabled"] = bool("cfgCF");

  try{
    const r = await fetch("/api/config", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    if(r.ok){ toast("Settings saved", "success"); addLog("Settings updated"); }
    else throw new Error("HTTP " + r.status);
  } catch(e){ toast("Save failed: " + e.message, "error"); }
}

// ── Utilities ──
function esc(str){
  if(str == null) return "";
  return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function toast(msg, type="info"){
  const c = document.getElementById("toast-container");
  if(!c) return;
  const t = document.createElement("div");
  t.className = "toast " + (type==="error"?"error":type==="success"?"success":type==="warn"?"warn":"");
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// Expose
window.showTab = showTab;
window.doSearch = doSearch;
window.addMagnet = addMagnet;
window.toggleBatch = toggleBatch;
window.clearBatch = clearBatch;
window.addBatchSelected = addBatchSelected;
window.doAnimeSearch = doAnimeSearch;
window.addAnimeMagnet = addAnimeMagnet;
window.loadFiles = loadFiles;
window.pickFiles = pickFiles;
window.uploadFile = uploadFile;
window.downloadUrl = downloadUrl;
window.startScreen = startScreen;
window.stopScreen = stopScreen;
window.toggleKeyboard = toggleKeyboard;
window.sendKeys = sendKeys;
window.torrentAction = torrentAction;
window.loadSettings = loadSettings;
window.saveSettings = saveSettings;

// Init
document.addEventListener("DOMContentLoaded", () => {
  showTab("dashboard");
  loadSettings();
  loadProviders();
  checkVpnStatus();
  checkCfStatus();
});
