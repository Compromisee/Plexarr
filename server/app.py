"""Plexarr V2.1 — Main Flask + SocketIO Application

Run: python app.py
Access: http://your-lan-ip:8080 (or any port configured in config.json)
"""
import os
import sys
import time
import json
import shutil
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

from flask import Flask, render_template, jsonify, request, send_file, Response, abort, redirect, url_for
from flask_socketio import SocketIO, emit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.config import config, DEFAULT_CONFIG
from modules.torrent_search import TorrentSearchManager
from modules.metadata import MetadataManager
from modules.qbittorrent import qb
from modules.discord_webhook import (
    notify_torrent_added, notify_torrent_completed, notify_torrent_error,
    notify_upload, notify_status, notify_progress, notify_download_completed,
    notify_ffmpeg_complete,
)
from modules.auto_renamer import process_file, batch_sort, suggest_filename, parse_filename
from modules.prometheus_metrics import metrics_bp, update_torrent_stats, GRAFANA_DASHBOARD, registry
from modules.screen_stream import ScreenStreamer
from modules.cloudflare_solver import cf_solver, _HAVE_CLOUDSCRAPER
from modules.vpn_manager import vpn
from modules.torrent_search import HEADERS as _TORRENT_HEADERS
from modules.url_downloader import url_downloader
from modules.ffmpeg_processor import process_file as ffmpeg_process, auto_process_download
from modules.naming_detector import detect_variations, full_strip, strip_all_variations
from modules.batch_downloader import batch_mgr, BatchItem
from modules.logger import log
from modules.watch_folder import (
    categorize_file, categorize_batch, start_watcher, stop_watcher,
    watcher_status, list_watchers, WatchFolder
)

# ── Flask Setup ──
app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = config.get("server.secret_key", "change-me")
app.register_blueprint(metrics_bp, url_prefix="/prometheus")

socketio = SocketIO(app, cors_allowed_origins="*", async_mode="eventlet")

searcher = TorrentSearchManager()
metadata = MetadataManager()
streamer: Optional[ScreenStreamer] = None

log.config_summary()

# ── Background Monitors ──
def monitor_torrents():
    """Background thread: poll qBittorrent, emit progress, send Discord notifications."""
    last_hashes = set()
    while True:
        try:
            if config.get("qbittorrent.enabled", True):
                torrents = qb.get_torrents()
                if torrents:
                    socketio.emit("torrent_list", {"torrents": torrents, "ts": time.time()})
                    speeds = qb.global_speed()
                    update_torrent_stats(torrents, speeds.get("down", 0), speeds.get("up", 0))
                    for t in torrents:
                        if t.get("progress", 0) >= 100 and t.get("hash") not in last_hashes:
                            notify_torrent_completed(
                                t.get("name", "?"), t.get("hash"), t.get("category", ""), t.get("save_path", "")
                            )
                            last_hashes.add(t.get("hash"))
                        if t.get("progress", 0) < 100:
                            last_hashes.discard(t.get("hash"))
                    active = [t for t in torrents if 0 < t.get("progress", 0) < 100]
                    if active and int(time.time()) % 60 < 5:
                        notify_progress(active)

            if int(time.time()) % 300 < 5 and config.get("qbittorrent.enabled", True):
                torrents = qb.get_torrents()
                active_count = len([t for t in torrents if 0 < t.get("progress", 0) < 100])
                completed_count = len([t for t in torrents if t.get("progress", 0) >= 100])
                speeds = qb.global_speed()
                notify_status(speeds.get("down", 0), speeds.get("up", 0), active_count, completed_count)

        except Exception as e:
            log.error(f"Monitor error: {e}")
        time.sleep(5)


threading.Thread(target=monitor_torrents, daemon=True).start()

# ── Routes ──
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/health")
def health():
    return jsonify({"status": "ok", "time": time.time(), "version": "2.1.0", "app": "Plexarr"})


# ── Providers ──
@app.route("/api/providers")
def api_providers():
    return jsonify(searcher.providers())


# ── Torrent Search ──
@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    provider = request.args.get("provider", None)
    media_type = request.args.get("type", "")
    category = request.args.get("category", "")
    limit = int(request.args.get("limit", 50))
    if not q or len(q) > 200:
        return jsonify({"error": "Invalid query"}), 400

    if media_type:
        results = searcher.search_by_type(q, media_type, limit)
    elif provider:
        results = searcher.search(q, provider, category, limit)
    else:
        results = searcher.search(q, limit=limit)

    enrich = request.args.get("enrich", "false").lower() == "true"
    if enrich and metadata.tmdb.enabled:
        for r in results[:5]:
            r["metadata"] = metadata.enrich_torrent(r.get("title", ""), media_type)

    return jsonify({"query": q, "count": len(results), "results": results})


