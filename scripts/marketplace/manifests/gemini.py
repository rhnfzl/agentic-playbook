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
from pathlib import Path

from ..content_ops import ResolvedRef, _resolves_within_repo
from ..types import EmitterConfig, Profile
from ._shared import _default_marketplace_description


def _stderr(msg: str) -> None:
    print(msg, file=sys.stderr)


def _mcp_servers_block(
    profile: Profile, resolved: tuple[ResolvedRef, ...], repo_root: Path
) -> dict:
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
        # SECURITY (TOCTOU): this merges read JSON into gemini-extension.json,
        # so re-validate the realpath at read time -- a symlink swapped after
        # _resolve_source must not inject out-of-repo content.
        if not _resolves_within_repo(source_json, repo_root):
            _stderr(
                f"WARN: profile '{profile.name}' gemini mcp '{entry.ref}' at "
                f"{source_json} resolves outside the repo; dropping the ref"
            )
            continue
        try:
            data = json.loads(source_json.resolve().read_text(encoding="utf-8"))
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
    mcp_servers = _mcp_servers_block(profile, resolved, config.repo_root)
    if mcp_servers:
        manifest["mcpServers"] = mcp_servers
    return manifest
