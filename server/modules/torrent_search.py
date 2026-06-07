"""Plexarr — Multi-Provider Torrent Search

Cloudflare-protected sites are NOT listed by default in provider search.
They can be accessed via the optional Cloudflare solver module or CORS proxy.
Nyaa.si has its own dedicated endpoint for anime-first search.
"""
import re
import urllib.parse
import requests
import time
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

from modules.config import config
from modules.cloudflare_solver import cf_solver
from modules.logger import log

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


def _safe_int(val, default=0):
    try:
        return int(str(val).replace(",", "").replace("+", ""))
    except:
        return default


class BaseProvider:
    name: str = "base"
    base_url: str = ""
    categories: List[str] = []
    requires_cloudflare: bool = False

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        raise NotImplementedError

    def _get(self, url: str, timeout: int = 15) -> requests.Response:
        if self.requires_cloudflare and cf_solver.enabled:
            resp = cf_solver.get(url, timeout=timeout)
            if resp:
                return resp
        return requests.get(url, headers=HEADERS, timeout=timeout)


class NyaaProvider(BaseProvider):
    name = "nyaa.si"
    base_url = "https://nyaa.si"
    categories = ["All", "Anime", "Audio", "Literature", "Live Action", "Pictures", "Software", "Games"]
    requires_cloudflare = False

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        cat_map = {
            "All": "0_0", "Anime": "1_0", "Audio": "2_0", "Literature": "3_0",
            "Live Action": "4_0", "Pictures": "5_0", "Software": "6_1", "Games": "6_2"
        }
        cat = cat_map.get(category, "0_0")
        url = f"{self.base_url}/?f=0&c={cat}&q={urllib.parse.quote(query)}"
        resp = self._get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        rows = soup.select("table.torrent-list tbody tr")
        results = []
        for row in rows[:limit]:
            tds = row.find_all("td")
            if len(tds) < 6:
                continue
            title_cell = tds[1]
            link_a = title_cell.find_all("a")[-1]
            title = link_a.get_text(strip=True)
            page = self.base_url + link_a["href"] if link_a["href"].startswith("/") else link_a["href"]

            links_cell = tds[2]
            magnet = None
            torrent = None
            for a in links_cell.find_all("a", href=True):
                href = a["href"]
                if href.startswith("magnet:"):
                    magnet = href
                elif href.endswith(".torrent"):
                    torrent = self.base_url + href if href.startswith("/") else href

            results.append({
                "title": title, "page": page, "magnet": magnet, "torrent": torrent,
                "size": tds[3].get_text(strip=True), "date": tds[4].get_text(strip=True),
                "seeders": _safe_int(tds[5].get_text(strip=True)),
                "leechers": _safe_int(tds[6].get_text(strip=True)) if len(tds) > 6 else 0,
                "downloads": _safe_int(tds[7].get_text(strip=True)) if len(tds) > 7 else 0,
                "provider": self.name, "category": category or "All",
                "resolution": self._guess_resolution(title),
                "requires_cloudflare": False,
                "anime_only": True,
            })
        return results

    def _guess_resolution(self, title: str) -> str:
        if "1080p" in title or "1920" in title: return "1080p"
        if "720p" in title or "1280" in title: return "720p"
        if "2160p" in title or "4K" in title or "UHD" in title: return "4K"
        return ""


class AnimeToshoProvider(BaseProvider):
    name = "animetosho.org"
    base_url = "https://animetosho.org"
    categories = ["All"]
    requires_cloudflare = False

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        url = f"{self.base_url}/search?q={urllib.parse.quote(query)}"
        resp = self._get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        entries = soup.select(".home_list_entry")
        results = []
        for entry in entries[:limit]:
            title_a = entry.select_one(".home_list_entry_title a")
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            page = title_a["href"]
            if page.startswith("/"):
                page = self.base_url + page

            size_el = entry.select_one(".home_list_entry_size")
            size = size_el.get_text(strip=True) if size_el else "?"

            magnet_a = entry.select_one("a[href^='magnet:']")
            magnet = magnet_a["href"] if magnet_a else None

            torrent_a = entry.select_one("a[href*='download']")
            torrent = None
            if torrent_a:
                torrent = torrent_a["href"]
                if torrent.startswith("/"):
                    torrent = self.base_url + torrent

            seeders = entry.select_one(".home_list_entry_seeders")
            seeders = seeders.get_text(strip=True) if seeders else "0"

            results.append({
                "title": title, "page": page, "magnet": magnet, "torrent": torrent,
                "size": size, "date": "", "seeders": _safe_int(seeders), "leechers": 0,
                "downloads": 0, "provider": self.name, "category": "All",
                "resolution": "", "requires_cloudflare": False, "anime_only": True,
            })
        return results


