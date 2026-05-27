"""FastMCP server: subprocess-proxies stock @modelcontextprotocol/server-filesystem,
overrides edit_file with [upto] support, adds preview_edit_match.

Spike finding 2: stock server exposes 14 tools; we override edit_file (1) and
passthrough the other 13.

Event-loop safety: startup of the StockFilesystemProxy happens inside a FastMCP
lifespan context manager so it runs within the same anyio event loop that
mcp.run() drives. Using asyncio.get_event_loop().run_until_complete() before
mcp.run() would create a different event loop and break the proxy connection.
"""

from __future__ import annotations
import argparse
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Any, Mapping

from fastmcp import FastMCP
from delegate import StockFilesystemProxy
from tools.edit_file import edit_file as _edit_file
from tools.preview_edit_match import preview_edit_match as _preview_edit_match


def _resolve_allowed(allowed_dirs: list[str]) -> list[Path]:
    """Resolve allowed dirs to absolute real paths once per process."""
    resolved: list[Path] = []
    for d in allowed_dirs:
        try:
            resolved.append(Path(os.path.expanduser(d)).resolve())
        except (OSError, RuntimeError):
            continue
    return resolved


def _within_allowed(path: str, allowed: list[Path]) -> bool:
    """Return True if path resolves under at least one allowed dir."""
    try:
        target = Path(os.path.expanduser(path)).resolve()
    except (OSError, RuntimeError):
        return False
    for root in allowed:
        try:
            target.relative_to(root)
            return True
        except ValueError:
            continue
    return False


# Proxy is set in lifespan; module-level so tool handlers can reach it.
_proxy: StockFilesystemProxy | None = None


def _build_server(allowed_dirs: list[str]) -> FastMCP:
    """Construct and return the FastMCP app for a given set of allowed dirs."""

    resolved_allowed = _resolve_allowed(allowed_dirs)

    @asynccontextmanager
    async def lifespan(app: FastMCP) -> AsyncIterator[None]:
        global _proxy
        _proxy = StockFilesystemProxy(allowed_dirs=allowed_dirs)
        await _proxy.start()
        try:
            yield
        finally:
            await _proxy.stop()

    mcp: FastMCP = FastMCP("anchored-fs", lifespan=lifespan)

    def _enforce_allowed(path: str) -> dict | None:
        """Return an error dict if path is outside allowed roots, else None."""
        if not _within_allowed(path, resolved_allowed):
            return {
                "ok": False,
                "error": f"path '{path}' is outside the allowed roots: "
                f"{[str(p) for p in resolved_allowed]}",
            }
        return None

    # -------------------------------------------------------------------------
    # Overridden tool: edit_file with [upto] anchor support
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def edit_file(
        path: str, old_text: str, new_text: str, dry_run: bool = False
    ) -> Mapping[str, Any]:  # type: ignore[return]
        """Edit file content, supporting [upto] anchor in old_text for range selection."""
        err = _enforce_allowed(path)
        if err is not None:
            return err
        return _edit_file(
            path=path, old_text=old_text, new_text=new_text, dry_run=dry_run
        )

    # -------------------------------------------------------------------------
    # Net-new tool: preview anchor resolution without writing
    # -------------------------------------------------------------------------

    @mcp.tool()
    async def preview_edit_match(path: str, old_text: str) -> Mapping[str, Any]:  # type: ignore[return]
        """Dry-run [upto] anchor resolution for old_text. Shows matched span without writing."""
        err = _enforce_allowed(path)
        if err is not None:
            return err
        return _preview_edit_match(path=path, old_text=old_text)

    # -------------------------------------------------------------------------
    # Passthrough tools (spike finding 2: 13 non-overridden stock tools)
    # -------------------------------------------------------------------------

    async def _delegate(tool: str, arguments: dict[str, Any]) -> dict:  # type: ignore[return]
        assert _proxy is not None, "proxy not started; lifespan not entered"
        return await _proxy.call("tools/call", {"name": tool, "arguments": arguments})

    @mcp.tool()
    async def read_file(path: str) -> dict:  # type: ignore[return]
        """Deprecated alias for read_text_file; kept for back-compat."""
        return await _delegate("read_file", {"path": path})

    @mcp.tool()
    async def read_text_file(path: str) -> dict:  # type: ignore[return]
        """Read the complete contents of a file as UTF-8 text."""
        return await _delegate("read_text_file", {"path": path})

    @mcp.tool()
    async def read_media_file(path: str) -> dict:  # type: ignore[return]
        """Read an image or binary file, returning base64-encoded content."""
        return await _delegate("read_media_file", {"path": path})

    @mcp.tool()
    async def read_multiple_files(paths: list[str]) -> dict:  # type: ignore[return]
        """Read multiple files in a single call."""
        return await _delegate("read_multiple_files", {"paths": paths})

    @mcp.tool()
    async def write_file(path: str, content: str) -> dict:  # type: ignore[return]
        """Write content to a file, creating it if it does not exist."""
        return await _delegate("write_file", {"path": path, "content": content})

    @mcp.tool()
    async def create_directory(path: str) -> dict:  # type: ignore[return]
        """Create a directory and any missing parents."""
        return await _delegate("create_directory", {"path": path})

    @mcp.tool()
    async def list_directory(path: str) -> dict:  # type: ignore[return]
        """List directory entries with type indicators."""
        return await _delegate("list_directory", {"path": path})

    @mcp.tool()
    async def list_directory_with_sizes(path: str) -> dict:  # type: ignore[return]
        """List directory entries including file sizes in bytes."""
        return await _delegate("list_directory_with_sizes", {"path": path})

    @mcp.tool()
    async def directory_tree(path: str) -> dict:  # type: ignore[return]
        """Recursively list a directory as a tree structure."""
        return await _delegate("directory_tree", {"path": path})

    @mcp.tool()
    async def move_file(source: str, destination: str) -> dict:  # type: ignore[return]
        """Move or rename a file or directory."""
        return await _delegate(
            "move_file", {"source": source, "destination": destination}
        )

    @mcp.tool()
    async def search_files(path: str, pattern: str) -> dict:  # type: ignore[return]
        """Recursively search for files matching a glob pattern."""
        return await _delegate("search_files", {"path": path, "pattern": pattern})

    @mcp.tool()
    async def get_file_info(path: str) -> dict:  # type: ignore[return]
        """Return metadata (size, timestamps, type) for a file or directory."""
        return await _delegate("get_file_info", {"path": path})

    @mcp.tool()
    async def list_allowed_directories() -> dict:  # type: ignore[return]
        """Return the list of directories the server is permitted to access."""
        return await _delegate("list_allowed_directories", {})

    return mcp


def main() -> int:
    parser = argparse.ArgumentParser(description="Anchored-FS FastMCP server")
    parser.add_argument(
        "--allowed-dir",
        action="append",
        dest="allowed_dirs",
        metavar="DIR",
        required=True,
        help="Allowed filesystem root (repeatable)",
    )
    args = parser.parse_args()
    mcp = _build_server(args.allowed_dirs)
    mcp.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
