"""Plexarr Client — Server Discovery (mDNS/SSDP/HTTP fallback)"""
import socket
import threading
import time
import requests
from typing import List, Dict, Optional


class ServerDiscovery:
    def __init__(self, timeout: int = 3):
        self.timeout = timeout
        self.results: List[Dict] = []

    def discover(self) -> List[Dict]:
        self.results = []
        threads = [
            threading.Thread(target=self._scan_lan, daemon=True),
            threading.Thread(target=self._ssdp_search, daemon=True),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=self.timeout + 1)
        return self.results

    def _scan_lan(self):
        """Scan common LAN IPs for port 8080."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            base = ".".join(local_ip.split(".")[:3])
        except Exception:
            base = "192.168.1"

        for i in range(1, 255):
            ip = f"{base}.{i}"
            try:
                r = requests.get(f"http://{ip}:8080/health", timeout=1.5)
                if r.status_code == 200:
                    data = r.json()
                    self.results.append({
                        "ip": ip,
                        "port": 8080,
                        "url": f"http://{ip}:8080",
                        "version": data.get("version", "?"),
                        "method": "http_scan",
                    })
            except Exception:
                pass

    def _ssdp_search(self):
        """Simple SSDP search for Plexarr server (optional)."""
        try:
            msg = (
                "M-SEARCH * HTTP/1.1\r\n"
                "HOST: 239.255.255.250:1900\r\n"
                "MAN: \"ssdp:discover\"\r\n"
                "MX: 2\r\n"
                "ST: urn:plexarr:device:server:1\r\n\r\n"
            )
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.settimeout(self.timeout)
            sock.sendto(msg.encode(), ("239.255.255.250", 1900))
            try:
                while True:
                    data, addr = sock.recvfrom(1024)
                    self.results.append({"ip": addr[0], "port": 8080, "url": f"http://{addr[0]}:8080", "method": "ssdp"})
            except socket.timeout:
                pass
        except Exception:
            pass


def discover_servers(timeout: int = 3) -> List[Dict]:
    return ServerDiscovery(timeout).discover()
