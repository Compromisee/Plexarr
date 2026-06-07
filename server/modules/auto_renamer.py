"""PlexLink V2 — Auto Renamer & Sorter (Plex Naming Guidelines)"""
import re
import shutil
import os
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any

try:
    from guessit import guessit as _guessit
except ImportError:
    _guessit = None

from modules.config import config

# Aggressive release tag stripping
_JUNK_RE = re.compile(
    r'[\[\(]?\s*'
    r'(?:'
    r'720p|1080p|2160p|4K|x264|x265|HEVC|AVC|AAC|MP3|FLAC|AC3|DTS|'
    r'Blu-?Ray|WEB-?DL|WEBRip|WEB-DLMux|DVDRip|BDRip|HDTV|HDR|HDR10|DV|DoVi|Atmos|'
    r'REPACK|PROPER|Extended|UNCUT|Directors\s*Cut|IMAX|'
    r'Dual\s*Audio|Multi-?Sub|ESub|HC|KORSUB|SUBBED|DUBBED|'
    r'YIFY|YTS|RARBG|AMZN|NF|Hulu|CR|Funimation|HIDIVE|VRV|'
    r'HorribleSubs|Erai-raws|SubsPlease|Commie|FFF|Asenshi|DameDesuYo|'
    r'SallySubs|GJM|Kametsu|Judas|Akihito|HakataRamune|Rare|AnimeKaizoku|'
    r'Ohys-Raws|Leopard-Raws|RAW|LoliHouse|ARC|Vivid|Tenrai|deanzel|'
    r'Pahe\.in|PSA|UWEB|HS|BD|OVA|ONA|Specials|OVAs|ONAs|'
    r'\d{3,4}p|10-?bit|8-?bit|Hi10|H264|H265|HEVC|'
    r'\d{1,2}bit|Lossless|'
    r'[a-zA-Z0-9\-]+subs?|[a-zA-Z0-9\-]+raws?|'
    r'\[\w+\]|\(\w+\)'
    r')'
    r'\s*[\]\)]?',
    re.IGNORECASE,
)

_YEAR_RE = re.compile(r'\s*\(\d{4}\)\s*')
_EPISODE_RE = re.compile(r'[Ss]?(\d{1,2})[Ee]?(\d{1,2})', re.IGNORECASE)
_SEASON_RE = re.compile(r'Season\s*(\d+)', re.IGNORECASE)


def clean_title(name: str) -> str:
    """Remove junk tags, normalize whitespace, title-case."""
    # Replace dots and underscores with spaces
    name = re.sub(r'[._]', ' ', name)
    # Strip junk tags
    name = _JUNK_RE.sub('', name)
    # Remove orphaned brackets and parens
    name = re.sub(r'[\[\]\(\)\{\}]', '', name)
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name)
    # Strip trailing season markers like "Season 1" from title itself
    name = re.sub(r'Season\s*\d+.*$', '', name, flags=re.IGNORECASE)
    return name.strip(' -').title()


def parse_filename(path: Path) -> Dict[str, Any]:
    """Extract metadata from filename."""
    if _guessit:
        try:
            guess = _guessit(path.name)
            # Override type for anime if detected
            if 'anime' in guess.get('type', '') or _is_anime_filename(path.name):
                guess['type'] = 'anime'
            return guess
        except Exception:
            pass

    # Fallback regex parser
    stem = path.stem
    ext = path.suffix.lstrip('.').lower() or 'mkv'

    # Check if anime (common patterns)
    if _is_anime_filename(stem):
        ep_match = re.search(r'\s-\s(\d+)(?:v\d+)?(?:\s|$)', stem)
        abs_ep = int(ep_match.group(1)) if ep_match else 1
        # Try to find season
        season_match = _SEASON_RE.search(stem)
        season = int(season_match.group(1)) if season_match else 1
        title = re.sub(r'\s-\s\d+.*$', '', stem).strip()
        return {
            'type': 'anime', 'title': title, 'season': season,
            'episode': abs_ep, 'absolute_episode': abs_ep,
            'container': ext, 'year': None,
        }

    # TV episode check
    ep_match = _EPISODE_RE.search(stem)
    if ep_match:
        season = int(ep_match.group(1)) if ep_match.group(1) else 1
        episode = int(ep_match.group(2))
        title = re.sub(r'[Ss]?\d{1,2}[Ee]?\d{1,2}.*$', '', stem).strip()
        return {
            'type': 'episode', 'title': title, 'season': season,
            'episode': episode, 'container': ext, 'year': None,
        }

    # Movie with year
    year_match = re.search(r'\((\d{4})\)', stem)
    if year_match:
        year = int(year_match.group(1))
        title = re.sub(r'\(\d{4}\).*', '', stem).strip()
        return {
            'type': 'movie', 'title': title, 'year': year,
            'container': ext, 'season': None, 'episode': None,
        }

    # Default
    return {'type': 'other', 'title': stem, 'container': ext, 'year': None}


def _is_anime_filename(name: str) -> bool:
    """Heuristic: check if filename has anime release patterns."""
    anime_patterns = [
        r'\[\w+\]', r'\[\w+\s*\d+\]', r'\(\d{3,4}p\)', r'\[BD\]', r'\[WEB\]',
        r'\[Batch\]', r'\[Complete\]', r'HorribleSubs', r'Erai-raws',
        r'SubsPlease', r'LoliHouse', r'\[\d+\]',
    ]
    for p in anime_patterns:
        if re.search(p, name, re.IGNORECASE):
            return True
    return False


