"""PlexLink V2 — Prometheus /metrics Endpoint and Grafana Dashboard"""
import time
from prometheus_flask_exporter import PrometheusMetrics
from prometheus_client import Counter, Gauge, Histogram, generate_latest, CollectorRegistry
from flask import Blueprint, Response

metrics_bp = Blueprint("metrics_bp", __name__)

# Custom registry
registry = CollectorRegistry()

torrent_added_total = Counter(
    "plexlink_torrent_added_total",
    "Total torrents added",
    ["provider", "category"],
    registry=registry,
)

torrent_completed_total = Counter(
    "plexlink_torrent_completed_total",
    "Total torrents completed",
    ["category"],
    registry=registry,
)

download_speed = Gauge(
    "plexlink_download_speed_bytes",
    "Current total download speed",
    registry=registry,
)

upload_speed = Gauge(
    "plexlink_upload_speed_bytes",
    "Current total upload speed",
    registry=registry,
)

active_torrents = Gauge(
    "plexlink_active_torrents",
    "Number of currently active torrents",
    registry=registry,
)

uploaded_files_total = Counter(
    "plexlink_uploaded_files_total",
    "Total files uploaded via LAN",
    ["destination"],
    registry=registry,
)

search_requests_total = Counter(
    "plexlink_search_requests_total",
    "Total search requests",
    ["provider", "query_type"],
    registry=registry,
)

api_request_duration = Histogram(
    "plexlink_api_request_duration_seconds",
    "API request duration",
    ["endpoint"],
    registry=registry,
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
)


@metrics_bp.route("/metrics")
def metrics():
    return Response(generate_latest(registry), mimetype="text/plain; version=0.0.4; charset=utf-8")


def update_torrent_stats(torrents: list, down_speed: int = 0, up_speed: int = 0):
    active = [t for t in torrents if t.get("state") in ("downloading", "stalledDL", "metaDL", "forcedDL")]
    active_torrents.set(len(active))
    download_speed.set(down_speed)
    upload_speed.set(up_speed)
    for t in torrents:
        if t.get("state") in ("uploading", "stalledUP", "forcedUP") and t.get("progress", 0) >= 100:
            torrent_completed_total.labels(category=t.get("category", "unknown")).inc()


# ── Grafana Dashboard JSON ──
GRAFANA_DASHBOARD = {
    "dashboard": {
        "id": None,
        "uid": "plexlink-v2",
        "title": "PlexLink V2",
        "tags": ["plexlink", "torrents", "media"],
        "timezone": "browser",
        "schemaVersion": 36,
        "refresh": "5s",
        "panels": [
            {
                "id": 1,
                "title": "Active Torrents",
                "type": "stat",
                "targets": [{"expr": "plexlink_active_torrents", "legendFormat": "Active"}],
                "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0},
            },
            {
                "id": 2,
                "title": "Download Speed",
                "type": "graph",
                "targets": [{"expr": "plexlink_download_speed_bytes", "legendFormat": "Down"}],
                "gridPos": {"h": 8, "w": 9, "x": 6, "y": 0},
            },
            {
                "id": 3,
                "title": "Upload Speed",
                "type": "graph",
                "targets": [{"expr": "plexlink_upload_speed_bytes", "legendFormat": "Up"}],
                "gridPos": {"h": 8, "w": 9, "x": 15, "y": 0},
            },
            {
                "id": 4,
                "title": "Torrents Added (by Provider)",
                "type": "bargauge",
                "targets": [{"expr": "sum by (provider) (plexlink_torrent_added_total)", "legendFormat": "{{provider}}"}],
                "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8},
            },
            {
                "id": 5,
                "title": "Files Uploaded",
                "type": "stat",
                "targets": [{"expr": "sum by (destination) (plexlink_uploaded_files_total)", "legendFormat": "{{destination}}"}],
                "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8},
            },
        ],
    },
    "overwrite": False,
}
