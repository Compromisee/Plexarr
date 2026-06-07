"""PlexLink V2 — qBittorrent Client Integration"""
import time
from typing import Dict, List, Optional
from qbittorrentapi import Client as QBClient, LoginFailed, APIConnectionError
from modules.config import config


class QBittorrentManager:
    def __init__(self):
        self.client: Optional[QBClient] = None
        self.host = config.get("qbittorrent.host", "http://localhost:8080")
        self.username = config.get("qbittorrent.username", "admin")
        self.password = config.get("qbittorrent.password", "adminadmin")
        self.enabled = config.get("qbittorrent.enabled", True)
        self._connected = False

    def connect(self) -> bool:
        if not self.enabled:
            return False
        try:
            self.client = QBClient(
                host=self.host,
                username=self.username,
                password=self.password,
                VERIFY_WEBUI_CERTIFICATE=False,
                REQUESTS_ARGS={"timeout": (10, 30)},
            )
            self.client.auth_log_in()
            self._connected = True
            return True
        except (LoginFailed, APIConnectionError) as e:
            print(f"[qBittorrent] Connection failed: {e}")
            self._connected = False
            return False

    def ensure_connected(self) -> bool:
        if self._connected and self.client:
            try:
                self.client.app.version
                return True
            except Exception:
                self._connected = False
        return self.connect()

    def add_magnet(self, magnet: str, category: str = "", tags: str = "", save_path: str = "") -> bool:
        if not self.ensure_connected():
            return False
        try:
            kwargs = {"urls": magnet}
            if category:
                kwargs["category"] = category
            if tags:
                kwargs["tags"] = tags
            if save_path:
                kwargs["savepath"] = save_path
            self.client.torrents.add(**kwargs)
            return True
        except Exception as e:
            print(f"[qBittorrent] Add magnet error: {e}")
            return False

    def add_torrent_file(self, file_path: str, category: str = "", save_path: str = "") -> bool:
        if not self.ensure_connected():
            return False
        try:
            with open(file_path, "rb") as f:
                kwargs = {"torrent_files": f}
                if category:
                    kwargs["category"] = category
                if save_path:
                    kwargs["savepath"] = save_path
                self.client.torrents_add(**kwargs)
            return True
        except Exception as e:
            print(f"[qBittorrent] Add torrent file error: {e}")
            return False

    def get_torrents(self, status_filter: str = "all") -> List[Dict]:
        if not self.ensure_connected():
            return []
        try:
            torrents = self.client.torrents_info(status_filter=status_filter)
            return [
                {
                    "hash": t.hash,
                    "name": t.name,
                    "size": t.size,
                    "progress": round(t.progress * 100, 2),
                    "speed_down": t.dlspeed,
                    "speed_up": t.upspeed,
                    "seeds": t.num_seeds,
                    "leechs": t.num_leechs,
                    "state": t.state,
                    "category": t.category,
                    "tags": t.tags,
                    "added_on": t.added_on,
                    "completion_on": t.completion_on,
                    "save_path": t.save_path,
                    "ratio": round(t.ratio, 2),
                }
                for t in torrents
            ]
        except Exception as e:
            print(f"[qBittorrent] List error: {e}")
            return []

    def get_categories(self) -> Dict:
        if not self.ensure_connected():
            return {}
        try:
            cats = self.client.torrents_categories()
            return {name: {"save_path": c.savePath} for name, c in cats.items()}
        except Exception as e:
            print(f"[qBittorrent] Categories error: {e}")
            return {}

    def create_category(self, name: str, save_path: str = "") -> bool:
        if not self.ensure_connected():
            return False
        try:
            self.client.torrents_create_category(name=name, save_path=save_path)
            return True
        except Exception as e:
            print(f"[qBittorrent] Create category error: {e}")
            return False

    def delete_torrent(self, torrent_hash: str, delete_files: bool = False) -> bool:
        if not self.ensure_connected():
            return False
        try:
            self.client.torrents_delete(delete_files=delete_files, torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            print(f"[qBittorrent] Delete error: {e}")
            return False

    def pause(self, torrent_hash: str) -> bool:
        if not self.ensure_connected():
            return False
        try:
            self.client.torrents_pause(torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            print(f"[qBittorrent] Pause error: {e}")
            return False

    def resume(self, torrent_hash: str) -> bool:
        if not self.ensure_connected():
            return False
        try:
            self.client.torrents_resume(torrent_hashes=torrent_hash)
            return True
        except Exception as e:
            print(f"[qBittorrent] Resume error: {e}")
            return False

    def global_speed(self) -> Dict:
        if not self.ensure_connected():
            return {"down": 0, "up": 0, "dht_nodes": 0}
        try:
            prefs = self.client.transfer_speed_limits_mode()
            info = self.client.transfer.info()
            return {
                "down": info.dl_info_speed,
                "up": info.up_info_speed,
                "total_downloaded": info.dl_info_data,
                "total_uploaded": info.up_info_data,
                "dht_nodes": info.dht_nodes,
            }
        except Exception as e:
            print(f"[qBittorrent] Speed error: {e}")
            return {"down": 0, "up": 0, "dht_nodes": 0}


qb = QBittorrentManager()
