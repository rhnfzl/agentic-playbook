#!/usr/bin/env python3
"""MCP facade for the local agent memory bridge."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from agent_memory_bridge import (
    MemoryRecord,
    connect,
    format_audit_rows,
    format_records,
    normalize_tags,
    query_audit,
    recent_memories,
    redact_secrets,
    search_memories,
    upsert_memory,
)


# v0.12: server name is configurable so the same generic bridge can be
# used by any team. AGENT_MEMORY_MCP_NAME overrides the default; the
# default itself is generic ("agent-memory") so the base playbook ships
# nothing team-specific. Any downstream that wants a branded display
# name sets the env var in their MCP launcher / server.json template.
_DEFAULT_MCP_NAME = "agent-memory"
mcp = FastMCP(os.environ.get("AGENT_MEMORY_MCP_NAME", _DEFAULT_MCP_NAME))


@mcp.tool()
def memory_search(query: str, limit: int = 6) -> str:
    """Search active shared workspace memories."""
    with connect() as conn:
        records = search_memories(conn, query, limit=limit, status="active")
    return format_records(records, include_content=True)


@mcp.tool()
def memory_context(query: str = "", limit: int = 6) -> str:
    """Return a compact context pack from shared workspace memory."""
    with connect() as conn:
        if query:
            records = search_memories(conn, query, limit=limit, status="active")
        else:
            records = recent_memories(conn, limit=limit, status="active")
    return "# Shared Agent Memory\n\n" + format_records(records, include_content=True)


@mcp.tool()
def memory_propose(
    title: str,
    content: str,
    kind: str = "learning",
    scope: str = "workspace",
    source_path: str = "",
    source_ref: str = "",
    tags: str = "",
    confidence: str = "medium",
) -> str:
    """Propose a memory for later human or agent promotion."""
    record = MemoryRecord(
        title=title,
        content=redact_secrets(content),
        kind=kind,
        scope=scope,
        status="pending",
        source_path=source_path or None,
        source_ref=source_ref or None,
        tags=normalize_tags(tags),
        confidence=confidence,
        writer="mcp-agent",
        trust="pending-review",
    )
    with connect() as conn:
        mem_id = upsert_memory(conn, record)
    return f"pending: {mem_id}"


@mcp.tool()
def memory_audit(memory_id: str = "", writer: str = "", limit: int = 10) -> str:
    """Read recent audit events for shared workspace memories."""
    with connect() as conn:
        rows = query_audit(
            conn,
            memory_id=memory_id or None,
            writer=writer or None,
            limit=limit,
        )
    return format_audit_rows(rows)


if __name__ == "__main__":
    mcp.run()
