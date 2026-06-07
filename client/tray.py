"""Plexarr Client — System Tray Integration"""
import os
import sys
import webview
import pystray
from PIL import Image, ImageDraw
from typing import Callable, Optional


def create_icon(size=64, color=(0, 212, 170)):
    """Generate a simple Plexarr icon."""
    img = Image.new("RGB", (size, size), (5, 5, 8))
    draw = ImageDraw.Draw(img)
    margin = size // 8
    draw.rectangle([margin, margin, size - margin, size - margin], fill=color, outline=(255, 255, 255), width=2)
    draw.text((size // 3, size // 3), "P", fill=(5, 5, 8))
    return img


class TrayManager:
    def __init__(self, on_toggle: Callable, on_search: Callable, on_quit: Callable, window: Optional[webview.Window] = None):
        self.on_toggle = on_toggle
        self.on_search = on_search
        self.on_quit = on_quit
        self.window = window
        self.icon: Optional[pystray.Icon] = None

    def _setup_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Toggle Window", self._on_toggle),
            pystray.MenuItem("Quick Search", self._on_search),
            pystray.MenuItem("Separator", pystray.Menu.SEPARATOR),
            pystray.MenuItem("Quit", self._on_quit),
        )

    def _on_toggle(self, icon, item):
        if self.on_toggle:
            self.on_toggle()

    def _on_search(self, icon, item):
        if self.on_search:
            self.on_search()

    def _on_quit(self, icon, item):
        if self.on_quit:
            self.on_quit()
        icon.stop()

    def start(self):
        self.icon = pystray.Icon("Plexarr", create_icon(), "Plexarr Client", self._setup_menu())
        threading.Thread(target=self.icon.run, daemon=True).start()

    def stop(self):
        if self.icon:
            self.icon.stop()

    def notify(self, title: str, message: str, duration: int = 5):
        if self.icon:
            self.icon.notify(message, title)


import threading
