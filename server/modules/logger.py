"""Plexarr — Verbose Logger / Debugger

Provides colored, structured logging with verbosity levels and debug mode.
QOL features: file logging, JSON output, log rotation, and performance timing.
"""
import sys
import time
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from modules.config import config

# ANSI color codes
_COLORS = {
    "DEBUG": "\033[36m",    # Cyan
    "INFO": "\033[32m",     # Green
    "WARN": "\033[33m",     # Yellow
    "ERROR": "\033[31m",    # Red
    "CRITICAL": "\033[35m", # Magenta
    "RESET": "\033[0m",
    "DIM": "\033[90m",
}

# Icon codes (using ASCII for console compatibility, no emojis)
_ICONS = {
    "DEBUG": "[DBG]",
    "INFO": "[INF]",
    "WARN": "[WRN]",
    "ERROR": "[ERR]",
    "CRITICAL": "[CRT]",
    "OK": "[OK ]",
    "PENDING": "[...]",
    "DONE": "[OK ]",
    "FAIL": "[FAIL]",
}


class Logger:
    def __init__(self, name: str = "Plexarr"):
        self.name = name
        self.verbose = config.get("server.verbose", False)
        self.debug = config.get("server.debug", False)
        self.log_file = Path("logs") / "plexarr.log"
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self._json_mode = False
        self._timers = {}

    def _write(self, level: str, message: str, color: str = None):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        icon = _ICONS.get(level, f"[{level[:3].upper()}]")
        colored = f"{_COLORS.get(color or level, '')}{icon}{_COLORS['RESET']}"
        dim = f"{_COLORS['DIM']}[{ts}]{_COLORS['RESET']}"

        if self._json_mode:
            line = json.dumps({"timestamp": ts, "level": level, "message": message})
        else:
            line = f"{dim} {colored} {message}"

        # Console output
        if level in ("ERROR", "CRITICAL") or self.verbose or (level == "DEBUG" and self.debug):
            print(line, file=sys.stderr if level in ("ERROR", "CRITICAL") else sys.stdout)

        # File output (always)
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(f"{ts} [{level}] {message}\n")
        except Exception:
            pass

    def debug(self, msg: str):
        if self.debug:
            self._write("DEBUG", msg, "DEBUG")

    def info(self, msg: str):
        self._write("INFO", msg, "INFO")

    def warn(self, msg: str):
        self._write("WARN", msg, "WARN")

    def error(self, msg: str, exc: Exception = None):
        full = msg
        if exc:
            full += f" | {str(exc)}"
        if self.debug and exc:
            full += "\n" + traceback.format_exc()
        self._write("ERROR", full, "ERROR")

    def critical(self, msg: str, exc: Exception = None):
        full = msg
        if exc:
            full += f" | {str(exc)}"
        self._write("CRITICAL", full, "CRITICAL")

    def ok(self, msg: str):
        self._write("OK", f"{_COLORS['OK']}{_ICONS['OK']}{_COLORS['RESET']} {msg}")

    def pending(self, msg: str):
        self._write("PENDING", f"{_COLORS['DIM']}{_ICONS['PENDING']}{_COLORS['RESET']} {msg}")

    def done(self, msg: str):
        self._write("DONE", f"{_COLORS['OK']}{_ICONS['DONE']}{_COLORS['RESET']} {msg}")

    def fail(self, msg: str):
        self._write("FAIL", f"{_COLORS['ERROR']}{_ICONS['FAIL']}{_COLORS['RESET']} {msg}")

    def timer_start(self, name: str):
        self._timers[name] = time.time()
        self.debug(f"Timer '{name}' started")

    def timer_end(self, name: str) -> float:
        if name not in self._timers:
            return 0.0
        elapsed = time.time() - self._timers[name]
        self.debug(f"Timer '{name}' ended: {elapsed:.3f}s")
        del self._timers[name]
        return elapsed

    def config_summary(self):
        self.info(f"Plexarr v2.1 starting...")
        self.info(f"Host: {config.get('server.host', '0.0.0.0')}:{config.get('server.port', 8080)}")
        self.info(f"Debug: {self.debug}, Verbose: {self.verbose}")
        self.info(f"qBittorrent: {config.get('qbittorrent.enabled', False)}")
        self.info(f"TMDB: {bool(config.get('tmdb.api_key', ''))}")
        self.info(f"Discord: {bool(config.get('discord.webhook_url', ''))}")
        self.info(f"VPN: {config.get('vpn.enabled', False)}")
        self.info(f"Cloudflare: {config.get('cloudflare_solver.enabled', False)}")
        self.info(f"FFmpeg: {config.get('ffmpeg.enabled', True)}")


log = Logger()
