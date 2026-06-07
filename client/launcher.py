"""Plexarr Client — Debug Launcher

Usage:
    python launcher.py --server http://192.168.1.50:8080 --verbose --debug
    python launcher.py --server auto --tray --minimize
    python launcher.py --profile home
"""
import argparse
import sys
import os
import logging
import logging.handlers
from pathlib import Path
from client.config import client_config, CONFIG_DIR


def setup_logging(verbose: bool = False, log_file: str = None, max_size_mb: int = 10, show_console: bool = False):
    level = logging.DEBUG if verbose else logging.INFO
    log_fmt = "[%(asctime)s] %(levelname)-8s %(name)s %(message)s"
    handlers = []

    if show_console:
        handlers.append(logging.StreamHandler(sys.stdout))

    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        rot = logging.handlers.RotatingFileHandler(
            log_path, maxBytes=max_size_mb * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        handlers.append(rot)

    if not handlers:
        handlers.append(logging.StreamHandler(sys.stdout))

    logging.basicConfig(level=level, format=log_fmt, handlers=handlers, force=True)

    # Suppress noisy libraries
    for name in ("urllib3", "requests", "engineio", "socketio", "pystray"):
        logging.getLogger(name).setLevel(logging.WARNING if not verbose else logging.DEBUG)

    return logging.getLogger("PlexarrClient")


def parse_args():
    parser = argparse.ArgumentParser(description="Plexarr Client Launcher")
    parser.add_argument("--server", default="auto", help="Server URL or 'auto' to discover")
    parser.add_argument("--profile", default=None, help="Use named profile from config")
    parser.add_argument("--width", type=int, default=None, help="Window width")
    parser.add_argument("--height", type=int, default=None, help="Window height")
    parser.add_argument("--no-tray", action="store_true", help="Disable system tray")
    parser.add_argument("--minimize", action="store_true", help="Start minimized to tray")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug mode (F12 dev tools)")
    parser.add_argument("--portable", action="store_true", help="Portable mode (store config next to executable)")
    parser.add_argument("--log-file", default=None, help="Custom log file path")
    parser.add_argument("--theme", choices=["dark", "light", "system"], default=None, help="UI theme")
    parser.add_argument("--discover", action="store_true", help="Run discovery and exit")
    parser.add_argument("--export-config", default=None, help="Export config to file and exit")
    parser.add_argument("--import-config", default=None, help="Import config from file and exit")
    return parser.parse_args()


def main():
    args = parse_args()

    if args.portable:
        exe_dir = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent
        os.environ["PLEXARR_CONFIG_DIR"] = str(exe_dir / "plexarr_config")
        client_config._data["portable"] = True
        client_config.save()

    cfg = client_config
    log_file = args.log_file or cfg.get("debug.log_file", str(CONFIG_DIR / "client.log"))
    setup_logging(
        verbose=args.verbose or cfg.get("debug.verbose", False),
        log_file=log_file,
        max_size_mb=cfg.get("debug.max_log_size_mb", 10),
        show_console=args.verbose or cfg.get("debug.show_console", False),
    )
    log = logging.getLogger("PlexarrClient")
    log.info("Plexarr Client Launcher starting...")

    if args.import_config:
        client_config.import_json(args.import_config)
        log.info(f"Config imported from {args.import_config}")
        return

    if args.export_config:
        client_config.export_json(args.export_config)
        log.info(f"Config exported to {args.export_config}")
        return

    if args.discover:
        from client.discovery import discover_servers
        log.info("Discovering servers...")
        servers = discover_servers()
        for s in servers:
            log.info(f"  Found: {s['url']} (v{s.get('version', '?')})")
        return

    if args.profile:
        profiles = cfg.get("profiles", [])
        for i, p in enumerate(profiles):
            if p.get("name") == args.profile:
                cfg.set("active_server", i)
                log.info(f"Using profile: {args.profile}")
                break

    server = args.server
    if server == "auto":
        active = cfg.get_active_server()
        if active:
            server = active.get("url", "http://localhost:8080")
        else:
            server = "http://localhost:8080"

    log.info(f"Target server: {server}")

    # Launch main client
    from client.main import run_client
    run_client(
        server_url=server,
        width=args.width or cfg.get("ui.window_width", 1440),
        height=args.height or cfg.get("ui.window_height", 900),
        debug=args.debug or cfg.get("debug.remote_debug", False),
        no_tray=args.no_tray,
        minimize=args.minimize,
        theme=args.theme or cfg.get("theme", "dark"),
    )


if __name__ == "__main__":
    main()