def build_plex_path(guess: dict, src: Path, base: Path, prefer_anime: bool = True) -> Tuple[Path, str]:
    """Returns (destination_path, description)."""
    mtype = guess.get('type', 'other')
    ext = guess.get('container', src.suffix.lstrip('.')).lower() or 'mkv'
    ext = ext.replace('mpeg4', 'mp4').replace('mpeg', 'mpg')
    title = clean_title(guess.get('title', 'Unknown'))
    year = guess.get('year')

    if mtype in ('episode', 'tv') and year is None:
        season = guess.get('season', 1)
        if isinstance(season, list):
            season = season[0]
        season = int(season) if season else 1
        episode = guess.get('episode', 1)
        if isinstance(episode, list):
            episode = episode[0]
        episode = int(episode) if episode else 1
        ep_title = clean_title(guess.get('episode_title', ''))
        if ep_title and ep_title.lower() != title.lower():
            fname = f"{title} - S{season:02d}E{episode:02d} - {ep_title}.{ext}"
        else:
            fname = f"{title} - S{season:02d}E{episode:02d}.{ext}"
        dest = base / 'TV Shows' / title / f'Season {season:02d}'
        return dest / fname, f"TV → {dest / fname}"

    elif mtype == 'movie':
        if year:
            folder = f"{title} ({year})"
            fname = f"{title} ({year}).{ext}"
        else:
            folder = title
            fname = f"{title}.{ext}"
        dest = base / 'Movies' / folder
        return dest / fname, f"Movie → {dest / fname}"

    elif mtype == 'anime' or (prefer_anime and _is_anime_filename(src.name)):
        season = guess.get('season', 1)
        if isinstance(season, list):
            season = season[0]
        season = int(season) if season else 1
        episode = guess.get('episode', guess.get('absolute_episode', 1))
        if isinstance(episode, list):
            episode = episode[0]
        episode = int(episode) if episode else 1
        abs_ep = guess.get('absolute_episode', episode)
        fname = f"{title} - S{season:02d}E{episode:02d}.{ext}"
        if abs_ep and abs_ep != episode:
            fname = f"{title} - S{season:02d}E{episode:02d} (E{abs_ep}).{ext}"
        dest = base / 'Anime' / title / f'Season {season:02d}'
        return dest / fname, f"Anime → {dest / fname}"

    else:
        # Music or other
        fname = f"{title}.{ext}" if title else src.name
        if ext in ('mp3', 'flac', 'aac', 'ogg', 'm4a', 'wav', 'opus'):
            dest = base / 'Music'
        else:
            dest = base / 'Other'
        return dest / fname, f"Other → {dest / fname}"


def process_file(src: str, dest_base: Optional[str] = None, media_type: str = "auto", prefer_anime: bool = True) -> Optional[str]:
    """Move and rename a file into Plex-friendly paths. Returns new path."""
    src_path = Path(src)
    if not src_path.exists():
        return None

    base = Path(dest_base) if dest_base else Path(config.get('paths.downloads', '/tmp/plexlink'))
    base.mkdir(parents=True, exist_ok=True)

    guess = parse_filename(src_path)
    if media_type != 'auto':
        guess['type'] = media_type

    dest, info = build_plex_path(guess, src_path, base, prefer_anime)
    dest.parent.mkdir(parents=True, exist_ok=True)

    if dest.resolve() == src_path.resolve():
        return str(dest)

    # Handle collisions by appending (1), (2), etc.
    counter = 1
    original = dest
    while dest.exists():
        stem = original.stem
        suffix = original.suffix
        dest = original.parent / f"{stem} ({counter}){suffix}"
        counter += 1

    shutil.move(str(src_path), str(dest))
    print(f"[AutoRenamer] {info}")
    return str(dest)


def batch_sort(directory: str, dest_base: Optional[str] = None, prefer_anime: bool = True) -> List[str]:
    """Sort all media files in a directory recursively."""
    root = Path(directory)
    if not root.exists() or not root.is_dir():
        return []
    moved = []
    extensions = {'mkv', 'mp4', 'avi', 'mov', 'ts', 'm2ts', 'wmv', 'mpg', 'mpeg', 'flv', 'mp3', 'flac', 'aac', 'ogg', 'wav', 'm4a', 'opus'}
    for p in root.rglob("*"):
        if p.is_file() and p.suffix.lower().lstrip('.') in extensions:
            res = process_file(str(p), dest_base, 'auto', prefer_anime)
            if res:
                moved.append(res)
    # Optionally clean empty dirs
    if config.get('auto_sort.delete_empty_dirs', True):
        for p in sorted(root.rglob("*"), reverse=True):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
    return moved


def suggest_filename(metadata: Dict[str, Any]) -> str:
    """Generate a Plex filename from metadata dict."""
    mtype = metadata.get('type', 'other')
    title = metadata.get('title', 'Unknown')
    year = metadata.get('year')
    season = metadata.get('season', 1)
    episode = metadata.get('episode', 1)
    ext = metadata.get('container', 'mkv')

    if mtype == 'movie' and year:
        return f"{title} ({year}).{ext}"
    elif mtype in ('episode', 'tv', 'anime'):
        return f"{title} - S{int(season):02d}E{int(episode):02d}.{ext}"
    else:
        return f"{title}.{ext}"
