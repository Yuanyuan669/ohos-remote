"""Background screen capture loop using hdc snapshot_display."""

from __future__ import annotations

import io
import os
import queue
import tempfile
import threading
import time
from typing import Optional

from PIL import Image

from hdc import Hdc, HdcError


class Mirror(threading.Thread):
    def __init__(self, hdc: Hdc, frames: "queue.Queue[tuple[str, object]]", interval: float = 0.05):
        super().__init__(daemon=True)
        self.hdc = hdc
        self.frames = frames
        self.interval = max(0.0, interval)
        self._stop = threading.Event()
        self._tmpdir = os.path.join(tempfile.gettempdir(), "ohos-remote")
        os.makedirs(self._tmpdir, exist_ok=True)
        self._path = os.path.join(self._tmpdir, "frame.jpeg")

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            start = time.time()
            try:
                self.hdc.snapshot_remote(self._path)
                with open(self._path, "rb") as fp:
                    data = fp.read()
                img = Image.open(io.BytesIO(data))
                img.load()
                self._put(("frame", img.convert("RGB")))
            except (HdcError, OSError, ValueError) as exc:
                self._put(("error", str(exc)))
                time.sleep(0.6)
            elapsed = time.time() - start
            wait = self.interval - elapsed
            if wait > 0:
                self._stop.wait(wait)

    def _put(self, item: tuple[str, object]) -> None:
        try:
            while True:
                self.frames.get_nowait()
        except queue.Empty:
            pass
        try:
            self.frames.put_nowait(item)
        except queue.Full:
            pass
