"""H264-over-TCP stream decoder using an ffmpeg subprocess."""

from __future__ import annotations

import os
import queue
import shutil
import socket
import subprocess
import threading
import time
from typing import Optional

from PIL import Image


def find_ffmpeg(explicit: Optional[str] = None) -> str:
    if explicit:
        return explicit
    try:
        import imageio_ffmpeg  # type: ignore

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if exe:
        return exe
    raise RuntimeError("ffmpeg not found; install imageio-ffmpeg or pass --ffmpeg")


class H264Stream(threading.Thread):
    """Connect to device TCP H264 (Annex-B), decode with ffmpeg, emit PIL frames."""

    def __init__(self, endpoint: str, size: tuple[int, int], frames: "queue.Queue[tuple[str, object]]",
                 ffmpeg_exe: Optional[str] = None, connect_timeout: float = 3.0):
        super().__init__(daemon=True)
        host, _, port = endpoint.partition(":")
        self.host = host
        self.port = int(port or "8766")
        self.width, self.height = size
        self.frame_bytes = self.width * self.height * 3
        self.frames = frames
        self.ffmpeg_exe = find_ffmpeg(ffmpeg_exe)
        self.connect_timeout = connect_timeout
        self._stop_evt = threading.Event()
        self._sock: Optional[socket.socket] = None
        self._proc: Optional[subprocess.Popen] = None

    def stop(self) -> None:
        self._stop_evt.set()
        try:
            if self._sock is not None:
                self._sock.close()
        except OSError:
            pass
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass

    def run(self) -> None:
        while not self._stop_evt.is_set():
            try:
                self._run_once()
            except Exception as exc:
                self._put(("error", f"h264: {exc}"))
            finally:
                self._cleanup()
            if not self._stop_evt.is_set():
                self._stop_evt.wait(1.0)

    def _run_once(self) -> None:
        self._sock = socket.create_connection((self.host, self.port), self.connect_timeout)
        self._sock.settimeout(0.5)
        cmd = [
            self.ffmpeg_exe, "-hide_banner", "-loglevel", "error",
            "-f", "h264", "-i", "pipe:0",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1",
        ]
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self._proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, creationflags=creationflags,
        )
        writer = threading.Thread(target=self._pump, daemon=True)
        writer.start()
        buf = bytearray()
        assert self._proc.stdout is not None
        while not self._stop_evt.is_set():
            chunk = self._proc.stdout.read(self.frame_bytes - len(buf))
            if not chunk:
                raise RuntimeError("ffmpeg exited")
            buf.extend(chunk)
            if len(buf) == self.frame_bytes:
                img = Image.frombytes("RGB", (self.width, self.height), bytes(buf))
                self._put(("frame", img))
                buf.clear()

    def _pump(self) -> None:
        assert self._sock is not None and self._proc is not None and self._proc.stdin is not None
        while not self._stop_evt.is_set():
            try:
                data = self._sock.recv(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            try:
                self._proc.stdin.write(data)
                self._proc.stdin.flush()
            except (OSError, ValueError):
                break
        try:
            self._proc.stdin.close()
        except (OSError, ValueError):
            pass

    def _cleanup(self) -> None:
        if self._proc is not None:
            try:
                self._proc.kill()
            except OSError:
                pass
            self._proc = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None

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
