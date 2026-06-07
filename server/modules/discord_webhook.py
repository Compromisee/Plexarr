"""Plexarr — Discord Webhook Notifications & Status"""
import json
import requests
from datetime import datetime
from typing import Dict, Optional
from modules.config import config
from modules.logger import log


def _is_enabled() -> bool:
    return bool(config.get("discord.webhook_enabled", False)) and bool(config.get("discord.webhook_url", ""))


def _send(payload: Dict) -> bool:
    if not _is_enabled():
        return False
    url = config.get("discord.webhook_url", "")
    try:
        resp = requests.post(
            url,
            data=json.dumps(payload),
            headers={"Content-Type": "application/json"},
            timeout=15,
        )
        return resp.status_code in (200, 204)
    except Exception as e:
        log.error(f"Discord webhook send failed: {e}")
        return False


def notify_torrent_added(name: str, magnet: str = "", category: str = "", size: str = ""):
    if not config.get("discord.notifications.torrent_added", True):
        return
    embed = {
        "title": "[+] Torrent Added",
        "description": f"**{name}**",
        "color": 0x4cc2ff,
        "fields": [
            {"name": "Category", "value": category or "N/A", "inline": True},
            {"name": "Size", "value": size or "?", "inline": True},
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_torrent_completed(name: str, hash: str = "", category: str = "", save_path: str = ""):
    if not config.get("discord.notifications.torrent_completed", True):
        return
    embed = {
        "title": "[OK] Download Complete",
        "description": f"**{name}**",
        "color": 0x00ff88,
        "fields": [
            {"name": "Category", "value": category or "N/A", "inline": True},
            {"name": "Path", "value": f"`{save_path}`", "inline": False},
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_torrent_error(name: str, error: str = ""):
    if not config.get("discord.notifications.torrent_error", True):
        return
    embed = {
        "title": "[X] Torrent Error",
        "description": f"**{name}**\n{error}",
        "color": 0xff4444,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_upload(filename: str, destination: str = "", size: str = ""):
    if not config.get("discord.notifications.upload_complete", True):
        return
    embed = {
        "title": "[UP] File Uploaded",
        "description": f"`{filename}` -> `{destination}`",
        "color": 0xffaa00,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_download_completed(filename: str, category: str = "", path: str = "", size: int = 0):
    if not config.get("discord.notifications.download_completed", True):
        return
    size_str = f"{size / 1024 / 1024:.1f} MB" if size else "?"
    embed = {
        "title": "[DL] URL Download Complete",
        "description": f"`{filename}` -> `{category}`",
        "color": 0x00ff88,
        "fields": [
            {"name": "Path", "value": f"`{path}`", "inline": False},
            {"name": "Size", "value": size_str, "inline": True},
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_ffmpeg_complete(filename: str, audio_tracks: int = 0, sub_tracks: int = 0, defaults_set: bool = True):
    if not config.get("discord.notifications.ffmpeg_complete", True):
        return
    embed = {
        "title": "[FF] FFmpeg Processed",
        "description": f"`{filename}`",
        "color": 0x00b4d8,
        "fields": [
            {"name": "Audio", "value": str(audio_tracks), "inline": True},
            {"name": "Subtitles", "value": str(sub_tracks), "inline": True},
            {"name": "Defaults", "value": "Yes" if defaults_set else "No", "inline": True},
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_status(total_down: int = 0, total_up: int = 0, active: int = 0, completed: int = 0):
    """Periodic status ping. Called by background monitor."""
    embed = {
        "title": "[i] Plexarr Status",
        "color": 0x888888,
        "fields": [
            {"name": "Active", "value": str(active), "inline": True},
            {"name": "Completed", "value": str(completed), "inline": True},
            {"name": "Down", "value": f"{total_down / 1024 / 1024:.1f} MB/s", "inline": True},
            {"name": "Up", "value": f"{total_up / 1024 / 1024:.1f} MB/s", "inline": True},
        ],
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def notify_progress(torrents: list):
    """Send progress summary for active torrents."""
    if not torrents:
        return
    lines = []
    for t in torrents[:10]:
        bar = _progress_bar(t.get("progress", 0))
        lines.append(f"{bar} `{t.get('name', '?')[:40]}` **{t.get('progress', 0)}%**")
    embed = {
        "title": "[o] Download Progress",
        "description": "\n".join(lines),
        "color": 0x4cc2ff,
        "timestamp": datetime.utcnow().isoformat(),
        "footer": {"text": "Plexarr V2"},
    }
    _send({"embeds": [embed], "username": "Plexarr"})


def _progress_bar(pct: float, length: int = 10) -> str:
    filled = int((pct / 100) * length)
    return "#" * filled + "-" * (length - filled)
