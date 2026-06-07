"""Watch folder auto-categorizer.

Monitors a staging folder and auto-detects media type from filenames,
then moves files into Plex-compliant paths using the existing auto_renamer.
Also provides a simple upload-to-categorize endpoint helper.
"""

import os
import re
import shutil
import logging
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from threading import Thread, Event
from time import sleep

try:
    from .auto_renamer import process_file, parse_filename, build_plex_path, _is_anime_filename
    from .naming_detector import full_strip, strip_all_variations
except ImportError:
    from auto_renamer import process_file, parse_filename, build_plex_path, _is_anime_filename
    from naming_detector import full_strip, strip_all_variations

logger = logging.getLogger(__name__)

# Extensions we consider media
MEDIA_EXTENSIONS = {".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".wmv", ".flv", ".mp3", ".flac", ".aac", ".m4a", ".ogg", ".wav", ".avi", ".webm"}


def _guess_media_type(filepath: str) -> str:
    """Guess media type from filename + content heuristics."""
    name = Path(filepath).name.lower()
    guess = parse_filename(filepath)

    # Anime detection via naming
    if _is_anime_filename(name):
        return "anime"

    # Music detection
    if Path(filepath).suffix.lower() in {".mp3", ".flac", ".aac", ".m4a", ".ogg", ".wav"}:
        return "music"

    # Video file
    if guess.get("type") == "episode":
        # Distinguish anime from TV using cleaned title
        clean = full_strip(name).lower()
        anime_keywords = {"season", "s01", "s02", "episode", "ep"}
        if any(k in clean for k in anime_keywords) and len(clean) < 80:
            pass  # could be TV or anime
        return "tv"
    if guess.get("type") == "movie":
        return "movie"

    # Fallback: check directory hints or size
    try:
        size = os.path.getsize(filepath)
        if size < 50 * 1024 * 1024:  # < 50MB likely music
            return "music"
    except OSError:
        pass

    return "downloads"


def categorize_file(filepath: str, paths_cfg: Dict[str, str], prefer_anime: bool = True, remove_original: bool = True) -> Optional[str]:
    """Move a single file into the correct Plex path based on auto-detection."""
    src = Path(filepath)
    if not src.exists():
        logger.warning("[WATCH] Source not found: %s", filepath)
        return None

    media_type = _guess_media_type(filepath)
    dest_base = paths_cfg.get(media_type, paths_cfg.get("downloads", "/tmp/plexarr"))

    # Use existing auto_renamer logic
    result = process_file(filepath, dest_base, media_type, prefer_anime)
    if result:
        logger.info("[WATCH] Categorized %s -> %s (%s)", src.name, result, media_type)
        return result
    else:
        # Fallback: copy to downloads with a clean name
        clean_name = strip_all_variations(src.name)
        dest_path = Path(dest_base) / clean_name
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        if remove_original:
            shutil.move(str(src), str(dest_path))
        else:
            shutil.copy2(str(src), str(dest_path))
        logger.info("[WATCH] Fallback move %s -> %s", src.name, dest_path)
        return str(dest_path)


def categorize_batch(directory: str, paths_cfg: Dict[str, str], prefer_anime: bool = True, remove_original: bool = True) -> List[str]:
    """Categorize all media files in a directory."""
    results = []
    d = Path(directory)
    if not d.is_dir():
        return results
    for f in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if f.is_file() and f.suffix.lower() in MEDIA_EXTENSIONS:
            res = categorize_file(str(f), paths_cfg, prefer_anime, remove_original)
            if res:
                results.append(res)
    return results


class WatchFolder:
    """Background thread that monitors a folder for new files."""

    def __init__(self, watch_dir: str, paths_cfg: Dict[str, str], interval: int = 5, prefer_anime: bool = True):
        self.watch_dir = Path(watch_dir)
        self.paths_cfg = paths_cfg
        self.interval = max(1, interval)
        self.prefer_anime = prefer_anime
        self._stop = Event()
        self._thread: Optional[Thread] = None
        self._seen: set = set()

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        # Pre-populate seen set with existing files
        self._seen = {str(f) for f in self.watch_dir.iterdir() if f.is_file()}
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[WATCH] Started monitoring %s", self.watch_dir)

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        logger.info("[WATCH] Stopped monitoring %s", self.watch_dir)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _run(self):
        while not self._stop.is_set():
            try:
                current = {f for f in self.watch_dir.iterdir() if f.is_file()}
                new_files = current - {Path(s) for s in self._seen}
                for f in sorted(new_files, key=lambda x: x.name.lower()):
                    # Wait briefly for file to finish writing
                    sleep(0.5)
                    categorize_file(str(f), self.paths_cfg, self.prefer_anime, remove_original=True)
                    self._seen.add(str(f))
                # Clean up seen set for files that were removed
                self._seen = {str(f) for f in current}
            except Exception as e:
                logger.error("[WATCH] Error: %s", e)
            self._stop.wait(self.interval)

    def status(self) -> Dict:
        return {
            "watch_dir": str(self.watch_dir),
            "running": self.is_running(),
            "interval": self.interval,
            "seen_count": len(self._seen),
        }


# Global singleton watch manager
_watchers: Dict[str, WatchFolder] = {}


def start_watcher(name: str, watch_dir: str, paths_cfg: Dict[str, str], interval: int = 5, prefer_anime: bool = True) -> WatchFolder:
    if name in _watchers:
        _watchers[name].stop()
    w = WatchFolder(watch_dir, paths_cfg, interval, prefer_anime)
    w.start()
    _watchers[name] = w
    return w


def stop_watcher(name: str) -> bool:
    if name in _watchers:
        _watchers[name].stop()
        del _watchers[name]
        return True
    return False


def watcher_status(name: str) -> Optional[Dict]:
    w = _watchers.get(name)
    return w.status() if w else None


def list_watchers() -> Dict[str, Dict]:
    return {k: v.status() for k, v in _watchers.items()}
