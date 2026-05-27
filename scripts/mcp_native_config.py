"""Shared adapter-shape registry for MCP native configs (v0.8 C3-cleanup).

Tier-1 adapters write the MCP server registration into one of four shapes:

  * ~/.claude.json                          (JSON, mcpServers block)
  * ~/.codex/config.toml                    (TOML, [mcp_servers.<name>])
  * ~/.cursor/mcp.json + <target>/.cursor/  (JSON, mcpServers block)
  * <target>/.windsurf/mcp.json             (JSON, mcpServers block)

Three call sites previously implemented per-adapter config-path lookup
and JSON/TOML parsing:

  * install_verify._mcp_config_paths_for       (verify pass)
  * install_verify._parse_native_mcp_servers   (verify pass, name set)
  * mcp_runtime_probe._load_mcp_entry           (runtime probe)

Three separate copies meant a new Tier-1 adapter that registered MCP had
to touch all three. This module centralizes the shape registry so the
verify and probe paths share entry loading and adapter resolution.

Per-adapter native config paths are now intentionally co-located here
rather than scattered through the verify module. Adding a new MCP-
registering adapter is one row in `_MCP_CONFIG_PATHS`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal


Format = Literal["json", "toml"]


# Adapter -> list of (path-factory, format). Factories take (home, target)
# so per-target writes (Cursor, Windsurf) and user-level writes are
# uniform. Each factory may return None when the path doesn't apply for
# the given (home, target) tuple (e.g., Windsurf user-level is None).
def _claude_paths(home: Path, target: Path | None) -> list[tuple[Path, Format]]:
    return [(home / ".claude.json", "json")]


def _codex_paths(home: Path, target: Path | None) -> list[tuple[Path, Format]]:
    return [(home / ".codex" / "config.toml", "toml")]


def _cursor_paths(home: Path, target: Path | None) -> list[tuple[Path, Format]]:
    paths: list[tuple[Path, Format]] = [(home / ".cursor" / "mcp.json", "json")]
    if target is not None and target.resolve() != home.resolve():
        paths.append((target / ".cursor" / "mcp.json", "json"))
    return paths


def _windsurf_paths(home: Path, target: Path | None) -> list[tuple[Path, Format]]:
    # WindsurfAdapter.install writes MCP entries to <target>/.windsurf/
    # mcp.json only; ~/.codeium/windsurf/ is global rules + hooks, not MCP.
    if target is None:
        return []
    return [(target / ".windsurf" / "mcp.json", "json")]


_MCP_CONFIG_PATHS = {
    "claude-code": _claude_paths,
    "codex": _codex_paths,
    "cursor": _cursor_paths,
    "windsurf": _windsurf_paths,
}


def mcp_config_paths_for(
    adapter_name: str, target: Path | None
) -> list[tuple[Path, Format]]:
    """Return [(path, format), ...] for the MCP config files this
    adapter writes. Empty list for non-MCP-registering adapters.
    """
    factory = _MCP_CONFIG_PATHS.get(adapter_name)
    if factory is None:
        return []
    return factory(Path.home(), target)


def scope_for_config_path(cfg_path: Path, target: Path | None) -> str:
    """Return "project" if cfg_path sits under the target dir, else "global".

    v0.9 (ADR-0039): records the agent's precedence position at install
    time so uninstall and reconcile can target the right config file.

    Conventions:
      * target=None: every path is "global" (user-level install).
      * target=$HOME: also "global" (the no-project case; Cursor + others
        intentionally skip project-level writes when target == home).
      * Otherwise: paths under target.resolve() are "project"; others
        are "global".
    """
    if target is None:
        return "global"
    try:
        target_resolved = target.resolve()
    except OSError:
        return "global"
    if target_resolved == Path.home().resolve():
        return "global"
    try:
        cfg_path.resolve().relative_to(target_resolved)
        return "project"
    except (ValueError, OSError):
        return "global"


def parse_native_mcp_servers(config_path: Path, fmt: Format) -> set[str]:
    """Extract registered MCP server names from a native config file.

    Returns an empty set on missing file, parse failure, or wrong shape.
    The verify pass treats missing/empty as "no servers registered
    here," which is the same shape as a healthy zero-server install.
    """
    if not config_path.is_file():
        return set()
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return set()
    if not text.strip():
        return set()
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()
        servers = data.get("mcpServers")
        if isinstance(servers, dict):
            return set(servers.keys())
        return set()
    # TOML
    try:
        import tomllib

        data = tomllib.loads(text)
    except (ImportError, Exception):
        return set()
    servers = data.get("mcp_servers")
    if isinstance(servers, dict):
        return set(servers.keys())
    return set()


def load_mcp_entry(config_path: Path, server_name: str) -> dict | None:
    """Return the MCP entry for the named server in a native config, or
    None if absent. Supports both JSON and TOML layouts (format inferred
    from extension).

    Used by mcp_runtime_probe.probe_one_server. Returning None means
    "server not registered here"; the caller decides whether that is a
    skip or a fail.
    """
    if not config_path.is_file():
        return None
    if config_path.suffix == ".toml":
        try:
            import tomllib

            with config_path.open("rb") as f:
                data = tomllib.load(f)
        except (OSError, Exception):
            return None
        servers = data.get("mcp_servers")
        if isinstance(servers, dict):
            entry = servers.get(server_name)
            return entry if isinstance(entry, dict) else None
        return None
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not text.strip():
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    servers = data.get("mcpServers")
    if isinstance(servers, dict):
        entry = servers.get(server_name)
        return entry if isinstance(entry, dict) else None
    return None


__all__ = [
    "Format",
    "load_mcp_entry",
    "mcp_config_paths_for",
    "parse_native_mcp_servers",
    "scope_for_config_path",
]
