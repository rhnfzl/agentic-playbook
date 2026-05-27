"""Subprocess proxy + supervisor for @modelcontextprotocol/server-filesystem."""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time


class StockFilesystemError(Exception):
    """Raised when the upstream stock filesystem MCP server returns a JSON-RPC error."""


# Pin version per Phase 0.1 spike finding 1 (avoids Node v26 stale-cache ESM failure).
# Correct invocation form: `npx -y <pkg@ver> <dirs>` — the binary in the published
# package is registered as the package name (via "bin" in package.json), not as a
# separate "server-filesystem" command, so the "--package <pkg> server-filesystem"
# split form fails with "command not found".
STOCK_PACKAGE_VERSION = "@modelcontextprotocol/server-filesystem@2026.1.14"


class StockFilesystemProxy:
    MAX_RESTARTS = 3
    RESTART_WINDOW_SECONDS = 60.0

    def __init__(self, allowed_dirs: list[str]) -> None:
        self.allowed_dirs = allowed_dirs
        self.process: asyncio.subprocess.Process | None = None
        self._pgid: int | None = None  # process group ID for whole-tree kill
        self.request_id = 0
        self.restart_count = 0
        self.restart_window_start = time.monotonic()
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        args = [
            "npx",
            "-y",
            STOCK_PACKAGE_VERSION,
            *self.allowed_dirs,
        ]
        # setsid puts the subprocess in its own process group so we can kill the
        # entire npm+node subtree (not just the npm wrapper) via os.killpg.
        self.process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            start_new_session=True,
        )
        self._pgid = self.process.pid  # setsid makes the child the group leader
        await self._initialize()

    async def _initialize(self) -> None:
        self.request_id = 0
        await self._raw_call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "anchored-fs-proxy", "version": "0.1.0"},
            },
        )
        assert self.process is not None
        assert self.process.stdin is not None
        self.process.stdin.write(
            (
                json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
                + "\n"
            ).encode()
        )
        await self.process.stdin.drain()

    async def _raw_call(self, method: str, params: dict) -> dict:
        assert self.process is not None
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.request_id += 1
        req = {
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        }
        self.process.stdin.write((json.dumps(req) + "\n").encode())
        await self.process.stdin.drain()
        line = await self.process.stdout.readline()
        if not line:
            raise RuntimeError("subprocess closed stdout")
        return json.loads(line.decode())

    def _is_process_dead(self) -> bool:
        """Return True if the supervisor process (npm exec) is dead.

        npx spawns a node child that inherits stdio; the node child can outlive
        the npm parent.  We track the npm parent via its PID.  When it dies
        (SIGKILL sent by the caller before they call us), os.kill(pid, 0) raises
        ProcessLookupError synchronously -- no event-loop round-trip required.
        asyncio's returncode may still be None because SIGCHLD hasn't been
        processed yet, so we check both.
        """
        if self.process is None:
            return True
        if self.process.returncode is not None:
            return True
        try:
            os.kill(self.process.pid, 0)
            return False
        except (ProcessLookupError, PermissionError):
            return True

    def _kill_process_group(self) -> None:
        """Kill the entire process group (npm + node children) synchronously."""
        if self._pgid is not None:
            try:
                os.killpg(self._pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass  # group already gone

    async def _wait_for_death(self) -> bool:
        """Poll until the supervisor process is confirmed dead (up to ~50ms).

        SIGKILL is asynchronous: the kernel schedules the kill but the process
        may not have exited within the same CPU quantum.  A 50ms bounded wait
        (in 5ms increments) is imperceptible in practice and avoids a busy-spin.
        Returns True if the process is dead, False if it is still alive after
        the deadline.
        """
        if self.process is None:
            return True
        deadline = time.monotonic() + 0.05  # 50 ms ceiling
        while time.monotonic() < deadline:
            if self._is_process_dead():
                return True
            await asyncio.sleep(0.005)  # 5 ms between probes
        return self._is_process_dead()

    def _check_error(self, response: dict) -> dict:
        """Raise StockFilesystemError if the response is a JSON-RPC error envelope."""
        if "error" in response:
            err = response["error"]
            raise StockFilesystemError(
                f"upstream MCP error {err.get('code')}: {err.get('message')}"
            )
        return response.get("result", {})

    async def call(self, method: str, params: dict) -> dict:
        async with self._lock:
            if await self._wait_for_death():
                # The npm parent is dead; kill any surviving node children before
                # we restart so they don't keep the old stdio pipes alive.
                self._kill_process_group()
                await self._restart_if_allowed()
            try:
                response = await self._raw_call(method, params)
                return self._check_error(response)
            except (BrokenPipeError, RuntimeError, ConnectionResetError):
                self._kill_process_group()
                await self._restart_if_allowed()
                response = await self._raw_call(method, params)
                return self._check_error(response)

    async def _restart_if_allowed(self) -> None:
        now = time.monotonic()
        if now - self.restart_window_start > self.RESTART_WINDOW_SECONDS:
            self.restart_count = 0
            self.restart_window_start = now
        if self.restart_count >= self.MAX_RESTARTS:
            raise RuntimeError(
                f"stock filesystem MCP subprocess crashed {self.MAX_RESTARTS}+ times "
                f"in {self.RESTART_WINDOW_SECONDS}s"
            )
        self.restart_count += 1
        await self.start()

    async def stop(self) -> None:
        if self.process and self.process.returncode is None:
            self._kill_process_group()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except asyncio.TimeoutError:
                pass  # already killed via killpg