class YTSProvider(BaseProvider):
    name = "yts.mx"
    base_url = "https://yts.mx"
    categories = ["Movies"]
    requires_cloudflare = False

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        url = f"{self.base_url}/api/v2/list_movies.json?query_term={urllib.parse.quote(query)}&limit={limit}"
        try:
            resp = self._get(url)
            data = resp.json()
        except Exception as e:
            log.error(f"[YTS] Error: {e}")
            return []
        results = []
        for movie in data.get("data", {}).get("movies", [])[:limit]:
            for torrent in movie.get("torrents", []):
                results.append({
                    "title": f"{movie.get('title_long', 'Unknown')} [{torrent.get('quality','')} {torrent.get('type','')}]",
                    "page": movie.get("url", ""),
                    "magnet": torrent.get("url", ""),
                    "torrent": None,
                    "size": torrent.get("size", "?"),
                    "date": movie.get("date_uploaded", ""),
                    "seeders": torrent.get("seeds", 0),
                    "leechers": torrent.get("peers", 0),
                    "downloads": 0,
                    "provider": self.name,
                    "category": "Movies",
                    "resolution": torrent.get("quality", ""),
                    "imdb": movie.get("imdb_code", ""),
                    "requires_cloudflare": False,
                    "anime_only": False,
                })
        return results


class EZTVProvider(BaseProvider):
    name = "eztv.re"
    base_url = "https://eztv.re"
    categories = ["TV"]
    requires_cloudflare = False

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        url = f"https://eztvx.to/search/{urllib.parse.quote(query.replace(' ', '-'))}"
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.error(f"[EZTV] Error: {e}")
            return []
        results = []
        for row in soup.select("tr.forum_header_border")[:limit]:
            tds = row.find_all("td")
            if len(tds) < 4:
                continue
            title_a = tds[1].find("a", class_="epinfo")
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            magnet = None
            for a in tds[2].find_all("a", href=True):
                if a["href"].startswith("magnet:"):
                    magnet = a["href"]
            size = tds[3].get_text(strip=True)
            results.append({
                "title": title, "page": "", "magnet": magnet, "torrent": None,
                "size": size, "date": "", "seeders": 0, "leechers": 0,
                "downloads": 0, "provider": self.name, "category": "TV",
                "resolution": "", "requires_cloudflare": False, "anime_only": False,
            })
        return results


class TorrentGalaxyProvider(BaseProvider):
    name = "torrentgalaxy.to"
    base_url = "https://torrentgalaxy.to"
    categories = ["All", "Movies", "TV", "Anime", "Apps", "Games", "Music", "Books", "Other"]
    requires_cloudflare = True  # Flagged as CF-protected

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        cat_map = {
            "All": "", "Movies": "c3=1&", "TV": "c4=1&", "Anime": "c28=1&",
            "Apps": "c5=1&", "Games": "c6=1&", "Music": "c7=1&", "Books": "c8=1&", "Other": "c9=1&"
        }
        cat = cat_map.get(category, "")
        url = f"{self.base_url}/torrents.php?{cat}search={urllib.parse.quote(query)}&lang=0&nox=1&sort=seeders&order=desc"
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.error(f"[TorrentGalaxy] Error: {e}")
            return []
        results = []
        for div in soup.select("div.tgxtablerow")[:limit]:
            tds = div.find_all("div", class_="tgxtablecell")
            if len(tds) < 8:
                continue
            title_a = tds[3].find("a", href=True)
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            page = title_a["href"]
            if page.startswith("/"):
                page = self.base_url + page

            magnet = None
            for a in div.find_all("a", href=True):
                if a["href"].startswith("magnet:"):
                    magnet = a["href"]

            size = tds[7].get_text(strip=True) if len(tds) > 7 else "?"
            seeders = tds[8].get_text(strip=True) if len(tds) > 8 else "0"

            results.append({
                "title": title, "page": page, "magnet": magnet, "torrent": None,
                "size": size, "date": "", "seeders": _safe_int(seeders), "leechers": 0,
                "downloads": 0, "provider": self.name, "category": category or "All",
                "resolution": "", "requires_cloudflare": True, "anime_only": False,
            })
        return results


