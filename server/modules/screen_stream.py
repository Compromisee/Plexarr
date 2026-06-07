"""PlexLink V2 — Screen Capture Stream (SocketIO)"""
import base64
import io
import threading
import time
from queue import Queue, Empty
from mss import mss
from PIL import Image


class ScreenStreamer:
    def __init__(self, fps: int = 10, quality: int = 55, scale: float = 0.7):
        self.fps = max(1, min(fps, 30))
        self.quality = max(10, min(quality, 95))
        self.scale = max(0.1, min(scale, 1.0))
        self._running = False
        self._capture_thread = None
        self._queue = Queue(maxsize=2)

    def start(self, emit_callback=None):
        if self._running:
            return
        self._running = True
        self._emit_callback = emit_callback
        self._capture_thread = threading.Thread(target=self._loop, daemon=True)
        self._capture_thread.start()
        if emit_callback:
            threading.Thread(target=self._broadcast_loop, daemon=True).start()

    def _loop(self):
        sct = mss()
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        interval = 1.0 / self.fps
        while self._running:
            t0 = time.time()
            try:
                img = sct.grab(monitor)
                pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
                if self.scale != 1.0:
                    new_size = (int(pil.width * self.scale), int(pil.height * self.scale))
                    pil = pil.resize(new_size, Image.Resampling.LANCZOS)
                buf = io.BytesIO()
                pil.save(buf, format="JPEG", quality=self.quality, optimize=True)
                b64 = base64.b64encode(buf.getvalue()).decode()
                payload = {"type": "screen", "data": b64, "ts": time.time()}
                if not self._queue.full():
                    self._queue.put_nowait(payload)
            except Exception as e:
                print(f"[Screen] Capture error: {e}")
            delay = max(0.0, interval - (time.time() - t0))
            time.sleep(delay)

    def _broadcast_loop(self):
        while self._running:
            try:
                msg = self._queue.get(timeout=1.0)
                if self._emit_callback:
                    self._emit_callback(msg)
            except Empty:
                continue

    def stop(self):
        self._running = False
        if self._capture_thread:
            self._capture_thread.join(timeout=2.0)

    def get_frame(self):
        try:
            return self._queue.get_nowait()
        except Empty:
            return None
