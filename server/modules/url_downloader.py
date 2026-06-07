"""Plexarr — URL / Rapidgator Downloader

Supports generic HTTP downloads and Rapidgator premium downloads.
If Rapidgator premium is configured, uses API for fast parallel downloads.
Otherwise falls back to free-mode scraping (slow, may require captcha).
"""
import os
import re
import time
import requests
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import urlparse
from modules.config import config
from modules.discord_webhook import notify_download_completed, notify_error


class URLDownloader:
    def __init__(self):
        self.enabled = config.get("url_downloader.enabled", True)
        self.rg = config.get("url_downloader.rapidgator", {})
        self.gen = config.get("url_downloader.generic", {})
        self.download_dir = Path(config.get("paths.downloads", "/tmp/plexarr")) / "url_downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)

    def _headers(self) -> Dict:
        return {
            "User-Agent": self.gen.get("user_agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def is_rapidgator(self, url: str) -> bool:
        return "rapidgator.net" in url or "rg.to" in url

    def download(self, url: str, filename: Optional[str] = None, category: str = "downloads") -> Dict:
        if not self.enabled:
            return {"ok": False, "error": "URL downloader disabled"}

        if self.is_rapidgator(url):
            return self._download_rapidgator(url, filename, category)
        return self._download_generic(url, filename, category)

    def _download_rapidgator(self, url: str, filename: Optional[str], category: str) -> Dict:
        premium = self.rg.get("premium", False)
        api_key = self.rg.get("api_key", "")
        username = self.rg.get("username", "")
        password = self.rg.get("password", "")

        if premium and api_key:
            return self._rg_premium_api(url, filename, category, api_key)
        elif premium and username and password:
            return self._rg_premium_web(url, filename, category, username, password)
        else:
            return self._rg_free(url, filename, category)

    def _rg_premium_api(self, url: str, filename: Optional[str], category: str, api_key: str) -> Dict:
        try:
            # Rapidgator API v2
            file_id = self._extract_rg_file_id(url)
            if not file_id:
                return {"ok": False, "error": "Could not extract Rapidgator file ID"}

            info_resp = requests.get(
                f"https://rapidgator.net/api/v2/file/info?file_id={file_id}&token={api_key}",
                timeout=15
            )
            info = info_resp.json()
            if info.get("response_status") != 200:
                return {"ok": False, "error": info.get("response_details", "API error")}

            dl_resp = requests.get(
                f"https://rapidgator.net/api/v2/file/download?file_id={file_id}&token={api_key}",
                timeout=30
            )
            dl = dl_resp.json()
            if dl.get("response_status") != 200:
                return {"ok": False, "error": dl.get("response_details", "API error")}

            dl_url = dl["response"]["download_url"]
            return self._save_stream(dl_url, filename or info["response"]["file"]["name"], category)
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _rg_premium_web(self, url: str, filename: Optional[str], category: str, username: str, password: str) -> Dict:
        # Fallback: premium web login session (not implemented fully, falls to generic)
        return self._download_generic(url, filename, category)

    def _rg_free(self, url: str, filename: Optional[str], category: str) -> Dict:
        # Free mode requires waiting/captcha — not reliable, falls to generic with warning
        return {
            "ok": False,
            "error": "Rapidgator free mode requires captcha. Enable premium in settings or use torrents.",
            "url": url
        }

    def _extract_rg_file_id(self, url: str) -> Optional[str]:
        m = re.search(r'file/([a-f0-9]+)', url)
        if m:
            return m.group(1)
        m = re.search(r'[?&]file_id=([a-f0-9]+)', url)
        if m:
            return m.group(1)
        return None

    def _download_generic(self, url: str, filename: Optional[str], category: str) -> Dict:
        try:
            resp = requests.get(url, headers=self._headers(), stream=True, timeout=60, allow_redirects=True)
            resp.raise_for_status()

            if not filename:
                cd = resp.headers.get("Content-Disposition", "")
                m = re.search(r'filename="?([^"]+)"?', cd)
                if m:
                    filename = m.group(1)
                else:
                    filename = os.path.basename(urlparse(url).path) or "download.bin"

            return self._save_stream(resp, filename, category)
        except Exception as e:
            return {"ok": False, "error": str(e), "url": url}

    def _save_stream(self, resp_or_url, filename: str, category: str) -> Dict:
        dest = self.download_dir / filename
        counter = 1
        original = dest
        while dest.exists():
            stem = original.stem
            suffix = original.suffix
            dest = original.parent / f"{stem} ({counter}){suffix}"
            counter += 1

        try:
            if isinstance(resp_or_url, str):
                resp = requests.get(resp_or_url, headers=self._headers(), stream=True, timeout=300)
            else:
                resp = resp_or_url

            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = self.gen.get("chunk_size", 8192)

            with open(dest, "wb") as f:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

            notify_download_completed(filename, category, str(dest), downloaded)
            return {
                "ok": True,
                "path": str(dest),
                "filename": filename,
                "size": downloaded,
                "category": category,
                "url": getattr(resp, "url", "")
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def queue_urls(self, urls: List[str], category: str = "downloads") -> List[Dict]:
        results = []
        for url in urls:
            result = self.download(url, category=category)
            results.append(result)
            time.sleep(1)
        return results


url_downloader = URLDownloader()
