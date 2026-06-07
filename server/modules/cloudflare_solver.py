"""Plexarr — Cloudflare Solver (Optional)

Wraps cloudscraper or curl-impersonate for sites protected by Cloudflare.
Only activates when cloudflare_solver.enabled is True.
Sites that require CF are NOT listed by default in the provider search.
Users can manually route them through the /proxy endpoint with ?cf_bypass=1.
"""
import requests
from typing import Optional, Dict
from modules.config import config

_HAVE_CLOUDSCRAPER = False
_CLOUDSCRAPER = None

try:
    import cloudscraper
    _HAVE_CLOUDSCRAPER = True
except ImportError:
    pass


class CloudflareSolver:
    def __init__(self):
        self.enabled = config.get("cloudflare_solver.enabled", False)
        self.provider = config.get("cloudflare_solver.provider", "cloudscraper")
        self.ua = config.get("cloudflare_solver.user_agent", "")
        self._session = None

    def _get_session(self):
        if self._session is not None:
            return self._session
        if self.provider == "cloudscraper" and _HAVE_CLOUDSCRAPER:
            self._session = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
        else:
            self._session = requests.Session()
        if self.ua:
            self._session.headers.update({"User-Agent": self.ua})
        return self._session

    def get(self, url: str, timeout: int = 30, **kwargs) -> Optional[requests.Response]:
        if not self.enabled:
            return None
        try:
            s = self._get_session()
            resp = s.get(url, timeout=timeout, **kwargs)
            return resp
        except Exception as e:
            print(f"[CloudflareSolver] GET failed: {e}")
            return None

    def post(self, url: str, data=None, timeout: int = 30, **kwargs) -> Optional[requests.Response]:
        if not self.enabled:
            return None
        try:
            s = self._get_session()
            resp = s.post(url, data=data, timeout=timeout, **kwargs)
            return resp
        except Exception as e:
            print(f"[CloudflareSolver] POST failed: {e}")
            return None


cf_solver = CloudflareSolver()
