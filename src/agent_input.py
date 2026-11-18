"""Low-latency input over the device agent's raw TCP channel."""

from __future__ import annotations

import socket
import threading
from typing import Optional


class AgentInputError(RuntimeError):
    pass


class AgentInput:
    def __init__(self, address: str, timeout: float = 1.0):
        host, _, port = address.rpartition(":")
        if not host:
            host, port = address, "8767"
        self.address = (host, int(port))
        self.timeout = timeout
        self.sock: Optional[socket.socket] = None
        self.last_error = ""
        self._connect()

    def _connect(self) -> None:
        self.close()
        try:
            sock = socket.create_connection(self.address, timeout=self.timeout)
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            sock.settimeout(None)
        except OSError as exc:
            raise AgentInputError(f"连接输入 agent 失败: {exc}") from exc
        self.sock = sock

    def _command(self, line: str) -> None:
        sock = self.sock
        if sock is None:
            self._connect()
            sock = self.sock
        try:
            sock.sendall((line + "\n").encode("ascii"))
        except OSError as exc:
            self.close()
            raise AgentInputError(f"输入 agent 断开: {exc}") from exc

    def tap(self, x: int, y: int) -> None:
        self._command(f"tap {int(x)} {int(y)}")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 200) -> None:
        self._command(
            f"swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}"
        )

    def close(self) -> None:
        sock = self.sock
        self.sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