# Cloudflare-protected providers not enabled by default
class Provider1337x(BaseProvider):
    name = "1337x.to"
    base_url = "https://1337x.to"
    categories = ["All", "Movies", "TV", "Anime", "Apps", "Games", "Music"]
    requires_cloudflare = True

    def search(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        if not cf_solver.enabled:
            return []
        url = f"{self.base_url}/search/{urllib.parse.quote(query)}/1/"
        try:
            resp = self._get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
        except Exception as e:
            log.error(f"[1337x] Error: {e}")
            return []
        results = []
        for row in soup.select("tbody tr")[:limit]:
            tds = row.find_all("td")
            if len(tds) < 5:
                continue
            title_a = tds[0].find("a", href=True, class_=False)
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            page = title_a["href"]
            if page.startswith("/"):
                page = self.base_url + page
            seeders = tds[1].get_text(strip=True) if len(tds) > 1 else "0"
            leechers = tds[2].get_text(strip=True) if len(tds) > 2 else "0"
            size = tds[4].get_text(strip=True) if len(tds) > 4 else "?"
            results.append({
                "title": title, "page": page, "magnet": None, "torrent": None,
                "size": size, "date": "", "seeders": _safe_int(seeders), "leechers": _safe_int(leechers),
                "downloads": 0, "provider": self.name, "category": category or "All",
                "resolution": "", "requires_cloudflare": True, "anime_only": False,
            })
        return results


class TorrentSearchManager:
    def __init__(self):
        self._providers: Dict[str, BaseProvider] = {}
        self.register(NyaaProvider())
        self.register(AnimeToshoProvider())
        self.register(YTSProvider())
        self.register(EZTVProvider())
        # CF providers only registered if solver is enabled
        self.register(TorrentGalaxyProvider())
        if cf_solver.enabled:
            self.register(Provider1337x())
            log.info("Cloudflare solver enabled. CF-protected providers registered.")

    def register(self, provider: BaseProvider):
        self._providers[provider.name] = provider

    def providers(self) -> List[Dict]:
        return [{"name": p.name, "categories": p.categories, "requires_cloudflare": p.requires_cloudflare, "anime_only": p.anime_only} for p in self._providers.values()]

    def search(self, query: str, provider: Optional[str] = None, category: str = "", limit: int = 50) -> List[Dict]:
        if provider and provider in self._providers:
            return self._providers[provider].search(query, category, limit)
        all_results = []
        for p in self._providers.values():
            if p.requires_cloudflare and not cf_solver.enabled:
                continue
            try:
                all_results.extend(p.search(query, category, limit))
                time.sleep(0.2)
            except Exception as e:
                log.error(f"SearchManager {p.name} failed: {e}")
        all_results.sort(key=lambda r: r.get("seeders", 0), reverse=True)
        return all_results

    def search_by_type(self, query: str, media_type: str = "", limit: int = 50) -> List[Dict]:
        """Route query to best providers by media type."""
        if media_type == "movie":
            return self._providers["yts.mx"].search(query, "Movies", limit)
        elif media_type == "tv":
            results = []
            if "eztv.re" in self._providers:
                results.extend(self._providers["eztv.re"].search(query, "TV", limit))
            if "torrentgalaxy.to" in self._providers:
                tg = self._providers["torrentgalaxy.to"]
                if not tg.requires_cloudflare or cf_solver.enabled:
                    results.extend(tg.search(query, "TV", limit))
            results.sort(key=lambda r: r.get("seeders", 0), reverse=True)
            return results
        elif media_type == "anime":
            results = []
            if "nyaa.si" in self._providers:
                results.extend(self._providers["nyaa.si"].search(query, "Anime", limit))
            if "animetosho.org" in self._providers:
                results.extend(self._providers["animetosho.org"].search(query, "Anime", limit))
            results.sort(key=lambda r: r.get("seeders", 0), reverse=True)
            return results
        else:
            return self.search(query, limit=limit)

    def search_anime(self, query: str, category: str = "", limit: int = 50) -> List[Dict]:
        """Dedicated anime search. Only anime providers."""
        results = []
        for p in self._providers.values():
            if p.anime_only:
                try:
                    results.extend(p.search(query, category, limit))
                except Exception as e:
                    log.error(f"Anime search {p.name} failed: {e}")
        results.sort(key=lambda r: r.get("seeders", 0), reverse=True)
        return results
