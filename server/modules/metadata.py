"""Plexarr — Metadata Providers (TMDB, Jikan, TVDB) with Cover Art"""
import requests
import time
from typing import Dict, List, Optional, Any

try:
    import tmdbsimple as tmdb
except ImportError:
    tmdb = None

from modules.config import config
from modules.logger import log

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}

TMDB_IMG_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"


class TMDBClient:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.get("tmdb.api_key", "")
        self.enabled = config.get("tmdb.enabled", True) and bool(self.api_key)
        self.language = config.get("tmdb.language", "en-US")
        self.fetch_cover = config.get("tmdb.fetch_cover_art", True)
        self.fetch_backdrop = config.get("tmdb.fetch_backdrops", True)
        if self.enabled and tmdb:
            tmdb.API_KEY = self.api_key

    def _cover_url(self, path: str) -> str:
        if not path:
            return ""
        return f"{TMDB_IMG_BASE}{path}"

    def _backdrop_url(self, path: str) -> str:
        if not path:
            return ""
        return f"{TMDB_BACKDROP_BASE}{path}"

    def search_movie(self, query: str, year: int = None) -> List[Dict]:
        if not self.enabled:
            return []
        try:
            search = tmdb.Search()
            kwargs = {"query": query, "language": self.language}
            if year:
                kwargs["year"] = year
            search.movie(**kwargs)
            results = []
            for r in search.results[:10]:
                item = {
                    "id": r.get("id"),
                    "title": r.get("title"),
                    "original_title": r.get("original_title"),
                    "overview": r.get("overview"),
                    "release_date": r.get("release_date"),
                    "vote_average": r.get("vote_average"),
                    "vote_count": r.get("vote_count"),
                    "poster_path": self._cover_url(r.get("poster_path")) if self.fetch_cover else r.get("poster_path"),
                    "backdrop_path": self._backdrop_url(r.get("backdrop_path")) if self.fetch_backdrop else r.get("backdrop_path"),
                    "media_type": "movie",
                }
                results.append(item)
            return results
        except Exception as e:
            log.error(f"TMDB movie search error: {e}")
            return []

    def search_tv(self, query: str, first_air_date_year: int = None) -> List[Dict]:
        if not self.enabled:
            return []
        try:
            search = tmdb.Search()
            kwargs = {"query": query, "language": self.language}
            if first_air_date_year:
                kwargs["first_air_date_year"] = first_air_date_year
            search.tv(**kwargs)
            results = []
            for r in search.results[:10]:
                item = {
                    "id": r.get("id"),
                    "name": r.get("name"),
                    "original_name": r.get("original_name"),
                    "overview": r.get("overview"),
                    "first_air_date": r.get("first_air_date"),
                    "vote_average": r.get("vote_average"),
                    "vote_count": r.get("vote_count"),
                    "poster_path": self._cover_url(r.get("poster_path")) if self.fetch_cover else r.get("poster_path"),
                    "backdrop_path": self._backdrop_url(r.get("backdrop_path")) if self.fetch_backdrop else r.get("backdrop_path"),
                    "media_type": "tv",
                }
                results.append(item)
            return results
        except Exception as e:
            log.error(f"TMDB TV search error: {e}")
            return []

    def get_tv_details(self, tv_id: int) -> Dict:
        if not self.enabled:
            return {}
        try:
            tv = tmdb.TV(tv_id)
            info = tv.info(language=self.language)
            seasons = []
            for s in info.get("seasons", []):
                seasons.append({
                    "number": s.get("season_number"),
                    "name": s.get("name"),
                    "episode_count": s.get("episode_count"),
                    "overview": s.get("overview"),
                    "air_date": s.get("air_date"),
                    "poster_path": self._cover_url(s.get("poster_path")) if self.fetch_cover else s.get("poster_path"),
                })
            return {
                "id": info.get("id"),
                "name": info.get("name"),
                "overview": info.get("overview"),
                "first_air_date": info.get("first_air_date"),
                "number_of_seasons": info.get("number_of_seasons"),
                "number_of_episodes": info.get("number_of_episodes"),
                "poster_path": self._cover_url(info.get("poster_path")) if self.fetch_cover else info.get("poster_path"),
                "backdrop_path": self._backdrop_url(info.get("backdrop_path")) if self.fetch_backdrop else info.get("backdrop_path"),
                "seasons": seasons,
                "genres": [g["name"] for g in info.get("genres", [])],
            }
        except Exception as e:
            log.error(f"TMDB TV details error: {e}")
            return {}

    def get_movie_details(self, movie_id: int) -> Dict:
        if not self.enabled:
            return {}
        try:
            movie = tmdb.Movies(movie_id)
            info = movie.info(language=self.language)
            return {
                "id": info.get("id"),
                "title": info.get("title"),
                "overview": info.get("overview"),
                "release_date": info.get("release_date"),
                "runtime": info.get("runtime"),
                "poster_path": self._cover_url(info.get("poster_path")) if self.fetch_cover else info.get("poster_path"),
                "backdrop_path": self._backdrop_url(info.get("backdrop_path")) if self.fetch_backdrop else info.get("backdrop_path"),
                "genres": [g["name"] for g in info.get("genres", [])],
                "vote_average": info.get("vote_average"),
            }
        except Exception as e:
            log.error(f"TMDB movie details error: {e}")
            return {}

    def get_episodes(self, tv_id: int, season_num: int) -> List[Dict]:
        if not self.enabled:
            return []
        try:
            tv = tmdb.TV(tv_id)
            info = tv.season(season_num, language=self.language)
            episodes = []
            for ep in info.get("episodes", []):
                episodes.append({
                    "number": ep.get("episode_number"),
                    "name": ep.get("name"),
                    "overview": ep.get("overview"),
                    "air_date": ep.get("air_date"),
                    "vote_average": ep.get("vote_average"),
                })
            return episodes
        except Exception as e:
            log.error(f"TMDB episodes error: {e}")
            return []


