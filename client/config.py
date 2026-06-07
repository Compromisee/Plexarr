"""Plexarr Client — Configuration Manager"""
import json
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
from copy import deepcopy

APP_NAME = "PlexarrClient"
CONFIG_DIR = Path.home() / ".config" / "plexarr"
if os.name == "nt":
    CONFIG_DIR = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")) / "Plexarr"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_PATH = CONFIG_DIR / "client.json"

DEFAULT_CONFIG = {
    "servers": [
        {
            "name": "Default",
            "url": "http://localhost:8080",
            "auto_connect": True,
            "username": "",
            "password": "",
        }
    ],
    "active_server": 0,
    "theme": "dark",
    "ui": {
        "window_width": 1440,
        "window_height": 900,
        "minimize_to_tray": True,
        "start_minimized": False,
        "show_system_tray": True,
        "enable_sounds": True,
        "notification_duration": 5,
    },
    "behavior": {
        "auto_reconnect": True,
        "reconnect_interval": 5,
        "auto_discovery": True,
        "discovery_timeout": 3,
        "cache_enabled": True,
        "cache_ttl": 300,
        "offline_mode": False,
    },
    "shortcuts": {
        "toggle_window": "Ctrl+Shift+P",
        "quick_search": "Ctrl+Shift+S",
        "screenshot": "Ctrl+Shift+X",
        "mini_mode": "Ctrl+Shift+M",
        "reload": "Ctrl+R",
        "dev_tools": "F12",
    },
    "debug": {
        "verbose": False,
        "log_file": str(CONFIG_DIR / "client.log"),
        "max_log_size_mb": 10,
        "log_level": "INFO",
        "show_console": False,
        "remote_debug": False,
    },
    "profiles": [],
    "updates": {
        "check_on_startup": True,
        "channel": "stable",
        "auto_download": False,
    },
    "portable": False,
}

class ClientConfig:
    def __init__(self):
        self._data = deepcopy(DEFAULT_CONFIG)
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    self._deep_update(self._data, loaded)
            except Exception as e:
                print(f"[Config] Load failed: {e}")
                self.save()
        else:
            self.save()

    def save(self):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[Config] Save failed: {e}")

    def _deep_update(self, d, u):
        for k, v in u.items():
            if isinstance(v, dict) and k in d and isinstance(d[k], dict):
                d[k] = self._deep_update(d[k], v)
            else:
                d[k] = v
        return d

    def get(self, key: str, default=None):
        keys = key.split(".")
        val = self._data
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

    def set(self, key: str, value):
        keys = key.split(".")
        d = self._data
        for k in keys[:-1]:
            d = d.setdefault(k, {})
        d[keys[-1]] = value
        self.save()

    def all(self) -> Dict:
        return deepcopy(self._data)

    def add_server(self, name: str, url: str, auto_connect: bool = True):
        servers = self._data.get("servers", [])
        servers.append({"name": name, "url": url, "auto_connect": auto_connect, "username": "", "password": ""})
        self._data["servers"] = servers
        self.save()

    def remove_server(self, index: int):
        servers = self._data.get("servers", [])
        if 0 <= index < len(servers):
            servers.pop(index)
            if self._data.get("active_server", 0) >= len(servers) and servers:
                self._data["active_server"] = len(servers) - 1
            self.save()

    def get_active_server(self) -> Optional[Dict]:
        servers = self._data.get("servers", [])
        idx = self._data.get("active_server", 0)
        if 0 <= idx < len(servers):
            return servers[idx]
        return None

    def set_active_server(self, index: int):
        servers = self._data.get("servers", [])
        if 0 <= index < len(servers):
            self._data["active_server"] = index
            self.save()

    def import_json(self, path: str):
        with open(path, "r", encoding="utf-8") as f:
            self._data = json.load(f)
        self.save()

    def export_json(self, path: str):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)


client_config = ClientConfig()
