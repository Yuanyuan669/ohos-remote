"""Thin wrapper around the OpenHarmony hdc CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import uuid
from typing import Optional

CREATE_NO_WINDOW = 0x08000000


class HdcError(RuntimeError):
    pass


def find_hdc() -> str:
    env = os.environ.get("OHOS_HDC")
    if env and os.path.isfile(env):
        return env
    found = shutil.which("hdc")
    if found:
        return found
    candidates = [
        r"D:\ohos-tools\sdk\openharmony-4.0-Release\toolchains\hdc.exe",
        r"D:\ohos-tools\sdk\openharmony\toolchains\hdc.exe",
        os.path.expanduser(r"~\ohos-sdk\windows\toolchains\hdc.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    raise HdcError("hdc.exe not found; set OHOS_HDC or install the SDK toolchains")


class Hdc:
    def __init__(self, exe: Optional[str] = None, target: Optional[str] = None):
        self.exe = exe or find_hdc()
        self.target = target
        self._lock = threading.Lock()
        self._remote_seq = 0

    def _base(self) -> list[str]:
        base = [self.exe]
        if self.target:
            base += ["-t", self.target]
        return base

    def run(self, args: list[str], timeout: float = 20.0) -> str:
        cmd = self._base() + args
        with self._lock:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                creationflags=CREATE_NO_WINDOW,
            )
        if proc.returncode != 0:
            raise HdcError((proc.stderr or proc.stdout or "hdc failed").strip())
        return proc.stdout

    def shell(self, command: str, timeout: float = 20.0) -> str:
        return self.run(["shell", command], timeout=timeout)

    def list_targets(self) -> list[str]:
        out = self.run(["list", "targets"], timeout=10)
        targets: list[str] = []
        for line in out.splitlines():
            line = line.strip()
            if not line or "Empty" in line:
                continue
            parts = line.split()
            if parts:
                targets.append(parts[0])
        return targets

    def file_recv(self, remote: str, local: str, timeout: float = 30.0) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(local)), exist_ok=True)
        self.run(["file", "recv", remote, local], timeout=timeout)

    def file_send(self, local: str, remote: str, timeout: float = 120.0) -> None:
        self.run(["file", "send", local, remote], timeout=timeout)

    def snapshot_remote(self, local: str, timeout: float = 30.0) -> None:
        self._remote_seq = (self._remote_seq + 1) % 100000
        remote = f"/data/local/tmp/ohosremote_{uuid.uuid4().hex}.jpeg"
        try:
            self.shell(f"snapshot_display -f {remote}", timeout=timeout)
            self.file_recv(remote, local)
        finally:
            try:
                self.shell(f"rm -f {remote}", timeout=5)
            except HdcError:
                pass

    def tap(self, x: int, y: int) -> None:
        self.shell(f"uinput -T -c {x} {y} 10")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 200) -> None:
        self.shell(f"uinput -T -m {x1} {y1} {x2} {y2} {duration_ms}")

    def input_text(self, x: int, y: int, text: str) -> None:
        safe = text.replace("\n", " ")
        self.shell(f"uitest uiInput inputText {x} {y} '{safe}'")

    def key_event(self, code: int) -> None:
        self.shell(f"uinput -K -d {code} -u {code}")

    def model(self) -> str:
        try:
            return self.shell("param get const.product.model", timeout=5).strip()
        except HdcError:
            return ""
