"""Gemini extension manifest.

Schema constraints validated 2026-05-28 against
geminicli.com/docs/extensions + google-gemini/gemini-cli docs:

  Required: `name`, `version`
  Optional: `description`, `mcpServers`, `contextFileName`, `excludeTools`,
            `migratedTo`, `plan`
  NOTE: `author` is NOT in the verified schema; do not emit it.

  `mcpServers` is the canonical place for MCP integration in Gemini
  extensions. Populate it from the profile's resolved MCP refs so a
  profile-driven plugin actually wires Gemini's MCP machinery.
"""

from __future__ import annotations

import json
import sys

from ..content_ops import ResolvedRef
from ..types import EmitterConfig, Profile
from ._shared import _default_marketplace_description


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _mcp_servers_block(profile: Profile, resolved: tuple[ResolvedRef, ...]) -> dict:
    """Aggregate MCP server configs from every resolved MCP ref.

    Handles both flat (`base/mcp/<name>.json`) and bundle
    (`base/mcp/<name>/server.json`) layouts: when `entry.source` is a
    directory, the JSON lives at `<source>/server.json`.
    """
    servers: dict[str, object] = {}
    for entry in resolved:
        if entry.spec.kind != "mcp":
            continue
        source_json = (
            entry.source / "server.json" if entry.source.is_dir() else entry.source
        )
        try:
            data = json.loads(source_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            _stderr(
                f"WARN: profile '{profile.name}' gemini mcp '{entry.ref}' at "
                f"{source_json} unparseable ({type(exc).__name__}); drop the "
                "ref or fix the JSON"
            )
            continue
        if isinstance(data, dict):
            servers.update(data)
    return dict(sorted(servers.items()))


def _gemini_extension_manifest(
    profile: Profile,
    config: EmitterConfig,
    resolved: tuple[ResolvedRef, ...],
) -> dict:
    manifest: dict = {
        "name": profile.name,
        "version": config.version_for(profile),
        "description": _default_marketplace_description(profile),
    }
    mcp_servers = _mcp_servers_block(profile, resolved)
    if mcp_servers:
        manifest["mcpServers"] = mcp_servers
    return manifest
