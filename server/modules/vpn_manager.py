"""Plexarr — VPN Manager (Windscribe Support)

Controls Windscribe CLI to connect/disconnect/route traffic through VPN.
Can be toggled per-download or globally via config.
"""
import subprocess
import os
import re
from typing import Optional, Dict
from modules.config import config


class VPNManager:
    def __init__(self):
        self.enabled = config.get("vpn.enabled", False)
        self.provider = config.get("vpn.provider", "windscribe")
        self.cli_path = config.get("vpn.cli_path", "/usr/bin/windscribe")
        self.username = config.get("vpn.username", "")
        self.password = config.get("vpn.password", "")
        self.location = config.get("vpn.location", "best")
        self.kill_switch = config.get("vpn.kill_switch", False)

    def _run(self, cmd: list, timeout: int = 30) -> tuple:
        if not self.enabled:
            return ("", "VPN disabled", 1)
        try:
            result = subprocess.run(
                [self.cli_path] + cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            return (result.stdout, result.stderr, result.returncode)
        except FileNotFoundError:
            return ("", f"CLI not found at {self.cli_path}", 1)
        except Exception as e:
            return ("", str(e), 1)

    def login(self) -> Dict:
        if not self.username or not self.password:
            return {"ok": False, "error": "No credentials in config"}
        out, err, code = self._run(["login", self.username, self.password])
        if code == 0 and "Logged in" in out:
            return {"ok": True, "msg": out.strip()}
        return {"ok": False, "error": err or out}

    def connect(self, location: str = None) -> Dict:
        loc = location or self.location
        out, err, code = self._run(["connect", loc])
        if code == 0:
            return {"ok": True, "location": loc, "msg": out.strip()}
        return {"ok": False, "error": err or out}

    def disconnect(self) -> Dict:
        out, err, code = self._run(["disconnect"])
        if code == 0:
            return {"ok": True, "msg": out.strip()}
        return {"ok": False, "error": err or out}

    def status(self) -> Dict:
        out, err, code = self._run(["status"])
        connected = "CONNECTED" in out.upper() or "Connect" in out
        ip_match = re.search(r'IP: ([\d.]+)', out)
        loc_match = re.search(r'Location: ([\w\s-]+)', out)
        return {
            "ok": code == 0,
            "connected": connected,
            "ip": ip_match.group(1) if ip_match else None,
            "location": loc_match.group(1).strip() if loc_match else None,
            "raw": out,
            "error": err if err else None
        }

    def locations(self) -> Dict:
        out, err, code = self._run(["locations"])
        if code != 0:
            return {"ok": False, "error": err}
        lines = [l.strip() for l in out.splitlines() if l.strip() and not l.startswith("-")]
        return {"ok": True, "locations": lines}

    def toggle(self, state: bool) -> Dict:
        if state:
            return self.connect()
        else:
            return self.disconnect()


vpn = VPNManager()
