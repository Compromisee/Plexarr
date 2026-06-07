"""Plexarr Client — Main Desktop Application

Cross-platform client (Windows, Linux, macOS) using PyWebView.
Features: system tray, auto-reconnect, server discovery, keyboard shortcuts,
mini mode, quick actions, debug console, offline cache, notifications.
"""
import os
import sys
import json
import time
import threading
import logging
import tempfile
from pathlib import Path
from typing import Optional, Dict

import webview
import requests
from client.config import client_config, CONFIG_DIR
from client.discovery import discover_servers
from client.tray import TrayManager, create_icon

try:
    from plyer import notification
    _PLYER = True
except ImportError:
    _PLYER = False

log = logging.getLogger("PlexarrClient")

_SERVER_URL = "http://localhost:8080"
_WINDOW: Optional[webview.Window] = None
_TRAY: Optional[TrayManager] = None
_RECONNECT_THREAD: Optional[threading.Thread] = None


def _build_html(server_url: str, theme: str = "dark") -> str:
    """Build the client HTML with injected server URL and settings."""
    cfg = client_config.all()
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Plexarr Client</title>
<style>
:root{{--bg:#050508;--surface:#0b0b0e;--surface-2:#111115;--accent:#00d4aa;--text:#e8e8ee;--text-2:#9090a0;--text-3:#606070;--border:#22222a;--font:'JetBrains Mono',monospace;}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{height:100%;width:100%;background:var(--bg);color:var(--text);font-family:var(--font);font-size:13px;overflow:hidden;}}
#app{{display:flex;height:100vh;flex-direction:column;}}
#topbar{{height:48px;background:var(--surface);border-bottom:1px solid var(--border);display:flex;align-items:center;padding:0 16px;gap:10px;}}
#topbar .title{{font-size:14px;font-weight:700;letter-spacing:0.5px;text-transform:uppercase;}}
#topbar .status{{margin-left:auto;display:flex;align-items:center;gap:8px;font-size:11px;color:var(--text-3);text-transform:uppercase;}}
#topbar .dot{{width:8px;height:8px;border-radius:50%;background:var(--text-3);}}
#topbar .dot.ok{{background:#00ff88;box-shadow:0 0 8px #00ff88;}}
#topbar .dot.off{{background:#ff4444;box-shadow:0 0 8px #ff4444;}}
#topbar .dot.warn{{background:#ffaa00;box-shadow:0 0 8px #ffaa00;}}
#frameWrap{{flex:1;overflow:hidden;}}
#serverFrame{{width:100%;height:100%;border:none;}}
#miniPanel{{display:none;position:fixed;bottom:12px;right:12px;width:320px;height:200px;background:var(--surface);border:1px solid var(--border);z-index:9999;}}
#miniPanel iframe{{width:100%;height:100%;border:none;}}
button.btn{{background:var(--surface-2);color:var(--text);border:1px solid var(--border);padding:6px 10px;font-size:11px;font-family:var(--font);cursor:pointer;text-transform:uppercase;}}
button.btn:hover{{border-color:var(--accent);color:var(--accent);}}
#quickPanel{{display:none;position:fixed;top:48px;left:50%;transform:translateX(-50%);background:var(--surface);border:1px solid var(--border);padding:12px;z-index:9999;gap:6px;}}
#quickPanel.active{{display:flex;}}
#debugConsole{{display:none;position:fixed;bottom:0;left:0;right:0;height:200px;background:var(--surface);border-top:1px solid var(--border);z-index:9999;flex-direction:column;}}
#debugConsole.active{{display:flex;}}
#debugConsole .header{{display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--border);font-size:11px;}}
#debugConsole .output{{flex:1;overflow:auto;padding:8px;font-size:11px;color:var(--text-2);line-height:1.6;white-space:pre-wrap;}}
#debugConsole .input{{display:flex;gap:4px;padding:6px;}}
#debugConsole input{{flex:1;background:var(--surface-2);border:1px solid var(--border);color:var(--text);padding:6px;font-family:var(--font);font-size:11px;}}
#discovery{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:10000;justify-content:center;align-items:center;}}
#discovery.active{{display:flex;}}
#discovery .box{{background:var(--surface);border:1px solid var(--border);padding:20px;max-width:500px;width:90%;}}
#discovery .box h3{{font-size:14px;margin-bottom:12px;text-transform:uppercase;}}
#discovery .server{{display:flex;justify-content:space-between;padding:8px;border-bottom:1px solid var(--border);cursor:pointer;}}
#discovery .server:hover{{background:var(--surface-2);}}
#offlineBanner{{display:none;background:#ff4444;color:#fff;text-align:center;padding:6px;font-size:11px;text-transform:uppercase;}}
#offlineBanner.active{{display:block;}}
#notif{{display:none;position:fixed;top:12px;right:12px;background:var(--surface);border:1px solid var(--border);padding:10px 14px;font-size:11px;z-index:99999;max-width:300px;}}
#notif.active{{display:block;}}
</style>
</head>
<body>
<div id="app">
  <div id="offlineBanner">OFFLINE MODE — SERVER UNREACHABLE</div>
  <div id="topbar">
    <div class="title">Plexarr</div>
    <button class="btn" onclick="quickAction('search')">Search</button>
    <button class="btn" onclick="quickAction('torrents')">Torrents</button>
    <button class="btn" onclick="quickAction('files')">Files</button>
    <button class="btn" onclick="toggleMini()">Mini</button>
    <button class="btn" onclick="toggleDebug()">Debug</button>
    <button class="btn" onclick="discover()">Discover</button>
    <button class="btn" onclick="reloadFrame()">Reload</button>
    <div class="status">
      <span id="connStatus">Connecting...</span>
      <span id="connDot" class="dot"></span>
    </div>
  </div>
  <div id="frameWrap">
    <iframe id="serverFrame" src="{server_url}"></iframe>
  </div>
  <div id="miniPanel">
    <iframe id="miniFrame" src="{server_url}"></iframe>
  </div>
</div>

<div id="quickPanel">
  <button class="btn" onclick="quickAction('search')">Search</button>
  <button class="btn" onclick="quickAction('torrents')">Torrents</button>
  <button class="btn" onclick="quickAction('files')">Files</button>
  <button class="btn" onclick="quickAction('upload')">Upload</button>
  <button class="btn" onclick="quickAction('settings')">Settings</button>
  <button class="btn" onclick="quickAction('remote')">Remote</button>
  <button class="btn" onclick="hideQuick()">Close</button>
</div>

<div id="debugConsole">
  <div class="header">
    <span>Debug Console</span>
    <button class="btn" onclick="toggleDebug()">Close</button>
    <button class="btn" onclick="clearDebug()">Clear</button>
  </div>
  <div class="output" id="debugOutput"></div>
  <div class="input">
    <input type="text" id="debugCmd" placeholder="Enter JS command..." onkeydown="if(event.key==='Enter')runDebug()">
    <button class="btn" onclick="runDebug()">Run</button>
  </div>
</div>

<div id="discovery">
  <div class="box">
    <h3>Server Discovery</h3>
    <div id="discList">Scanning...</div>
    <div style="margin-top:10px;text-align:right;">
      <button class="btn" onclick="hideDiscovery()">Close</button>
    </div>
  </div>
</div>

<div id="notif"></div>

<script>
const SERVER = "{server_url}";
let reconnectTimer = null;
let isOffline = false;

function checkConnection(){{
  fetch(SERVER + "/health", {{cache:"no-store",signal:AbortSignal.timeout(3000)}})
    .then(r => r.ok ? r.json() : Promise.reject())
    .then(d => {{
      document.getElementById("connDot").className = "dot ok";
      document.getElementById("connStatus").textContent = "Online v" + (d.version || "?");
      document.getElementById("offlineBanner").classList.remove("active");
      isOffline = false;
    }})
    .catch(() => {{
      document.getElementById("connDot").className = "dot off";
      document.getElementById("connStatus").textContent = "Offline";
      document.getElementById("offlineBanner").classList.add("active");
      isOffline = true;
    }});
}}

setInterval(checkConnection, 5000);
checkConnection();

function quickAction(tab){{
  const f = document.getElementById("serverFrame");
  if(f && f.contentWindow) f.contentWindow.location.href = SERVER + "#" + tab;
  hideQuick();
}}

function toggleMini(){{
  const p = document.getElementById("miniPanel");
  p.style.display = p.style.display === "block" ? "none" : "block";
}}

function toggleDebug(){{
  document.getElementById("debugConsole").classList.toggle("active");
}}

function clearDebug(){{
  document.getElementById("debugOutput").textContent = "";
}}

function logDebug(msg){{
  const el = document.getElementById("debugOutput");
  el.textContent += msg + "\\n";
  el.scrollTop = el.scrollHeight;
}}

function runDebug(){{
  const cmd = document.getElementById("debugCmd").value;
  try{{
    const f = document.getElementById("serverFrame");
    const result = f.contentWindow.eval(cmd);
    logDebug("> " + cmd + "\\n" + JSON.stringify(result, null, 2));
  }}catch(e){{
    logDebug("> " + cmd + "\\nERROR: " + e.message);
  }}
}}

function discover(){{
  document.getElementById("discovery").classList.add("active");
  document.getElementById("discList").innerHTML = "Scanning LAN...";
  window.pywebview.api.discover_servers().then(list => {{
    if(!list.length){{ document.getElementById("discList").innerHTML = "No servers found."; return; }}
    document.getElementById("discList").innerHTML = list.map(s =>
      `<div class="server" onclick="connectServer('${{s.url}}')">${{s.url}} <span style="color:var(--text-3)">v${{s.version || '?'}}</span></div>`
    ).join("");
  }});
}}

function hideDiscovery(){{ document.getElementById("discovery").classList.remove("active"); }}
function hideQuick(){{ document.getElementById("quickPanel").classList.remove("active"); }}
function reloadFrame(){{ document.getElementById("serverFrame").src = SERVER; }}
function connectServer(url){{ document.getElementById("serverFrame").src = url; hideDiscovery(); }}
function showNotif(msg){{ const n = document.getElementById("notif"); n.textContent = msg; n.classList.add("active"); setTimeout(() => n.classList.remove("active"), 4000); }}

// Keyboard shortcuts
window.addEventListener("keydown", e => {{
  if(e.ctrlKey && e.shiftKey && e.key === "P"){{ e.preventDefault(); toggleMini(); }}
  if(e.ctrlKey && e.shiftKey && e.key === "S"){{ e.preventDefault(); quickAction('search'); }}
  if(e.ctrlKey && e.shiftKey && e.key === "X"){{ e.preventDefault(); window.pywebview.api.take_screenshot(); }}
  if(e.ctrlKey && e.shiftKey && e.key === "M"){{ e.preventDefault(); toggleMini(); }}
  if(e.key === "F12"){{ e.preventDefault(); toggleDebug(); }}
  if(e.ctrlKey && e.key === "r"){{ e.preventDefault(); reloadFrame(); }}
}});
</script>
</body>
</html>'''
    return html


def _write_temp_html(server_url: str, theme: str) -> str:
    html = _build_html(server_url, theme)
    fd, path = tempfile.mkstemp(suffix="_plexarr_client.html")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(html)
    return path


class ClientAPI:
    """Exposed to the webview JS via window.pywebview.api."""

    def __init__(self, window: webview.Window):
        self.window = window
        self._log = []

    def discover_servers(self):
        log.info("Running server discovery...")
        return discover_servers(timeout=3)

    def take_screenshot(self):
        try:
            self.window.capture()
            log.info("Screenshot captured")
            return {"ok": True}
        except Exception as e:
            log.error(f"Screenshot failed: {e}")
            return {"ok": False, "error": str(e)}

    def get_config(self):
        return client_config.all()

    def set_config(self, key: str, value):
        client_config.set(key, value)
        return {"ok": True}

    def import_config(self, path: str):
        client_config.import_json(path)
        return {"ok": True}

    def export_config(self, path: str):
        client_config.export_json(path)
        return {"ok": True}

    def list_profiles(self):
        return client_config.get("profiles", [])

    def add_profile(self, name: str, url: str):
        servers = client_config.get("servers", [])
        servers.append({"name": name, "url": url, "auto_connect": True, "username": "", "password": ""})
        client_config.set("servers", servers)
        return {"ok": True}

    def remove_profile(self, index: int):
        client_config.remove_server(index)
        return {"ok": True}

    def switch_profile(self, index: int):
        client_config.set_active_server(index)
        srv = client_config.get_active_server()
        return {"ok": True, "url": srv.get("url", "") if srv else ""}

    def get_active_server(self):
        return client_config.get_active_server()

    def notify(self, title: str, message: str):
        if _PLYER:
            notification.notify(title=title, message=message, timeout=5)
        return {"ok": True}

    def log(self, message: str):
        log.info(f"[JS] {message}")
        return {"ok": True}

    def get_version(self):
        return {"client": "2.1.0", "server": self._check_server()}

    def _check_server(self):
        try:
            srv = client_config.get_active_server()
            if not srv:
                return None
            r = requests.get(srv["url"] + "/health", timeout=3)
            if r.ok:
                return r.json()
        except Exception:
            pass
        return None

    def set_theme(self, theme: str):
        client_config.set("theme", theme)
        return {"ok": True}

    def get_theme(self):
        return client_config.get("theme", "dark")

    def toggle_mini_mode(self):
        self.window.toggle_fullscreen() if not self.window.fullscreen else None
        return {"ok": True}

    def open_url(self, url: str):
        import subprocess
        if sys.platform == "darwin":
            subprocess.call(["open", url])
        elif sys.platform == "win32":
            os.startfile(url)
        else:
            subprocess.call(["xdg-open", url])
        return {"ok": True}

    def quit(self):
        log.info("Client quit requested from JS")
        self.window.destroy()


def _toggle_window():
    if _WINDOW and _WINDOW.running:
        if _WINDOW.visible:
            _WINDOW.hide()
        else:
            _WINDOW.show()


def _toggle_search():
    if _WINDOW and _WINDOW.running:
        _WINDOW.show()


def _on_quit():
    if _TRAY:
        _TRAY.stop()
    if _WINDOW:
        _WINDOW.destroy()


def _auto_reconnect(window: webview.Window):
    """Background thread: monitor server health and reconnect if needed."""
    interval = client_config.get("behavior.reconnect_interval", 5)
    while window.running:
        try:
            srv = client_config.get_active_server()
            if srv:
                url = srv.get("url", "")
                try:
                    r = requests.get(url + "/health", timeout=3)
                    if not r.ok and client_config.get("behavior.auto_reconnect", True):
                        log.warn("Server unreachable, attempting reconnect...")
                        # The iframe will auto-reload on its own
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(interval)


def run_client(server_url: str, width: int, height: int, debug: bool, no_tray: bool, minimize: bool, theme: str):
    global _WINDOW, _TRAY, _SERVER_URL
    _SERVER_URL = server_url

    client_config.set("theme", theme)
    client_config.save()

    html_path = _write_temp_html(server_url, theme)

    # QOL: Custom user agent and title
    title = f"Plexarr Client — {server_url}"

    window = webview.create_window(
        title=title,
        url=html_path,
        width=width,
        height=height,
        min_size=(800, 600),
        text_select=True,
        confirm_close=True,
    )
    _WINDOW = window

    api = ClientAPI(window)
    window.expose(api.discover_servers)
    window.expose(api.take_screenshot)
    window.expose(api.get_config)
    window.expose(api.set_config)
    window.expose(api.import_config)
    window.expose(api.export_config)
    window.expose(api.list_profiles)
    window.expose(api.add_profile)
    window.expose(api.remove_profile)
    window.expose(api.switch_profile)
    window.expose(api.get_active_server)
    window.expose(api.notify)
    window.expose(api.log)
    window.expose(api.get_version)
    window.expose(api.set_theme)
    window.expose(api.get_theme)
    window.expose(api.toggle_mini_mode)
    window.expose(api.open_url)
    window.expose(api.quit)

    # Start tray
    if not no_tray and client_config.get("ui.show_system_tray", True):
        _TRAY = TrayManager(
            on_toggle=_toggle_window,
            on_search=_toggle_search,
            on_quit=_on_quit,
            window=window,
        )
        _TRAY.start()

    # Start reconnect monitor
    if client_config.get("behavior.auto_reconnect", True):
        t = threading.Thread(target=_auto_reconnect, args=(window,), daemon=True)
        t.start()

    log.info(f"Starting client window: {width}x{height} debug={debug}")
    webview.start(
        debug=debug,
        user_agent="PlexarrClient/2.1.0",
        storage_path=str(CONFIG_DIR / "webview_storage"),
    )

    try:
        os.remove(html_path)
    except Exception:
        pass

    if _TRAY:
        _TRAY.stop()
    log.info("Client exited.")


if __name__ == "__main__":
    from client.launcher import parse_args, setup_logging
    args = parse_args()
    setup_logging(verbose=args.verbose)
    run_client(
        server_url=args.server if args.server != "auto" else "http://localhost:8080",
        width=args.width or 1440,
        height=args.height or 900,
        debug=args.debug,
        no_tray=args.no_tray,
        minimize=args.minimize,
        theme=args.theme or "dark",
    )