# ── Dedicated Anime Search (Nyaa + AnimeTosho) ──
@app.route("/api/search/anime")
def api_search_anime():
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    limit = int(request.args.get("limit", 50))
    if not q or len(q) > 200:
        return jsonify({"error": "Invalid query"}), 400
    results = searcher.search_anime(q, category, limit)
    enrich = request.args.get("enrich", "false").lower() == "true"
    if enrich and metadata.jikan.enabled:
        for r in results[:5]:
            r["metadata"] = metadata.enrich_torrent(r.get("title", ""), "anime")
    return jsonify({"query": q, "count": len(results), "results": results})


# ── Metadata ──
@app.route("/api/metadata/search")
def api_metadata_search():
    q = request.args.get("q", "").strip()
    media_type = request.args.get("type", "")
    if not q:
        return jsonify({"error": "No query"}), 400
    return jsonify(metadata.search(q, media_type))


@app.route("/api/metadata/enrich")
def api_metadata_enrich():
    title = request.args.get("title", "").strip()
    media_type = request.args.get("type", "")
    if not title:
        return jsonify({"error": "No title"}), 400
    return jsonify(metadata.enrich_torrent(title, media_type))


@app.route("/api/metadata/seasons")
def api_metadata_seasons():
    source = request.args.get("source", "tmdb")
    id_val = request.args.get("id", type=int)
    media_type = request.args.get("media_type", "tv")
    if not id_val:
        return jsonify({"error": "No ID"}), 400
    return jsonify(metadata.get_seasons(source, id_val, media_type))


@app.route("/api/metadata/episodes")
def api_metadata_episodes():
    source = request.args.get("source", "tmdb")
    id_val = request.args.get("id", type=int)
    season_num = request.args.get("season", type=int, default=1)
    media_type = request.args.get("media_type", "tv")
    if not id_val:
        return jsonify({"error": "No ID"}), 400
    return jsonify(metadata.get_episodes(source, id_val, season_num, media_type))


@app.route("/api/metadata/cover")
def api_metadata_cover():
    """Fetch cover art URL for a given title and media type."""
    title = request.args.get("title", "").strip()
    media_type = request.args.get("type", "")
    if not title:
        return jsonify({"error": "No title"}), 400
    enriched = metadata.enrich_torrent(title, media_type)
    return jsonify({
        "cover_url": enriched.get("cover_url", ""),
        "backdrop_url": enriched.get("backdrop_url", ""),
        "overview": enriched.get("overview", ""),
    })


# ── Torrents ──
@app.route("/api/torrents")
def api_torrents():
    status = request.args.get("status", "all")
    return jsonify(qb.get_torrents(status))


@app.route("/api/torrent/add", methods=["POST"])
def api_torrent_add():
    data = request.get_json() or {}
    magnet = data.get("magnet") or request.form.get("magnet")
    torrent_url = data.get("torrent_url") or request.form.get("torrent_url")
    category = data.get("category") or request.form.get("category", "")
    media_type = data.get("media_type") or request.form.get("media_type", "")
    count = data.get("count") or request.form.get("count", "1")
    try:
        count = int(count)
    except:
        count = 1

    if not magnet and not torrent_url:
        return jsonify({"error": "No magnet or torrent URL provided"}), 400

    cat_map = config.get("qbittorrent.categories_map", {})
    qb_category = cat_map.get(category, category) if category else ""

    success = False
    results = []
    for i in range(count):
        if magnet:
            s = qb.add_magnet(magnet, qb_category)
            if s:
                notify_torrent_added(magnet.split("&dn=")[1].split("&")[0] if "&dn=" in magnet else "Unknown", magnet, category)
            success = success or s
            results.append({"method": "magnet", "success": s})
        if not success and torrent_url:
            try:
                r = requests.get(torrent_url, headers=_TORRENT_HEADERS, timeout=30)
                tmp = Path(config.get("paths.downloads", "/tmp")) / "tmp.torrent"
                with open(tmp, "wb") as f:
                    f.write(r.content)
                s = qb.add_torrent_file(str(tmp), qb_category)
                tmp.unlink(missing_ok=True)
                success = success or s
                results.append({"method": "torrent_file", "success": s})
            except Exception as e:
                log.error(f"Torrent download error: {e}")
                results.append({"method": "torrent_file", "success": False, "error": str(e)})

    return jsonify({"success": success, "magnet": bool(magnet), "category": category, "count": count, "results": results})


@app.route("/api/torrent/delete", methods=["POST"])
def api_torrent_delete():
    data = request.get_json() or {}
    h = data.get("hash") or request.form.get("hash")
    delete_files = (data.get("delete_files") or request.form.get("delete_files", "false")).lower() == "true"
    if not h:
        return jsonify({"error": "Missing hash"}), 400
    return jsonify({"success": qb.delete_torrent(h, delete_files)})


