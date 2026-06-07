"""Plexarr — Usenet / SABnzbd Integration

Connects to SABnzbd NZB download client. Maps categories to Plex paths.
Supports NZBGeek and other indexers via NZB search.
"""
import requests
import urllib.parse
from typing import Dict, List, Optional
from modules.config import config
from modules.logger import log


class SABnzbdClient:
    def __init__(self):
        self.host = config.get("sabnzbd.host", "http://localhost:8080")
        self.api_key = config.get("sabnzbd.api_key", "")
        self.enabled = config.get("sabnzbd.enabled", False) and bool(self.api_key)
        self.categories_map = config.get("sabnzbd.categories_map", {
            "tv": "tv",
            "movies": "movies",
            "anime": "anime",
            "music": "music",
        })

    def _get(self, mode: str, params: dict = None) -> Optional[Dict]:
        if not self.enabled:
            return None
        url = f"{self.host}/api"
        payload = {"apikey": self.api_key, "mode": mode, "output": "json"}
        if params:
            payload.update(params)
        try:
            r = requests.get(url, params=payload, timeout=15)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error(f"[SABnzbd] {mode} error: {e}")
            return None

    def _post(self, mode: str, params: dict = None) -> Optional[Dict]:
        if not self.enabled:
            return None
        url = f"{self.host}/api"
        payload = {"apikey": self.api_key, "mode": mode, "output": "json"}
        if params:
            payload.update(params)
        try:
            r = requests.post(url, data=payload, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.error(f"[SABnzbd] {mode} post error: {e}")
            return None

    def queue(self) -> List[Dict]:
        data = self._get("queue")
        if not data or "queue" not in data:
            return []
        slots = data["queue"].get("slots", [])
        return [
            {
                "nzo_id": s.get("nzo_id"),
                "name": s.get("filename", s.get("nzo_id")),
                "status": s.get("status", "Unknown"),
                "size": s.get("size", "?"),
                "size_left": s.get("sizeleft", "?"),
                "percentage": s.get("percentage", "0"),
                "category": s.get("cat", ""),
                "priority": s.get("priority", "Normal"),
            }
            for s in slots
        ]

    def history(self, limit: int = 50) -> List[Dict]:
        data = self._get("history", {"limit": limit})
        if not data or "history" not in data:
            return []
        slots = data["history"].get("slots", [])
        return [
            {
                "nzo_id": s.get("nzo_id"),
                "name": s.get("name", s.get("nzo_id")),
                "status": s.get("status", "Unknown"),
                "size": s.get("size", "?"),
                "category": s.get("category", ""),
                "completed": s.get("completed", ""),
                "path": s.get("storage", ""),
            }
            for s in slots
        ]

    def add_nzb(self, url: str = None, nzb: str = None, category: str = "", filename: str = None, priority: str = "0") -> Dict:
        params = {}
        if category:
            params["cat"] = self.categories_map.get(category, category)
        if priority:
            params["priority"] = priority
        if url:
            params["name"] = url
        elif nzb:
            params["name"] = nzb
        if filename:
            params["nzbname"] = filename
        result = self._post("addurl", params)
        if not result:
            result = self._post("addfile", params)
        if result and result.get("status"):
            return {"ok": True, "nzo_id": result.get("nzo_ids", [None])[0]}
        return {"ok": False, "error": result.get("error", "Add failed") if result else "No response"}

    def pause(self, nzo_id: str = None) -> bool:
        if nzo_id:
            return self._get("queue", {"name": "pause", "value": nzo_id}) is not None
        return self._get("pause") is not None

    def resume(self, nzo_id: str = None) -> bool:
        if nzo_id:
            return self._get("queue", {"name": "resume", "value": nzo_id}) is not None
        return self._get("resume") is not None

    def delete(self, nzo_id: str, delete_files: bool = False) -> bool:
        mode = "delete" if delete_files else "remove"
        return self._get("queue", {"name": mode, "value": nzo_id}) is not None

    def speed(self) -> Dict:
        data = self._get("queue")
        if not data or "queue" not in data:
            return {"speed": "0", "mb_left": "0"}
        q = data["queue"]
        return {
            "speed": q.get("kbpersec", "0"),
            "mb_left": q.get("mbleft", "0"),
            "time_left": q.get("timeleft", "0:00"),
        }


class NZBGeekSearch:
    """NZBGeek RSS/Search wrapper (requires API key)."""
    def __init__(self):
        self.api_key = config.get("nzbgeek.api_key", "")
        self.base_url = "https://api.nzbgeek.info"
        self.enabled = config.get("nzbgeek.enabled", False) and bool(self.api_key)

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        if not self.enabled:
            return []
        try:
            url = f"{self.base_url}/api?t=search&q={urllib.parse.quote(query)}&apikey={self.api_key}&limit={limit}"
            if category:
                url += f"&cat={category}"
            r = requests.get(url, timeout=15)
            r.raise_for_status()
            # Parse XML RSS
            import xml.etree.ElementTree as ET
            root = ET.fromstring(r.text)
            items = []
            for item in root.findall(".//item"):
                title = item.find("title")
                link = item.find("link")
                size = item.find("{http://www.newznab.com/DTD/2010/feeds/attributes/}attr")
                items.append({
                    "title": title.text if title is not None else "?",
                    "link": link.text if link is not None else "",
                    "size": size.attrib.get("value", "?") if size is not None else "?",
                    "provider": "nzbgeek",
                })
            return items
        except Exception as e:
            log.error(f"[NZBGeek] Search error: {e}")
            return []


sab = SABnzbdClient()
nzbgeek = NZBGeekSearch()
