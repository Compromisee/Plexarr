"""Plexarr — FFmpeg Post-Processor

Sets default English audio and subtitle tracks via FFmpeg metadata.
Detects multiple naming variations (MediaHub-eng, etc.) and normalizes.
"""
import os
import re
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from modules.config import config


def ffprobe(path: str) -> Optional[Dict]:
    """Run ffprobe and return JSON streams info."""
    ffmpeg_path = config.get("ffmpeg.path", "ffmpeg")
    ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
    try:
        result = subprocess.run(
            [ffprobe_path, "-v", "quiet", "-print_format", "json", "-show_streams", path],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        print(f"[FFmpeg] ffprobe error: {e}")
    return None


def get_audio_sub_streams(data: Dict) -> Tuple[List[Dict], List[Dict]]:
    """Extract audio and subtitle streams from ffprobe output."""
    streams = data.get("streams", [])
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    subs = [s for s in streams if s.get("codec_type") == "subtitle"]
    return audio, subs


def detect_language(stream: Dict) -> str:
    """Detect language from stream metadata. Handles variations like eng, en, english, English, etc."""
    tags = stream.get("tags", {})
    candidates = [
        tags.get("language", ""),
        tags.get("LANGUAGE", ""),
        tags.get("title", ""),
        tags.get("handler_name", ""),
    ]
    for c in candidates:
        c = c.lower().strip()
        if c in ("eng", "en", "english", "und", "en-us", "en-gb", "en_ca"):
            return "eng"
        if c in ("jpn", "ja", "japanese", "jp"):
            return "jpn"
        if c in ("spa", "es", "spanish"):
            return "spa"
        if c in ("fre", "fr", "french"):
            return "fre"
        if c in ("ger", "de", "german"):
            return "ger"
        if c in ("ita", "it", "italian"):
            return "ita"
        if c in ("por", "pt", "portuguese"):
            return "por"
        if c in ("rus", "ru", "russian"):
            return "rus"
    # Try to detect from title tags like "MediaHub - eng" or "[English]"
    title = tags.get("title", "")
    if re.search(r'\beng\b|\benglish\b|\bEng\b|\bEnglish\b', title, re.I):
        return "eng"
    if re.search(r'\bjpn\b|\bjapanese\b', title, re.I):
        return "jpn"
    return "und"


def build_ffmpeg_command(path: str, audio: List[Dict], subs: List[Dict], out_path: str) -> List[str]:
    """Build FFmpeg command to set default English audio and subs."""
    ffmpeg_path = config.get("ffmpeg.path", "ffmpeg")
    cmd = [ffmpeg_path, "-y", "-i", path, "-map", "0"]

    default_audio = config.get("ffmpeg.default_audio_lang", "eng")
    default_sub = config.get("ffmpeg.default_subtitle_lang", "eng")
    wanted = set(config.get("ffmpeg.wanted_langs", ["eng", "jpn"]))
    strip_unwanted = config.get("ffmpeg.strip_unwanted_langs", False)

    # Find best audio track index
    audio_idx = 0
    best_audio_stream = None
    for i, a in enumerate(audio):
        lang = detect_language(a)
        if lang == default_audio:
            best_audio_stream = i
            break
        if best_audio_stream is None:
            best_audio_stream = i
    if best_audio_stream is not None:
        cmd += [f"-disposition:a:{best_audio_stream}", "default"]
        for i in range(len(audio)):
            if i != best_audio_stream:
                cmd += [f"-disposition:a:{i}", "none"]

    # Find best subtitle track
    if subs:
        best_sub = None
        for i, s in enumerate(subs):
            lang = detect_language(s)
            if lang == default_sub:
                best_sub = i
                break
        if best_sub is None and subs:
            best_sub = 0
        for i in range(len(subs)):
            if i == best_sub:
                cmd += [f"-disposition:s:{i}", "default"]
            else:
                cmd += [f"-disposition:s:{i}", "none"]

    # Strip unwanted tracks if enabled
    if strip_unwanted and wanted:
        # Re-map: only keep audio/subs in wanted langs
        # For simplicity, this is a full remap approach
        cmd = [ffmpeg_path, "-y", "-i", path]
        # Map video
        cmd += ["-map", "0:v:0"]
        # Map matching audio
        audio_map_count = 0
        for i, a in enumerate(audio):
            if detect_language(a) in wanted:
                cmd += ["-map", f"0:a:{i}"]
                cmd += [f"-disposition:a:{audio_map_count}", "default" if detect_language(a) == default_audio else "none"]
                audio_map_count += 1
        # Map matching subs
        sub_map_count = 0
        for i, s in enumerate(subs):
            if detect_language(s) in wanted:
                cmd += ["-map", f"0:s:{i}"]
                cmd += [f"-disposition:s:{sub_map_count}", "default" if detect_language(s) == default_sub else "none"]
                sub_map_count += 1

    cmd += ["-c", "copy", out_path]
    return cmd


def process_file(path: str, replace_original: bool = False) -> Dict:
    """Process a media file with FFmpeg to set default English tracks."""
    if not config.get("ffmpeg.enabled", True):
        return {"ok": False, "error": "FFmpeg disabled"}

    ffmpeg_path = config.get("ffmpeg.path", "ffmpeg")
    if not Path(ffmpeg_path).exists() and not shutil.which(ffmpeg_path):
        return {"ok": False, "error": f"FFmpeg not found: {ffmpeg_path}"}

    data = ffprobe(path)
    if not data:
        return {"ok": False, "error": "ffprobe failed"}

    audio, subs = get_audio_sub_streams(data)
    if not audio:
        return {"ok": False, "error": "No audio streams found"}

    p = Path(path)
    out_path = str(p.parent / (p.stem + ".processed" + p.suffix))

    cmd = build_ffmpeg_command(path, audio, subs, out_path)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr, "command": " ".join(cmd)}

        if replace_original:
            os.replace(out_path, path)
            out_path = path

        return {
            "ok": True,
            "output": out_path,
            "audio_tracks": len(audio),
            "subtitle_tracks": len(subs),
            "default_audio_lang": config.get("ffmpeg.default_audio_lang", "eng"),
            "default_sub_lang": config.get("ffmpeg.default_subtitle_lang", "eng"),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


def auto_process_download(path: str) -> Dict:
    """Auto-process a newly downloaded file if ffmpeg.post_process_downloads is True."""
    if not config.get("ffmpeg.post_process_downloads", True):
        return {"ok": False, "skipped": True}
    ext = Path(path).suffix.lower()
    if ext not in (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts"):
        return {"ok": False, "skipped": True, "reason": "Not a video file"}
    return process_file(path, replace_original=True)


import shutil