class JikanClient:
    """Jikan API v4 — Unofficial MyAnimeList API. No key required."""
    def __init__(self):
        self.base_url = config.get("jikan.base_url", "https://api.jikan.moe/v4")
        self.enabled = config.get("jikan.enabled", True)
        self.fetch_cover = config.get("jikan.fetch_cover_art", True)
        self._last_request = 0
        self._min_delay = 0.6

    def _get(self, endpoint: str, params: dict = None) -> Optional[Dict]:
        if not self.enabled:
            return None
        elapsed = time.time() - self._last_request
        if elapsed < self._min_delay:
            time.sleep(self._min_delay - elapsed)
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
            self._last_request = time.time()
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2)
                return self._get(endpoint, params)
            else:
                log.warn(f"Jikan HTTP {resp.status_code} on {url}")
                return None
        except Exception as e:
            log.error(f"Jikan request error: {e}")
            return None

    def search_anime(self, query: str, limit: int = 10) -> List[Dict]:
        data = self._get("/anime", {"q": query, "limit": limit, "order_by": "popularity", "sort": "asc"})
        if data and "data" in data:
            results = []
            for r in data["data"][:limit]:
                item = {
                    "mal_id": r.get("mal_id"),
                    "title": r.get("title"),
                    "title_english": r.get("title_english"),
                    "title_japanese": r.get("title_japanese"),
                    "type": r.get("type"),
                    "episodes": r.get("episodes"),
                    "score": r.get("score"),
                    "synopsis": r.get("synopsis"),
                    "status": r.get("status"),
                    "aired": r.get("aired", {}).get("string"),
                    "images": r.get("images", {}),
                    "cover_url": r.get("images", {}).get("jpg", {}).get("image_url") if self.fetch_cover else "",
                    "media_type": "anime",
                }
                results.append(item)
            return results
        return []

    def search_manga(self, query: str, limit: int = 10) -> List[Dict]:
        data = self._get("/manga", {"q": query, "limit": limit})
        if data and "data" in data:
            return data["data"]
        return []

    def get_anime(self, mal_id: int) -> Optional[Dict]:
        data = self._get(f"/anime/{mal_id}")
        if data and "data" in data:
            r = data["data"]
            return {
                "mal_id": r.get("mal_id"),
                "title": r.get("title"),
                "title_english": r.get("title_english"),
                "synopsis": r.get("synopsis"),
                "episodes": r.get("episodes"),
                "score": r.get("score"),
                "status": r.get("status"),
                "season": r.get("season"),
                "year": r.get("year"),
                "cover_url": r.get("images", {}).get("jpg", {}).get("image_url") if self.fetch_cover else "",
            }
        return None

    def get_seasons(self, mal_id: int) -> List[Dict]:
        data = self._get(f"/anime/{mal_id}/full")
        if not data or "data" not in data:
            return []
        anime = data["data"]
        related = anime.get("relations", [])
        seasons = []
        for rel in related:
            if rel.get("relation") in ("Sequel", "Prequel", "Alternative version"):
                for entry in rel.get("entry", []):
                    if entry.get("type") == "anime":
                        seasons.append({
                            "mal_id": entry.get("mal_id"),
                            "title": entry.get("name"),
                            "relation": rel.get("relation"),
                        })
        return seasons


