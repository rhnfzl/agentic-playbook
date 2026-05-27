"""MCP ownership policy for the v0.9 lockfile (ADR-0039).

v0.9 round-3 Cursor #1 extraction: per-(adapter, config_path) managed_keys
construction used to live in scripts/install.py, which then absorbed
both orchestration AND ownership policy. Splitting them keeps install.py
under control as new adapters land and lets the policy layer be tested
in isolation.

Public surface:

  snapshot_pre_install_mcp(selected, target) -> dict[(adapter, path), set[str]]
      Build the per-config snapshot of MCP server names visible BEFORE
      any adapter.install() runs. The install dispatcher calls this once
      up-front; the result threads into compute_managed_keys_for.

  compute_managed_keys_for(adapter_name, content, target, *,
                           pre_install_per_config, prior_entries) -> dict
      Return the managed_keys dict the adapter will own AFTER install.
      Includes mcp_servers (list[ManagedMcpEntry]), hooks, and
      windsurf_hooks fields when applicable.

The ownership rule (per ADR-0039):
  A (name, config_path) pair is playbook-owned iff
    (a) the name appears in the post-install config but not in pre,
        (freshly inserted) OR
    (b) it was in prior_entries at THIS config_path AND the name is
        still configured (carry-forward for repeat installs).
Per-config logic replaces v0.8's per-adapter UNION fallback for Cursor.
"""

from __future__ import annotations

from pathlib import Path

from install_lockfile import make_managed_mcp_entry
from mcp_native_config import (
    mcp_config_paths_for,
    parse_native_mcp_servers,
    scope_for_config_path,
)


_MCP_REGISTERING_ADAPTERS = frozenset(
    {"claude-code", "codex", "cursor", "windsurf"}
)


def snapshot_pre_install_mcp(
    selected: list, target: Path | None
) -> dict[tuple[str, str], set[str]]:
    """Capture per-(adapter, config_path) pre-install MCP server name sets.

    Called BEFORE any adapter.install() runs. The result feeds into
    compute_managed_keys_for so freshly-inserted names can be diffed
    against this baseline.
    """
    snap: dict[tuple[str, str], set[str]] = {}
    for adapter in selected:
        name = getattr(adapter, "name", None)
        if name not in _MCP_REGISTERING_ADAPTERS:
            continue
        for cfg_path, fmt in mcp_config_paths_for(name, target):
            snap[(name, str(cfg_path))] = parse_native_mcp_servers(cfg_path, fmt)
    return snap


def compute_managed_keys_for(
    adapter_name: str,
    content,
    target: Path | None,
    *,
    pre_install_per_config: dict[tuple[str, str], set[str]] | None = None,
    prior_entries: list | None = None,
    hook_keys_factory=None,
    windsurf_keys_factory=None,
) -> dict:
    """Return the managed_keys dict the adapter will own AFTER install.

    For test paths that don't supply pre_install_per_config, the
    function reads native configs as the post-install state with no pre
    snapshot (treats every present name as freshly inserted at this
    path). This matches the unit-test ergonomics in test_adapters.py.

    hook_keys_factory(adapter_name, content, target) -> dict[event, list[path]]
        Optional. When supplied, populates keys["hooks"]. Provided as a
        callback so install.py keeps the hook directory mapping (which
        depends on _HOOK_REGISTERING_ADAPTERS, an install.py-local
        registry).
    windsurf_keys_factory(content) -> dict[name, bool]
        Optional. When supplied AND adapter_name == "windsurf",
        populates keys["windsurf_hooks"].
    """
    keys: dict = {}
    if adapter_name in _MCP_REGISTERING_ADAPTERS:
        configured_names = {m.name for m in content.mcp_configs}
        prior_by_key: dict[tuple[str, str], dict] = {}
        if prior_entries:
            for e in prior_entries:
                if not isinstance(e, dict):
                    continue
                ename = e.get("name")
                epath = e.get("config_path")
                if isinstance(ename, str) and isinstance(epath, str):
                    prior_by_key[(ename, epath)] = e
        entries: list = []
        for cfg_path, fmt in mcp_config_paths_for(adapter_name, target):
            cfg_path_str = str(cfg_path)
            if pre_install_per_config is not None:
                pre_set = pre_install_per_config.get(
                    (adapter_name, cfg_path_str), set()
                )
            else:
                pre_set = set()
            post_set = parse_native_mcp_servers(cfg_path, fmt)
            freshly_inserted = post_set - pre_set
            scope = scope_for_config_path(cfg_path, target)
            for name in sorted(freshly_inserted):
                if name not in configured_names:
                    continue
                entries.append(make_managed_mcp_entry(name, cfg_path, scope))
            for name in sorted(post_set - freshly_inserted):
                if name not in configured_names:
                    continue
                prior = prior_by_key.get((name, cfg_path_str))
                if prior is not None:
                    entries.append(prior)
        keys["mcp_servers"] = entries

    # v0.9 round-9-r2 regular review P2 fix: when an adapter ran and
    # the profile produces zero hooks, RECORD that explicitly so the
    # new lockfile overwrites the prior adapter section. The earlier
    # `if hook_keys: keys["hooks"] = hook_keys` left compute_managed_keys_for
    # returning {} for hook-only adapters (cline/copilot) on narrow,
    # and install.py's "if adapter_new: new_managed_keys[name] = adapter_new"
    # guard then skipped the rewrite, so stale hook entries persisted
    # in the new lockfile and doctor-verify reported them as drift.
    if hook_keys_factory is not None and adapter_name != "windsurf":
        hook_keys = hook_keys_factory(adapter_name, content, target)
        keys["hooks"] = hook_keys if hook_keys else {}

    if windsurf_keys_factory is not None and adapter_name == "windsurf":
        wkeys = windsurf_keys_factory(content)
        keys["windsurf_hooks"] = wkeys if wkeys else {}

    return keys


__all__ = [
    "compute_managed_keys_for",
    "snapshot_pre_install_mcp",
]
