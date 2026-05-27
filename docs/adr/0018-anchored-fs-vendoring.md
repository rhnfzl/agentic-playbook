# 0018. Vendor anchored-fs as a playbook MCP bundle (playbook-as-upstream)

## Status

Accepted (2026-05-25)

## Context

`anchored-fs` is the user's locally-developed MCP filesystem server with `prefix[upto]suffix` anchored-edit support, fuzzy path resolution, stale-read detection, and auto-graduation policies. Inspired by antirez's DwarfStar `[upto]` trick (2026-05-24).

v0.2.1 left anchored-fs outside the playbook: source lived in `~/.config/agent-shared/mcp_servers/anchored-fs/` (a local-only git repo with no remote). This created two problems:

1. The playbook documented anchored-fs but could not actually distribute it to teammates.
2. anchored-fs development happened on one machine with no team review.

## Decision

Vendor the full anchored-fs source into `mcp/anchored-fs/`. The playbook becomes the canonical upstream for anchored-fs from v0.3 onward.

### Vendor scope

Copied from `~/.config/agent-shared/mcp_servers/anchored-fs/` excluding `.venv/`, `.git/`, `.pytest_cache/`, `.ruff_cache/`, `__pycache__/`, `CODEX_FINDINGS.md`, `PHASE_0_GATE.md`. Resulting bundle: ~480K on disk.

### License

`mcp/anchored-fs/LICENSE` added (MIT, attributed to Rehan Fazal and contributors). Required for team-shared distribution.

### Installer integration

`mcp/anchored-fs/server.json` follows the v0.2.1 bundle pattern (`{{AGENT_SHARED_MCP_DIR}}` placeholder + `cwd` + `--allowed-dir ~`). The installer's `materialize_mcp_sources` was extended to symlink directories in addition to files, so anchored-fs's subdirs (`core/`, `daemon/`, `hooks/`, etc.) appear under `~/.config/agent-shared/mcp_servers/anchored-fs/` as one symlink per top-level entry.

`MCP_BUNDLE_SKIP_NAMES` expanded with `LICENSE`, `.gitignore`, `.python-version` so vendor-only files do not get symlinked into the shared directory.

### Migration

Users with an existing real-dir install at `~/.config/agent-shared/mcp_servers/anchored-fs/`:

```bash
mv ~/.config/agent-shared/mcp_servers/anchored-fs ~/.config/agent-shared/mcp_servers/anchored-fs.bak
make install
```

The installer detects real files at symlink targets and refuses to overwrite (returns `skipped-real-file` action; warns the user with the path). The `.bak` rename is the safe migration step.

## Consequences

- Future anchored-fs commits go through playbook PR review.
- The original local git repo at `~/.config/agent-shared/mcp_servers/anchored-fs/.git` becomes a backup; develop in the playbook instead.
- Vendored bundle is excluded from em-dash and parent-dir-match checks (per `VENDORED_PREFIXES` in `scripts/check_em_dashes.py` and `VENDORED_PREFIX` in `scripts/frontmatter_lint.py`).
- anchored-fs's own `install.py` (manifest-driven hook wiring) still works against the playbook copy after `uv sync`.

## Related

- v0.3 plan: scope row 7
- ADR-0012 (MCP bundle layout) is the precedent for shipping Python source in the playbook
