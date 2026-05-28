"""Cursor plugin manifest.

Cursor schema (validated 2026-05-28 against cursor.com/docs/plugins +
github.com/cursor/plugins):

  .cursor-plugin/plugin.json:
    Required: `name`
    Recommended: `description`, `version`, `author`
    (Strict subset of Claude's plugin.json so passthrough is valid.)

  .cursor-plugin/marketplace.json:
    `name`, `owner` (with `name`, optional `url`), `plugins[]`
    Source is a bare string `"./<dir>"` (same as Claude).

We expose the same builders behind Cursor-named imports so future drift
can be caught by changing only this file.
"""

from __future__ import annotations

from .claude import (
    _claude_marketplace_manifest as _cursor_marketplace_manifest,
    _claude_plugin_manifest as _cursor_plugin_manifest,
)

__all__ = ["_cursor_marketplace_manifest", "_cursor_plugin_manifest"]
