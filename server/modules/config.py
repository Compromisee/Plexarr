"""Plexarr V2 — Configuration Manager"""
import json
import os
from pathlib import Path
from copy import deepcopy

CONFIG_PATH = Path("config.json")

DEFAULT_CONFIG = {
    "server": {
        "host": "0.0.0.0",
        "port": 8080,
        "debug": False,
        "verbose": False,
        "secret_key": "change-me-plexarr-v2-secret-key"
    },
    "paths": {
        "tv": "/media/plex/TV Shows",
        "movies": "/media/plex/Movies",
        "anime": "/media/plex/Anime",
        "music": "/media/plex/Music",
        "downloads": "/media/plex/Downloads"
    },
    "plex": {
        "url": "http://localhost:32400",
        "token": "",
        "library_sections": [],
        "auto_scan": True
    },
    "qbittorrent": {
        "host": "http://localhost:8080",
        "username": "admin",
        "password": "adminadmin",
        "enabled": True,
        "categories_map": {
            "tv": "tv-plex",
            "movies": "movies-plex",
            "anime": "anime-plex",
            "music": "music-plex"
        }
    },
    "tmdb": {
        "api_key": "",
        "language": "en-US",
        "enabled": True,
        "fetch_cover_art": True,
        "fetch_backdrops": True
    },
    "jikan": {
        "enabled": True,
        "base_url": "https://api.jikan.moe/v4",
        "fetch_cover_art": True
    },
    "tvdb": {
        "api_key": "",
        "enabled": False
    },
    "cors_proxy": {
        "enabled": True,
        "timeout": 30
    },
    "cloudflare_solver": {
        "enabled": False,
        "provider": "cloudscraper",
        "sites": ["1337x.to", "rarbg.to", "torrentgalaxy.to"],
        "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    },
    "vpn": {
        "enabled": False,
        "provider": "windscribe",
        "cli_path": "/usr/bin/windscribe",
        "username": "",
        "password": "",
        "auto_connect": True,
        "location": "best",
        "kill_switch": False
    },
    "url_downloader": {
        "enabled": True,
        "rapidgator": {
            "enabled": False,
            "premium": False,
            "username": "",
            "password": "",
            "api_key": "",
            "parallel": 4
        },
        "generic": {
            "enabled": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "chunk_size": 8192,
            "max_retries": 3
        }
    },
    "ffmpeg": {
        "enabled": True,
        "path": "ffmpeg",
        "default_audio_lang": "eng",
        "default_subtitle_lang": "eng",
        "auto_set_defaults": True,
        "strip_unwanted_langs": False,
        "wanted_langs": ["eng", "jpn"],
        "post_process_downloads": True
    },
    "naming": {
        "variations": [
            "MediaHub",
            "Pahe",
            "HorribleSubs",
            "Erai-raws",
            "SubsPlease",
            "Judas",
            "YTS",
            "RARBG",
            "YIFY",
            "WEB-DL",
            "BluRay",
            "x264",
            "x265"
        ],
        "auto_detect_variations": True
    },
    "batch_download": {
        "enabled": True,
        "max_queue": 50,
        "auto_start": True
    },
    "watch_folder": {
        "enabled": False,
        "dir": "",
        "interval": 5,
        "auto_start": True,
        "delete_empty_dirs": True
    },
    "screen_stream": {
        "enabled": False,
        "fps": 10,
        "quality": 55,
        "scale": 0.7
    },
    "remote_control": {
        "enabled": False,
        "require_password": True,
        "password": "plexarr"
    },
    "auto_sort": {
        "enabled": True,
        "prefer_anime": True,
        "delete_empty_dirs": True
    },
    "uploads": {
        "max_size_mb": 5000,
        "allowed_extensions": [
            ".mkv", ".mp4", ".avi", ".mov", ".ts", ".m2ts",
            ".mp3", ".flac", ".aac", ".ogg", ".wav", ".m4a", ".opus",
            ".jpg", ".png", ".srt", ".ass", ".nfo", ".txt", ".zip", ".rar"
        ]
    },
    "discord": {
        "webhook_url": "",
        "webhook_enabled": True,
        "notifications": {
            "torrent_added": True,
            "torrent_completed": True,
            "torrent_error": True,
            "upload_complete": True,
            "download_completed": True,
            "ffmpeg_complete": True,
            "plex_scan": False
        }
    },
    "overseerr": {
        "enabled": False,
        "url": "http://localhost:5055",
        "api_key": ""
    },
    "tautulli": {
        "enabled": False,
        "url": "http://localhost:8181",
        "api_key": ""
    },
    "prometheus": {
        "enabled": True,
        "port": 9090
    },
    "grafana": {
        "enabled": True,
        "dashboard_uid": "plexarr-v2"
    },
    "sabnzbd": {
        "enabled": False,
        "host": "http://localhost:8080",
        "api_key": "",
        "categories_map": {
            "tv": "tv",
            "movies": "movies",
            "anime": "anime",
            "music": "music"
        }
    },
    "nzbgeek": {
        "enabled": False,
        "api_key": ""
    }
}


class ConfigManager:
    def __init__(self):
        self._data = deepcopy(DEFAULT_CONFIG)
        if CONFIG_PATH.exists():
            self.load()
        else:
            self.save()

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                self._deep_update(self._data, loaded)
        except Exception as e:
            print(f"[Config] Load failed: {e}. Using defaults.")
            self.save()

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)

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

    def all(self):
        return deepcopy(self._data)

    def update(self, payload: dict):
        self._deep_update(self._data, payload)
        self.save()

    def ensure_dirs(self):
        for p in self._data.get("paths", {}).values():
            Path(p).mkdir(parents=True, exist_ok=True)


config = ConfigManager()
