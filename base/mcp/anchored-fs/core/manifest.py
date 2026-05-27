"""Manifest loading, schema validation, and template substitution."""

from __future__ import annotations
import json
from pathlib import Path

TEMPLATE_PATH = Path(__file__).parent.parent / "templates" / "manifest.json"
CURRENT_SCHEMA = 1


def load_template() -> dict:
    return json.loads(TEMPLATE_PATH.read_text())


def validate(manifest: dict) -> None:
    if "schema_version" not in manifest:
        raise ValueError("manifest missing schema_version")
    if manifest["schema_version"] != CURRENT_SCHEMA:
        raise ValueError(
            f"schema_version {manifest['schema_version']} not supported (expected {CURRENT_SCHEMA})"
        )
    if "hooks" not in manifest or "mcp_servers" not in manifest:
        raise ValueError("manifest missing hooks or mcp_servers")


def render(manifest: dict, *, anchored_fs_root: str, allowed_root: str = "~") -> dict:
    raw = json.dumps(manifest)
    rendered = raw.replace("{anchored_fs_root}", anchored_fs_root).replace(
        "{allowed_root}", allowed_root
    )
    result = json.loads(rendered)
    for hook in result.get("hooks", {}).values():
        if "command_template" in hook:
            hook["command"] = hook.pop("command_template")
    return result