@app.route("/api/torrent/pause", methods=["POST"])
def api_torrent_pause():
    h = (request.get_json() or {}).get("hash") or request.form.get("hash")
    return jsonify({"success": qb.pause(h) if h else False})


@app.route("/api/torrent/resume", methods=["POST"])
def api_torrent_resume():
    h = (request.get_json() or {}).get("hash") or request.form.get("hash")
    return jsonify({"success": qb.resume(h) if h else False})


@app.route("/api/qb/categories")
def api_qb_categories():
    return jsonify(qb.get_categories())


@app.route("/api/qb/speed")
def api_qb_speed():
    return jsonify(qb.global_speed())


# ── URL / Rapidgator Download ──
@app.route("/api/download/url", methods=["POST"])
def api_download_url():
    data = request.get_json() or {}
    url = data.get("url") or request.form.get("url")
    category = data.get("category") or request.form.get("category", "downloads")
    filename = data.get("filename") or request.form.get("filename")
    if not url:
        return jsonify({"error": "No URL"}), 400
    result = url_downloader.download(url, filename, category)
    if result.get("ok"):
        # Auto-process with ffmpeg
        if config.get("ffmpeg.post_process_downloads", True):
            auto_process_download(result.get("path", ""))
    return jsonify(result)


@app.route("/api/download/queue", methods=["POST"])
def api_download_queue():
    data = request.get_json() or {}
    urls = data.get("urls", []) or request.form.getlist("urls")
    category = data.get("category") or request.form.get("category", "downloads")
    if not urls:
        return jsonify({"error": "No URLs"}), 400
    results = url_downloader.queue_urls(urls, category)
    return jsonify({"ok": True, "count": len(results), "results": results})


# ── Batch Torrent Download ──
@app.route("/api/batch/add", methods=["POST"])
def api_batch_add():
    data = request.get_json() or {}
    items = data.get("items", [])
    if not items:
        return jsonify({"error": "No items"}), 400

    added = []
    for item in items:
        batch_item = BatchItem(
            id=batch_mgr.generate_id(),
            type=item.get("type", "magnet"),
            source=item.get("source", ""),
            title=item.get("title", "Unknown"),
            category=item.get("category", "downloads"),
            media_type=item.get("media_type", "auto"),
            size=item.get("size", "?"),
            provider=item.get("provider", ""),
            metadata=item.get("metadata", {}),
        )
        if batch_mgr.add(batch_item):
            added.append(batch_item.to_dict())

    return jsonify({"ok": True, "added": len(added), "items": added})


@app.route("/api/batch/list")
def api_batch_list():
    status = request.args.get("status")
    if status:
        return jsonify(batch_mgr.get_by_status(status))
    return jsonify(batch_mgr.get_all())


@app.route("/api/batch/clear", methods=["POST"])
def api_batch_clear():
    count = batch_mgr.clear()
    return jsonify({"ok": True, "cleared": count})


@app.route("/api/batch/remove", methods=["POST"])
def api_batch_remove():
    item_id = (request.get_json() or {}).get("id") or request.form.get("id")
    if not item_id:
        return jsonify({"error": "No ID"}), 400
    return jsonify({"ok": batch_mgr.remove(item_id)})


