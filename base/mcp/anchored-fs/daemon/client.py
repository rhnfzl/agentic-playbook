"""Thin synchronous Unix-socket client for hook scripts. ~5ms RTT."""

from __future__ import annotations
import json
import os
import socket


def call(socket_path: str, request: dict, timeout: float = 2.0) -> dict:
    # Resolve symlinks so connect() never receives a path longer than the
    # OS AF_UNIX sun_path limit (~103 bytes on macOS).
    connect_path = os.path.realpath(socket_path)
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(connect_path)
        s.sendall((json.dumps(request) + "\n").encode())
        chunks = []
        while True:
            chunk = s.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b"\n" in chunk:
                break
        return json.loads(b"".join(chunks).decode().splitlines()[0])
    finally:
        s.close()
