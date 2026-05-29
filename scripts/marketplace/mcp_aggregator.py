"""Aggregate MCP server configs into .mcp.json per profile."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .content_ops import ResolvedRef
from .types import EmitterConfig, Profile


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _build_mcp_json(
    profile: Profile,
    resolved: tuple[ResolvedRef, ...],
    config: EmitterConfig,
    plugin_dir: Path,
) -> int:
    mcp_entries = [r for r in resolved if r.spec.kind == "mcp"]
    out = plugin_dir / ".mcp.json"
    if not mcp_entries:
        if out.exists() and not config.dry_run:
            out.unlink()
        return 0

    servers: dict[str, object] = {}
    for entry in mcp_entries:
        # Flat layout: entry.source is `<name>.json`. Bundle layout:
        # entry.source is a directory whose config lives at `server.json`
        # (mirrors gemini._mcp_servers_block).
        source_json = (
            entry.source / "server.json" if entry.source.is_dir() else entry.source
        )
        try:
            data = json.loads(source_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _stderr(
                f"WARN: profile '{profile.name}' mcp '{entry.ref}' at {source_json} "
                f"unparseable ({type(exc).__name__}); drop the ref or fix the JSON"
            )
            continue
        if isinstance(data, dict):
            for name, cfg in data.items():
                servers[name] = cfg
        else:
            _stderr(
                f"WARN: profile '{profile.name}' mcp '{entry.ref}' at {entry.source} "
                "must be a top-level JSON object keyed by server name"
            )

    if not servers:
        if out.exists() and not config.dry_run:
            out.unlink()
        return 0

    payload = {"mcpServers": dict(sorted(servers.items()))}
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if config.dry_run:
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.read_text(encoding="utf-8") == text:
        return 0
    out.write_text(text, encoding="utf-8")
    return 1