class TVDBClient:
    """TheTVDB API v4 — requires subscription/key."""
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.get("tvdb.api_key", "")
        self.enabled = config.get("tvdb.enabled", False) and bool(self.api_key)
        self.token = None
        self.base_url = "https://api4.thetvdb.com/v4"

    def _auth(self) -> bool:
        if not self.enabled or not self.api_key:
            return False
        try:
            resp = requests.post(
                f"{self.base_url}/login",
                json={"apikey": self.api_key},
                headers={"Content-Type": "application/json"},
                timeout=15,
            )
            if resp.status_code == 200:
                self.token = resp.json().get("data", {}).get("token")
                return True
        except Exception as e:
            log.error(f"TVDB auth error: {e}")
        return False

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}

    def search(self, query: str, type: str = "series") -> List[Dict]:
        if not self.enabled or not self.token:
            if not self._auth():
                return []
        try:
            resp = requests.get(
                f"{self.base_url}/search",
                params={"q": query, "type": type},
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return data
            elif resp.status_code == 401:
                self._auth()
                return self.search(query, type)
        except Exception as e:
            log.error(f"TVDB search error: {e}")
        return []

    def get_series(self, tvdb_id: int) -> Optional[Dict]:
        if not self.enabled or not self.token:
            if not self._auth():
                return None
        try:
            resp = requests.get(
                f"{self.base_url}/series/{tvdb_id}/extended",
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json().get("data")
        except Exception as e:
            log.error(f"TVDB series error: {e}")
        return None

    def get_seasons(self, tvdb_id: int) -> List[Dict]:
        series = self.get_series(tvdb_id)
        if not series:
            return []
        seasons = series.get("seasons", [])
        return [
            {
                "number": s.get("number"),
                "name": s.get("name"),
                "type": s.get("type", {}).get("name"),
                "episode_count": len(s.get("episodes", [])),
            }
            for s in seasons
        ]


class MetadataManager:
    def __init__(self):
        self.tmdb = TMDBClient()
        self.jikan = JikanClient()
        self.tvdb = TVDBClient()

    def search(self, query: str, media_type: str = "") -> Dict[str, List]:
        """Search across all enabled providers."""
        results = {}
        if media_type in ("", "movie", "tv"):
            if self.tmdb.enabled:
                if media_type in ("", "movie"):
                    results["tmdb_movies"] = self.tmdb.search_movie(query)
                if media_type in ("", "tv"):
                    results["tmdb_tv"] = self.tmdb.search_tv(query)
        if media_type in ("", "anime"):
            if self.jikan.enabled:
                results["jikan_anime"] = self.jikan.search_anime(query)
        if media_type in ("", "tv"):
            if self.tvdb.enabled:
                results["tvdb_series"] = self.tvdb.search(query, "series")
        return results

    def enrich_torrent(self, torrent_title: str, media_type: str = "") -> Dict[str, Any]:
        """Try to find metadata for a torrent title to improve naming."""
        try:
            from guessit import guessit
            guess = guessit(torrent_title)
            clean_title = guess.get("title", torrent_title)
            year = guess.get("year")
            season = guess.get("season", 1)
            episode = guess.get("episode", 1)
        except Exception:
            clean_title = torrent_title
            year = None
            season = 1
            episode = 1

        enriched = {
            "title": clean_title,
            "year": year,
            "season": season,
            "episode": episode,
            "media_type": media_type or "unknown",
            "cover_url": "",
            "backdrop_url": "",
            "overview": "",
        }

        if media_type == "movie" or (not media_type and year):
            movies = self.tmdb.search_movie(clean_title, year) if self.tmdb.enabled else []
            if movies:
                m = movies[0]
                enriched["tmdb_match"] = m
                enriched["cover_url"] = m.get("poster_path", "")
                enriched["backdrop_url"] = m.get("backdrop_path", "")
                enriched["overview"] = m.get("overview", "")
                enriched["year"] = m.get("release_date", year)

        if media_type == "tv" or media_type == "anime":
            tv = self.tmdb.search_tv(clean_title, year) if self.tmdb.enabled else []
            if tv:
                t = tv[0]
                enriched["tmdb_match"] = t
                enriched["cover_url"] = t.get("poster_path", "")
                enriched["backdrop_url"] = t.get("backdrop_path", "")
                enriched["overview"] = t.get("overview", "")
            if media_type == "anime":
                anime = self.jikan.search_anime(clean_title, limit=3) if self.jikan.enabled else []
                if anime:
                    a = anime[0]
                    enriched["jikan_match"] = a
                    if not enriched["cover_url"]:
                        enriched["cover_url"] = a.get("cover_url", "")
                    if not enriched["overview"]:
                        enriched["overview"] = a.get("synopsis", "")

        return enriched

    def get_seasons(self, source: str, id_val: int, media_type: str = "") -> List[Dict]:
        """Get seasons from TMDB or TVDB."""
        if source == "tmdb" and media_type == "tv":
            return self.tmdb.get_tv_details(id_val).get("seasons", [])
        if source == "tmdb" and media_type == "movie":
            return []
        if source == "tvdb":
            return self.tvdb.get_seasons(id_val)
        return []

    def get_episodes(self, source: str, id_val: int, season_num: int, media_type: str = "") -> List[Dict]:
        if source == "tmdb" and media_type == "tv":
            return self.tmdb.get_episodes(id_val, season_num)
        return []
