"""
Tier 3 adapter: generic AGENTS.md generator.

Covers all coding agents that read AGENTS.md natively at the target project
root. Inserts the playbook's rules as a managed block inside the target's
AGENTS.md so any pre-existing hand-authored content is preserved.

Per ADR-0024: this module exposes one `TierThreeAdapter` instance per
supported Tier 3 tool. Each instance carries its own slug + detector
callable; they share the same install() body. The dispatcher walks
`ADAPTERS` uniformly with no Tier 3 special case.

Per ADR-0030 (v0.5): the per-tool list lives in `tier3.toml` rather than
inline Python literals. The TOML supports five detection idioms
(home_dir, cli, vscode_extension, app_bundle, any_of); adding a new
Tier 3 tool is a data-only edit unless its detection needs a new idiom.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Callable, Iterable

from agents_md import AgentsMd

from . import _loader
from ._loader import Adapter, InstalledPath, PlaybookContent


TIER3_TOML = Path(__file__).resolve().parent / "tier3.toml"


class TierThreeAdapter:
    """One per supported Tier 3 tool. Detector is injected at construction time."""

    tier = 3

    def __init__(self, name: str, detector: Callable[[], bool]) -> None:
        self.name = name
        self._detector = detector

    def detect(self) -> bool:
        try:
            return bool(self._detector())
        except (OSError, PermissionError):
            return False

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
        prior_managed_keys: dict | None = None,
    ) -> Iterable[InstalledPath]:
        _ = prior_managed_keys  # tier-3 only writes AGENTS.md; no MCP/hook reconciliation
        if target is None:
            raise ValueError(f"{self.name} adapter requires a target project directory")
        agents_md = target / "AGENTS.md"
        action = (
            AgentsMd.load_or_empty(agents_md)
            .with_managed_rules(content.rules, label=self.name)
            .save_to(agents_md)
        )
        print(f"   {agents_md}: {action} ({len(content.rules)} rule(s))")
        yield InstalledPath(agents_md, "managed")


def _build_detector(detect: dict) -> Callable[[], bool]:
    """Compile one detection rule from tier3.toml into a callable.

    Each rule is a single-key mapping (home_dir / cli / vscode_extension /
    app_bundle / any_of). any_of recurses to handle composites like
    "home dir OR cli on PATH".

    Raises ValueError on unknown rule keys so a typo in tier3.toml fails
    at import time rather than at detect() time when the symptom would
    be "tool silently never matches."
    """
    if "home_dir" in detect:
        home_dir_name = detect["home_dir"]
        return lambda: (Path.home() / home_dir_name).is_dir()
    if "cli" in detect:
        cli_name = detect["cli"]
        return lambda: _loader.which(cli_name) is not None
    if "vscode_extension" in detect:
        ext_id = detect["vscode_extension"]
        return lambda: _loader.vscode_extension_present(ext_id)
    if "app_bundle" in detect:
        bundle_path = detect["app_bundle"]
        return lambda: Path(bundle_path).exists()
    if "any_of" in detect:
        sub_detectors = [_build_detector(sub) for sub in detect["any_of"]]
        return lambda: any(d() for d in sub_detectors)
    raise ValueError(
        f"tier3.toml: unknown detect rule {detect!r}; expected one of "
        f"home_dir / cli / vscode_extension / app_bundle / any_of"
    )


def _load_tier3_adapters() -> list[Adapter]:
    """Read tier3.toml and build TierThreeAdapter instances from it.

    Called at import time (see ADAPTERS assignment below) so the toml is
    parsed exactly once per Python session. Reads via tomllib (Py 3.11+
    stdlib) so no third-party dependency is added.
    """
    with TIER3_TOML.open("rb") as f:
        data = tomllib.load(f)
    adapters: list[Adapter] = []
    for entry in data.get("tier3", []):
        adapters.append(
            TierThreeAdapter(
                name=entry["name"],
                detector=_build_detector(entry["detect"]),
            )
        )
    return adapters


ADAPTERS: list[Adapter] = _load_tier3_adapters()
