"""Plexarr — Batch Download Manager

Queue system for batch-adding torrents, magnets, and URLs.
Allows selecting multiple items from search results and queuing them.
"""
import time
import threading
from typing import Dict, List, Optional
from queue import Queue, Empty
from dataclasses import dataclass, field, asdict

from modules.config import config
from modules.qbittorrent import qb
from modules.url_downloader import url_downloader
from modules.discord_webhook import notify_torrent_added, notify_error


@dataclass
class BatchItem:
    id: str
    type: str  # "magnet", "torrent", "url", "rapidgator"
    source: str  # the actual URL/magnet
    title: str
    category: str = "downloads"
    media_type: str = "auto"
    status: str = "queued"  # queued, downloading, completed, failed
    error: Optional[str] = None
    size: str = "?"
    provider: str = ""
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


class BatchDownloader:
    def __init__(self):
        self.max_queue = config.get("batch_download.max_queue", 50)
        self.auto_start = config.get("batch_download.auto_start", True)
        self._queue: Queue = Queue(maxsize=self.max_queue)
        self._items: Dict[str, BatchItem] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def add(self, item: BatchItem) -> bool:
        with self._lock:
            if len(self._items) >= self.max_queue:
                return False
            self._items[item.id] = item
        try:
            self._queue.put_nowait(item)
            if self.auto_start and not self._running:
                self.start()
            return True
        except Exception:
            with self._lock:
                item.status = "failed"
                item.error = "Queue full"
            return False

    def add_batch(self, items: List[BatchItem]) -> List[bool]:
        return [self.add(item) for item in items]

    def remove(self, item_id: str) -> bool:
        with self._lock:
            if item_id in self._items:
                self._items[item_id].status = "removed"
                return True
            return False

    def clear(self) -> int:
        with self._lock:
            count = len(self._items)
            self._items.clear()
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except Empty:
                    break
            return count

    def get_all(self) -> List[Dict]:
        with self._lock:
            return [item.to_dict() for item in self._items.values()]

    def get_by_status(self, status: str) -> List[Dict]:
        with self._lock:
            return [item.to_dict() for item in self._items.values() if item.status == status]

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._process_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _process_loop(self):
        while self._running:
            try:
                item = self._queue.get(timeout=1.0)
            except Empty:
                continue

            with self._lock:
                if item.id not in self._items:
                    continue
                self._items[item.id].status = "downloading"

            try:
                if item.type == "magnet":
                    cat_map = config.get("qbittorrent.categories_map", {})
                    qb_category = cat_map.get(item.category, item.category)
                    success = qb.add_magnet(item.source, qb_category)
                    if success:
                        notify_torrent_added(item.title, item.source, item.category, item.size)
                elif item.type == "torrent":
                    # Would need to download .torrent first then add
                    pass
                elif item.type in ("url", "rapidgator"):
                    result = url_downloader.download(item.source, category=item.category)
                    success = result.get("ok", False)
                else:
                    success = False

                with self._lock:
                    if item.id in self._items:
                        self._items[item.id].status = "completed" if success else "failed"
                        if not success:
                            self._items[item.id].error = "Download failed"
            except Exception as e:
                with self._lock:
                    if item.id in self._items:
                        self._items[item.id].status = "failed"
                        self._items[item.id].error = str(e)

    def generate_id(self) -> str:
        return f"batch_{int(time.time()*1000)}_{threading.current_thread().ident}"


batch_mgr = BatchDownloader()
