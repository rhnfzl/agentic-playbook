"""Integration tests for delegate.py subprocess proxy + supervisor."""

import os
import pytest
from delegate import StockFilesystemProxy, StockFilesystemError


@pytest.mark.asyncio
async def test_proxy_lists_tools():
    proxy = StockFilesystemProxy(allowed_dirs=[os.path.expanduser("~")])
    await proxy.start()
    try:
        tools = await proxy.call("tools/list", {})
        names = [t["name"] for t in tools["tools"]]
        assert "read_file" in names
        assert "list_directory" in names
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_restarts_subprocess_on_crash():
    proxy = StockFilesystemProxy(allowed_dirs=[os.path.expanduser("~")])
    await proxy.start()
    try:
        assert proxy.process is not None, "proxy.start() must initialize .process"
        old_pid = proxy.process.pid
        proxy.process.kill()
        await proxy.call("tools/list", {})
        assert proxy.process is not None
        assert proxy.process.pid != old_pid
        assert proxy.restart_count == 1
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_raises_on_jsonrpc_error():
    """Calling an unrecognised JSON-RPC method returns an error envelope
    (code -32601 Method not found). The proxy must surface that as
    StockFilesystemError, not silently return it as a result."""
    proxy = StockFilesystemProxy(allowed_dirs=[os.path.expanduser("~")])
    await proxy.start()
    try:
        with pytest.raises(StockFilesystemError):
            # An unknown JSON-RPC method triggers a -32601 error envelope
            await proxy.call("anchored_fs/__no_such_method__", {})
    finally:
        await proxy.stop()