# ── File Upload / Browser ──
@app.route("/api/upload", methods=["POST"])
def api_upload():
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    dest = request.form.get("destination", "downloads")
    auto_sort = request.form.get("sort", "false").lower() == "true"
    media_type = request.form.get("media_type", "auto")

    paths = config.get("paths", {})
    target_dir = Path(paths.get(dest, config.get("paths.downloads", "/tmp/plexarr")))
    target_dir.mkdir(parents=True, exist_ok=True)

    allowed = set(config.get("uploads.allowed_extensions", []))
    suffix = Path(f.filename).suffix.lower()
    if allowed and suffix not in allowed:
        return jsonify({"error": f"Extension {suffix} not allowed"}), 400

    dest_path = target_dir / f.filename
    f.save(dest_path)

    result = str(dest_path)
    if auto_sort and config.get("auto_sort.enabled", True):
        new = process_file(
            str(dest_path),
            config.get("paths.downloads", str(target_dir)),
            media_type,
            config.get("auto_sort.prefer_anime", True),
        )
        if new:
            result = new

    # FFmpeg post-processing
    if config.get("ffmpeg.post_process_downloads", True) and suffix in (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"):
        ff = auto_process_download(result)
        if ff and ff.get("ok"):
            notify_ffmpeg_complete(Path(result).name, ff.get("audio_tracks", 0), ff.get("subtitle_tracks", 0))

    notify_upload(f.filename, dest, os.path.getsize(result))
    return jsonify({"success": True, "path": result, "filename": Path(result).name})


@app.route("/api/upload/wifi", methods=["POST"])
def api_upload_wifi():
    """WiFi upload endpoint — auto-categorizes files into Plex paths.

    Accepts multipart file uploads from any device on the LAN.
    Files are saved to a temporary staging area, then auto-detected
    and moved into the correct Plex library (TV, Movies, Anime, Music).
    No destination parameter required.
    """
    if "file" not in request.files:
        return jsonify({"error": "No file"}), 400

    uploaded = request.files.getlist("file")
    if not uploaded:
        return jsonify({"error": "No files"}), 400

    # Staging directory for incoming WiFi uploads
    paths_cfg = config.get("paths", {})
    staging = Path(paths_cfg.get("downloads", config.get("paths.downloads", "/tmp/plexarr"))) / "wifi_staging"
    staging.mkdir(parents=True, exist_ok=True)

    allowed = set(config.get("uploads.allowed_extensions", []))
    prefer_anime = config.get("auto_sort.prefer_anime", True)
    max_size_mb = config.get("uploads.max_size_mb", 5000)
    max_size = max_size_mb * 1024 * 1024

    results = []
    errors = []

    for f in uploaded:
        if not f.filename:
            continue
        suffix = Path(f.filename).suffix.lower()
        if allowed and suffix not in allowed:
            errors.append({"file": f.filename, "error": f"Extension {suffix} not allowed"})
            continue

        temp_path = staging / f.filename
        f.save(temp_path)

        # Check size limit
        try:
            size = temp_path.stat().st_size
            if size > max_size:
                errors.append({"file": f.filename, "error": f"File exceeds {max_size_mb}MB limit"})
                temp_path.unlink(missing_ok=True)
                continue
        except OSError:
            pass

        # Auto-categorize into Plex path
        try:
            from modules.watch_folder import categorize_file
            final = categorize_file(
                str(temp_path),
                paths_cfg,
                prefer_anime=prefer_anime,
                remove_original=True
            )
            if final:
                results.append({
                    "file": f.filename,
                    "path": final,
                    "type": _guess_media_type_from_path(final),
                    "size": os.path.getsize(final)
                })
                # FFmpeg post-processing
                if suffix in (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"):
                    ff = auto_process_download(final)
                    if ff and ff.get("ok"):
                        notify_ffmpeg_complete(Path(final).name, ff.get("audio_tracks", 0), ff.get("subtitle_tracks", 0))
                notify_upload(f.filename, _guess_media_type_from_path(final), os.path.getsize(final))
            else:
                errors.append({"file": f.filename, "error": "Auto-categorization failed"})
        except Exception as e:
            log.error(f"[WIFI] Categorization error for {f.filename}: {e}")
            errors.append({"file": f.filename, "error": str(e)})

    # Clean up empty staging directory
    try:
        if not any(staging.iterdir()):
            staging.rmdir()
    except OSError:
        pass

    return jsonify({
        "success": len(results) > 0,
        "uploaded_count": len(results),
        "error_count": len(errors),
        "files": results,
        "errors": errors,
    })


def _guess_media_type_from_path(path: str) -> str:
    """Infer media type from the destination path."""
    p = Path(path)
    paths_cfg = config.get("paths", {})
    for key, val in paths_cfg.items():
        try:
            if Path(val).resolve() in p.resolve().parents or Path(val).resolve() == p.resolve().parent:
                return key
        except (OSError, ValueError):
            continue
    return "downloads"


@app.route("/api/upload/wifi/status")
def api_upload_wifi_status():
    """Return available WiFi upload info for the client."""
    paths_cfg = config.get("paths", {})
    staging = Path(paths_cfg.get("downloads", config.get("paths.downloads", "/tmp/plexarr"))) / "wifi_staging"
    return jsonify({
        "enabled": True,
        "max_size_mb": config.get("uploads.max_size_mb", 5000),
        "allowed_extensions": list(config.get("uploads.allowed_extensions", [])),
        "staging_dir": str(staging),
        "server_url": f"http://{request.host}/api/upload/wifi",
    })


@app.route("/api/files")
def api_files():
    root = request.args.get("root", "downloads")
    subpath = request.args.get("subpath", "")
    paths = config.get("paths", {})
    base = Path(paths.get(root, config.get("paths.downloads", "/tmp/plexarr")))
    target = base / subpath if subpath else base
    if not target.exists():
        return jsonify({"error": "Path not found"}), 404
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        return jsonify({"error": "Path traversal blocked"}), 403

    items = []
    for p in sorted(target.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        items.append({
            "name": p.name,
            "is_dir": p.is_dir(),
            "size": p.stat().st_size if p.is_file() else 0,
            "relative": str(p.relative_to(base)).replace("\\", "/"),
            "modified": p.stat().st_mtime,
        })
    return jsonify({"root": root, "path": str(target.relative_to(base)).replace("\\", "/"), "items": items})


@app.route("/api/download")
def api_download():
    root = request.args.get("root", "downloads")
    subpath = request.args.get("subpath", "")
    paths = config.get("paths", {})
    base = Path(paths.get(root, config.get("paths.downloads", "/tmp/plexarr")))
    target = base / subpath
    try:
        target.resolve().relative_to(base.resolve())
    except ValueError:
        abort(403)
    if not target.exists() or target.is_dir():
        abort(404)
    return send_file(target, as_attachment=True, download_name=target.name)


# ── Sort / Rename ──
@app.route("/api/sort", methods=["POST"])
def api_sort():
    data = request.get_json() or {}
    path = data.get("path") or request.form.get("path")
    media_type = data.get("media_type") or request.form.get("media_type", "auto")
    if not path or not Path(path).exists():
        return jsonify({"error": "File not found"}), 404
    new = process_file(
        path,
        config.get("paths.downloads", "/tmp/plexarr"),
        media_type,
        config.get("auto_sort.prefer_anime", True),
    )
    if not new:
        return jsonify({"error": "Sort failed"}), 500
    return jsonify({"success": True, "from": path, "to": new})


@app.route("/api/sort/batch", methods=["POST"])
def api_sort_batch():
    data = request.get_json() or {}
    directory = data.get("directory") or request.form.get("directory")
    if not directory or not Path(directory).is_dir():
        return jsonify({"error": "Directory not found"}), 404
    moved = batch_sort(
        directory,
        config.get("paths.downloads", "/tmp/plexarr"),
        config.get("auto_sort.prefer_anime", True),
    )
    return jsonify({"success": True, "moved_count": len(moved), "files": moved})


# ── Naming Detection ──
@app.route("/api/naming/detect")
def api_naming_detect():
    filename = request.args.get("filename", "").strip()
    if not filename:
        return jsonify({"error": "No filename"}), 400
    variations = detect_variations(filename)
    custom = config.get("naming.variations", [])
    return jsonify({
        "filename": filename,
        "variations": variations,
        "custom_variations": custom,
        "cleaned": strip_all_variations(filename),
        "fully_cleaned": full_strip(filename),
    })


# ── FFmpeg ──
@app.route("/api/ffmpeg/process", methods=["POST"])
def api_ffmpeg_process():
    data = request.get_json() or {}
    path = data.get("path") or request.form.get("path")
    replace = (data.get("replace") or request.form.get("replace", "false")).lower() == "true"
    if not path or not Path(path).exists():
        return jsonify({"error": "File not found"}), 404
    result = ffmpeg_process(path, replace)
    if result.get("ok") and result.get("default_audio_lang"):
        notify_ffmpeg_complete(Path(path).name, result.get("audio_tracks", 0), result.get("subtitle_tracks", 0))
    return jsonify(result)


@app.route("/api/ffmpeg/auto", methods=["POST"])
def api_ffmpeg_auto():
    data = request.get_json() or {}
    path = data.get("path") or request.form.get("path")
    if not path or not Path(path).exists():
        return jsonify({"error": "File not found"}), 404
    result = auto_process_download(path)
    return jsonify(result)


@app.route("/api/ffmpeg/status")
def api_ffmpeg_status():
    """Check if ffmpeg is available."""
    ffmpeg_path = config.get("ffmpeg.path", "ffmpeg")
    found = shutil.which(ffmpeg_path) is not None
    return jsonify({"available": found, "path": ffmpeg_path, "enabled": config.get("ffmpeg.enabled", True)})


# ── Config ──
@app.route("/api/config")
def api_config_get():
    d = config.all()
    d = json.loads(json.dumps(d))
    # Redact secrets
    for section in ["discord", "qbittorrent", "tmdb", "tvdb", "vpn"]:
        if section in d:
            for key in ["webhook_url", "password", "api_key", "token"]:
                if key in d[section]:
                    d[section][key] = "***" if d[section][key] else ""
            # Nested
            if section == "vpn" and "password" in d[section]:
                d[section]["password"] = "***" if d[section]["password"] else ""
            if section == "url_downloader" and "rapidgator" in d.get(section, {}):
                for key in ["password", "api_key"]:
                    if key in d[section]["rapidgator"]:
                        d[section]["rapidgator"][key] = "***" if d[section]["rapidgator"][key] else ""
    return jsonify(d)


@app.route("/api/config", methods=["POST"])
def api_config_post():
    data = request.get_json() or {}
    for k, v in data.items():
        config.set(k, v)
    config.save()
    return jsonify({"success": True, "updated": list(data.keys())})


@app.route("/api/config/raw")
def api_config_raw():
    return jsonify(config.all())


# ── CORS Proxy ──
@app.route("/proxy", methods=["GET", "POST", "PUT", "DELETE", "HEAD"])
def proxy():
    if not config.get("cors_proxy.enabled", True):
        return jsonify({"error": "Proxy disabled"}), 403
    target = request.args.get("url")
    cf_bypass = request.args.get("cf_bypass", "false").lower() == "true"
    if not target or not target.startswith(("http://", "https://")):
        return jsonify({"error": "Invalid URL"}), 400
    try:
        headers = {k: v for k, v in request.headers if k.lower() not in ("host", "origin")}
        body = request.get_data() if request.method in ("POST", "PUT") else None

        if cf_bypass and cf_solver.enabled:
            resp = cf_solver.get(target, timeout=config.get("cors_proxy.timeout", 30))
            if not resp:
                resp = cf_solver.post(target, data=body, timeout=config.get("cors_proxy.timeout", 30))
            if not resp:
                return jsonify({"error": "Cloudflare bypass failed"}), 502
        else:
            resp = requests.request(
                method=request.method,
                url=target,
                headers=headers,
                data=body,
                stream=True,
                timeout=config.get("cors_proxy.timeout", 30),
                allow_redirects=True,
            )

        excluded = {"content-encoding", "transfer-encoding", "content-length"}
        out_headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        return Response(resp.iter_content(8192), status=resp.status_code, headers=out_headers, mimetype=resp.headers.get("content-type", "application/octet-stream"))
    except requests.exceptions.Timeout:
        return jsonify({"error": "Upstream timeout"}), 504
    except requests.exceptions.ConnectionError as e:
        return jsonify({"error": f"Cannot connect: {e}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Screen Stream ──
@app.route("/api/screen/start", methods=["POST"])
def api_screen_start():
    global streamer
    if streamer and streamer._running:
        return jsonify({"success": True, "status": "already_running"})
    streamer = ScreenStreamer(
        fps=config.get("screen_stream.fps", 10),
        quality=config.get("screen_stream.quality", 55),
        scale=config.get("screen_stream.scale", 0.7),
    )
    streamer.start(emit_callback=lambda msg: socketio.emit("screen_frame", msg))
    return jsonify({"success": True, "status": "started"})


@app.route("/api/screen/stop", methods=["POST"])
def api_screen_stop():
    global streamer
    if streamer:
        streamer.stop()
    streamer = None
    return jsonify({"success": True, "status": "stopped"})


@app.route("/api/screen/status")
def api_screen_status():
    return jsonify({"running": streamer is not None and streamer._running})


# ── Remote Control ──
try:
    from pynput.mouse import Controller as MouseController, Button
    from pynput.keyboard import Controller as KeyboardController
    _PYNPUT = True
except ImportError:
    _PYNPUT = False

if _PYNPUT:
    _mouse = MouseController()
    _keyboard = KeyboardController()
else:
    _mouse = None
    _keyboard = None


@app.route("/api/remote/mouse", methods=["POST"])
def remote_mouse():
    if not config.get("remote_control.enabled", False):
        return jsonify({"error": "Remote control disabled"}), 403
    if not _mouse:
        return jsonify({"error": "pynput not installed"}), 500
    data = request.get_json() or {}
    x = data.get("x", request.form.get("x", type=int))
    y = data.get("y", request.form.get("y", type=int))
    action = data.get("action", request.form.get("action", "move"))
    if x is not None and y is not None:
        _mouse.position = (x, y)
    if action == "click":
        _mouse.click(Button.left)
    elif action == "right_click":
        _mouse.click(Button.right)
    elif action == "double_click":
        _mouse.click(Button.left, 2)
    return jsonify({"ok": True})


@app.route("/api/remote/keyboard", methods=["POST"])
def remote_keyboard():
    if not config.get("remote_control.enabled", False):
        return jsonify({"error": "Remote control disabled"}), 403
    if not _keyboard:
        return jsonify({"error": "pynput not installed"}), 500
    text = (request.get_json() or {}).get("text") or request.form.get("text", "")
    if text:
        _keyboard.type(text)
    return jsonify({"ok": True})


# ── VPN ──
@app.route("/api/vpn/status")
def api_vpn_status():
    if not config.get("vpn.enabled", False):
        return jsonify({"enabled": False})
    return jsonify(vpn.status())


@app.route("/api/vpn/connect", methods=["POST"])
def api_vpn_connect():
    if not config.get("vpn.enabled", False):
        return jsonify({"error": "VPN disabled"}), 400
    location = request.form.get("location") or request.json.get("location") if request.json else None
    return jsonify(vpn.connect(location))


@app.route("/api/vpn/disconnect", methods=["POST"])
def api_vpn_disconnect():
    if not config.get("vpn.enabled", False):
        return jsonify({"error": "VPN disabled"}), 400
    return jsonify(vpn.disconnect())


@app.route("/api/vpn/login", methods=["POST"])
def api_vpn_login():
    if not config.get("vpn.enabled", False):
        return jsonify({"error": "VPN disabled"}), 400
    return jsonify(vpn.login())


@app.route("/api/vpn/locations")
def api_vpn_locations():
    if not config.get("vpn.enabled", False):
        return jsonify({"enabled": False})
    return jsonify(vpn.locations())


# ── Cloudflare Solver ──
@app.route("/api/cloudflare/status")
def api_cf_status():
    return jsonify({
        "enabled": cf_solver.enabled,
        "provider": cf_solver.provider,
        "installed": _HAVE_CLOUDSCRAPER,
        "sites": config.get("cloudflare_solver.sites", []),
    })


@app.route("/api/cloudflare/toggle", methods=["POST"])
def api_cf_toggle():
    data = request.get_json() or {}
    enabled = data.get("enabled", True)
    config.set("cloudflare_solver.enabled", enabled)
    return jsonify({"ok": True, "enabled": enabled})


# ── Grafana Dashboard ──
@app.route("/api/grafana/dashboard.json")
def grafana_dashboard():
    return jsonify(GRAFANA_DASHBOARD)


# ── Overseerr / Tautulli Proxy ──
@app.route("/api/overseerr/status")
def overseerr_status():
    if not config.get("overseerr.enabled", False):
        return jsonify({"enabled": False})
    try:
        url = config.get("overseerr.url", "http://localhost:5055") + "/api/v1/status"
        r = requests.get(url, headers={"X-Api-Key": config.get("overseerr.api_key", "")}, timeout=5)
        return jsonify(r.json()) if r.ok else jsonify({"error": "Overseerr unreachable"}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/tautulli/activity")
def tautulli_activity():
    if not config.get("tautulli.enabled", False):
        return jsonify({"enabled": False})
    try:
        url = config.get("tautulli.url", "http://localhost:8181") + "/api/v2"
        r = requests.get(url, params={"apikey": config.get("tautulli.api_key", ""), "cmd": "get_activity"}, timeout=5)
        return jsonify(r.json()) if r.ok else jsonify({"error": "Tautulli unreachable"}), r.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 502


# ── WebSocket Handlers ──
@socketio.on("connect")
def handle_connect():
    emit("status", {"connected": True, "version": "2.1.0"})


@socketio.on("disconnect")
def handle_disconnect():
    pass


@socketio.on("request_torrents")
def handle_request_torrents():
    emit("torrent_list", {"torrents": qb.get_torrents()})


@socketio.on("request_screen")
def handle_request_screen(data):
    if not config.get("screen_stream.enabled", False):
        emit("screen_error", {"msg": "Screen stream disabled in config"})
        return
    global streamer
    if not streamer or not streamer._running:
        streamer = ScreenStreamer(
            fps=config.get("screen_stream.fps", 10),
            quality=config.get("screen_stream.quality", 55),
            scale=config.get("screen_stream.scale", 0.7),
        )
        streamer.start(emit_callback=lambda msg: socketio.emit("screen_frame", msg))
    emit("screen_status", {"running": True})


# ── Usenet / SABnzbd ──
from modules.usenet import sab, nzbgeek

@app.route("/api/sabnzbd/queue")
def api_sab_queue():
    if not sab.enabled:
        return jsonify({"enabled": False})
    return jsonify(sab.queue())


@app.route("/api/sabnzbd/history")
def api_sab_history():
    if not sab.enabled:
        return jsonify({"enabled": False})
    limit = int(request.args.get("limit", 50))
    return jsonify(sab.history(limit))


@app.route("/api/sabnzbd/add", methods=["POST"])
def api_sab_add():
    if not sab.enabled:
        return jsonify({"error": "SABnzbd disabled"}), 400
    data = request.get_json() or {}
    url = data.get("url") or request.form.get("url")
    nzb = data.get("nzb") or request.form.get("nzb")
    category = data.get("category") or request.form.get("category", "")
    filename = data.get("filename") or request.form.get("filename")
    if not url and not nzb:
        return jsonify({"error": "No URL or NZB provided"}), 400
    return jsonify(sab.add_nzb(url=url, nzb=nzb, category=category, filename=filename))


@app.route("/api/sabnzbd/pause", methods=["POST"])
def api_sab_pause():
    if not sab.enabled:
        return jsonify({"error": "SABnzbd disabled"}), 400
    nzo_id = (request.get_json() or {}).get("nzo_id") or request.form.get("nzo_id")
    return jsonify({"success": sab.pause(nzo_id)})


@app.route("/api/sabnzbd/resume", methods=["POST"])
def api_sab_resume():
    if not sab.enabled:
        return jsonify({"error": "SABnzbd disabled"}), 400
    nzo_id = (request.get_json() or {}).get("nzo_id") or request.form.get("nzo_id")
    return jsonify({"success": sab.resume(nzo_id)})


@app.route("/api/sabnzbd/delete", methods=["POST"])
def api_sab_delete():
    if not sab.enabled:
        return jsonify({"error": "SABnzbd disabled"}), 400
    nzo_id = (request.get_json() or {}).get("nzo_id") or request.form.get("nzo_id")
    delete_files = (request.get_json() or {}).get("delete_files", False) or request.form.get("delete_files", "false").lower() == "true"
    return jsonify({"success": sab.delete(nzo_id, delete_files)})


@app.route("/api/sabnzbd/speed")
def api_sab_speed():
    if not sab.enabled:
        return jsonify({"enabled": False})
    return jsonify(sab.speed())


@app.route("/api/nzbgeek/search")
def api_nzbgeek_search():
    if not nzbgeek.enabled:
        return jsonify({"enabled": False})
    q = request.args.get("q", "").strip()
    category = request.args.get("category", "")
    limit = int(request.args.get("limit", 50))
    if not q:
        return jsonify({"error": "No query"}), 400
    return jsonify(nzbgeek.search(q, category, limit))


# ── Watch Folder / Auto-Categorize ──
@app.route("/api/watch/start", methods=["POST"])
def api_watch_start():
    data = request.get_json() or {}
    watch_dir = data.get("watch_dir") or request.form.get("watch_dir", config.get("watch_folder.dir", config.get("paths.downloads", "/tmp/plexarr")))
    interval = int(data.get("interval") or request.form.get("interval", 5))
    name = data.get("name") or request.form.get("name", "default")
    paths_cfg = config.get("paths", {})
    prefer_anime = config.get("auto_sort.prefer_anime", True)
    w = start_watcher(name, watch_dir, paths_cfg, interval, prefer_anime)
    return jsonify({"success": True, "status": w.status()})


@app.route("/api/watch/stop", methods=["POST"])
def api_watch_stop():
    data = request.get_json() or {}
    name = data.get("name") or request.form.get("name", "default")
    ok = stop_watcher(name)
    return jsonify({"success": ok, "running": not ok})


@app.route("/api/watch/status")
def api_watch_status():
    name = request.args.get("name", "default")
    s = watcher_status(name)
    if not s:
        return jsonify({"error": "Watcher not found", "name": name}), 404
    return jsonify(s)


@app.route("/api/watch/list")
def api_watch_list():
    return jsonify(list_watchers())


@app.route("/api/categorize", methods=["POST"])
def api_categorize():
    data = request.get_json() or {}
    filepath = data.get("path") or request.form.get("path")
    if not filepath or not Path(filepath).exists():
        return jsonify({"error": "File not found"}), 404
    paths_cfg = config.get("paths", {})
    prefer_anime = config.get("auto_sort.prefer_anime", True)
    result = categorize_file(filepath, paths_cfg, prefer_anime, remove_original=True)
    if not result:
        return jsonify({"error": "Categorization failed"}), 500
    return jsonify({"success": True, "from": filepath, "to": result, "type": "auto"})


@app.route("/api/categorize/batch", methods=["POST"])
def api_categorize_batch():
    data = request.get_json() or {}
    directory = data.get("directory") or request.form.get("directory")
    if not directory or not Path(directory).is_dir():
        return jsonify({"error": "Directory not found"}), 404
    paths_cfg = config.get("paths", {})
    prefer_anime = config.get("auto_sort.prefer_anime", True)
    moved = categorize_batch(directory, paths_cfg, prefer_anime, remove_original=True)
    return jsonify({"success": True, "moved_count": len(moved), "files": moved})


# ── Main ──
if __name__ == "__main__":
    host = config.get("server.host", "0.0.0.0")
    port = config.get("server.port", 8080)
    debug = config.get("server.debug", False)
    config.ensure_dirs()
    log.info(f"Plexarr v2.1 server starting on {host}:{port}")
    print(f"""
╔══════════════════════════════════════════╗
║           Plexarr V2.1 Server            ║
║  http://{host}:{port:<26}║
╚══════════════════════════════════════════╝
    """)
    socketio.run(app, host=host, port=port, debug=debug, use_reloader=False)
