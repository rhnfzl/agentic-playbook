"""Profile loading + content filtering (ADR-0025).

A Profile selects a subset of the playbook's seven content types for a
specific role (backend-developer, frontend-developer, qa, tech-lead).
Used by `make install --profile <role>` to materialize only the role's
content, and by `playbook_init.py --profile <role>` for per-project
scaffolding.

TOML schema (profiles/<name>.toml):

    name = "backend-developer"
    description = "..."

    [skills]
    include = ["engineering/code-review", ...]

    [rules]
    include = ["label-policy", "no-em-dashes", ...]

    [hooks]
    include = ["sonar-advisory", "lint-guard", ...]

    [mcp]
    include = ["atlassian", "slack", ...]

Content types not listed in the Profile (agents, commands, prompts) pass
through filtering unchanged; the Profile is a soft filter for the seven
canonical types but only constrains the four it lists today.
"""

from __future__ import annotations

import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters._loader import PlaybookContent  # noqa: E402


@dataclass(frozen=True)
class Profile:
    name: str
    description: str
    skills: list[str]  # slugs like "engineering/diagnose"
    rules: list[str]  # slugs like "no-em-dashes"
    hooks: list[str]  # slugs like "lint-guard"
    mcp: list[str]  # slugs like "atlassian"
    # v0.11 (ADR-0040): overlays required for this profile to be valid.
    requires_overlays: list[str] = field(default_factory=list)


def load_profile(repo_root: Path, name: str) -> Profile:
    """Load profiles/<name>.toml. Raises FileNotFoundError if missing,
    ValueError if the TOML is malformed.

    v0.11 (ADR-0040): profiles MAY declare top-level
    `requires_overlays = ["team"]` to assert their content depends on a
    specific overlay being active. Validation happens later via
    validate_profile_scope (split from load to keep load_profile pure).
    """
    path = repo_root / "profiles" / f"{name}.toml"
    if not path.is_file():
        available = ", ".join(sorted(list_profiles(repo_root)))
        raise FileNotFoundError(
            f"profile '{name}' not found at {path}. Available: {available or '(none)'}"
        )
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    raw_overlays = data.get("requires_overlays", [])
    if not isinstance(raw_overlays, list) or not all(
        isinstance(o, str) for o in raw_overlays
    ):
        raise ValueError(
            f"profile '{name}': requires_overlays must be a list of strings"
        )
    return Profile(
        name=data.get("name", name),
        description=data.get("description", ""),
        skills=list(data.get("skills", {}).get("include", [])),
        rules=list(data.get("rules", {}).get("include", [])),
        hooks=list(data.get("hooks", {}).get("include", [])),
        mcp=list(data.get("mcp", {}).get("include", [])),
        requires_overlays=list(raw_overlays),
    )


def load_profiles(repo_root: Path, names: list[str]) -> Profile:
    """Load multiple profiles by name and return their union as a single Profile.

    v0.10: small companies have devs wearing multiple hats (PM + research +
    developer + a-bit-of-DevOps). The installer accepts a comma-separated
    `--profile a,b,c` and unions the includes via this helper. Per the
    profile-separation principle, each input profile stays single-role; the
    composition lives in the install command, not in a pre-authored
    composite profile.

    Dedupe is set-based, so the same skill appearing in two profiles
    materializes once. Order is sorted for determinism: lockfile bytes
    stay stable across reruns regardless of how `--profile` ordered the
    names.

    Returns a synthetic Profile whose name is the comma-joined input list
    (preserved verbatim so the lockfile can round-trip it) and whose
    description concatenates each profile's description with " + ".
    """
    if not names:
        raise ValueError("at least one profile name required")
    loaded = [load_profile(repo_root, n) for n in names]
    if len(loaded) == 1:
        return loaded[0]
    return Profile(
        name=",".join(p.name for p in loaded),
        description=" + ".join(p.description for p in loaded if p.description),
        skills=sorted({s for p in loaded for s in p.skills}),
        rules=sorted({r for p in loaded for r in p.rules}),
        hooks=sorted({h for p in loaded for h in p.hooks}),
        mcp=sorted({m for p in loaded for m in p.mcp}),
        requires_overlays=sorted({o for p in loaded for o in p.requires_overlays}),
    )


def validate_profile_scope(profile: Profile, active_scope: list[str]) -> None:
    """Raise ValueError if the profile requires overlays not in the active scope.

    Per ADR-0040 (v0.11): a profile may declare `requires_overlays =
    ["team"]` to assert it cannot install in a base-only context.
    The installer calls this after `load_profile` / `load_profiles` and
    before any materialize step, so the failure surfaces with a clear
    actionable message rather than a silent partial install.

    Profiles without `requires_overlays` are always valid (no constraint).
    """
    if not profile.requires_overlays:
        return
    missing = [o for o in profile.requires_overlays if o not in active_scope]
    if not missing:
        return
    raise ValueError(
        f"Profile '{profile.name}' requires overlay(s) "
        f"{', '.join(missing)} but they are not in the active scope.\n"
        f"Active scope: {active_scope or '(base only)'}\n"
        f"Resolution: pass --scope {','.join(profile.requires_overlays)}, "
        f"or pick a profile that does not require these overlays."
    )


def parse_profile_arg(value: str | None) -> list[str]:
    """Parse a --profile CLI value into a list of profile names.

    Accepts None (no profile, returns []), a single name ("backend-developer"),
    or a comma-separated list ("product-manager,research,backend-developer").
    Whitespace around each name is stripped; empty tokens are dropped so
    "pm, , dev" doesn't trip the loader.

    The installer feeds this into `load_profiles`. Round-tripping the
    same input on `make update` (no explicit --profile) is handled by the
    lockfile, which records the resolved name list.
    """
    if value is None:
        return []
    names = [token.strip() for token in value.split(",")]
    return [name for name in names if name]


def list_profiles(repo_root: Path) -> list[str]:
    """Return the slugs of all profiles/*.toml files."""
    profiles_dir = repo_root / "profiles"
    if not profiles_dir.is_dir():
        return []
    return sorted(p.stem for p in profiles_dir.glob("*.toml"))


def filter_content(content: PlaybookContent, profile: Profile) -> PlaybookContent:
    """Return a PlaybookContent narrowed to the profile's lists.

    Skills are matched by `<category>/<name>` (e.g. "engineering/diagnose").
    Rules / hooks / MCP are matched by their slug. Agents / commands /
    prompts pass through unchanged (Profile doesn't constrain them today).
    """
    skill_slugs = set(profile.skills)
    rule_slugs = set(profile.rules)
    hook_slugs = set(profile.hooks)
    mcp_slugs = set(profile.mcp)

    return PlaybookContent(
        skills=[s for s in content.skills if f"{s.category}/{s.name}" in skill_slugs],
        rules=[r for r in content.rules if r.name in rule_slugs],
        hooks=[h for h in content.hooks if h.name in hook_slugs],
        mcp_configs=[m for m in content.mcp_configs if m.name in mcp_slugs],
        agents=content.agents,
        commands=content.commands,
        prompts=content.prompts,
        trajectories=content.trajectories,
    )


def dangling_entries(
    content: PlaybookContent, profile: Profile
) -> dict[str, list[str]]:
    """Return profile entries that reference content slugs not present in the repo.

    `profiles/README.md` documents that referenced items MUST exist in the
    playbook; otherwise the entry is silently dropped by filter_content. This
    helper surfaces such drift so the installer can warn loudly when a profile
    has rotted (e.g. a skill was renamed but its old slug lives on in a
    role bundle).

    Returns a dict keyed by content type with the orphan slugs as values:
        {"skills": [...], "rules": [...], "hooks": [...], "mcp": [...]}
    """
    have_skills = {f"{s.category}/{s.name}" for s in content.skills}
    have_rules = {r.name for r in content.rules}
    have_hooks = {h.name for h in content.hooks}
    have_mcp = {m.name for m in content.mcp_configs}
    dangling: dict[str, list[str]] = {}
    missing_skills = [s for s in profile.skills if s not in have_skills]
    missing_rules = [r for r in profile.rules if r not in have_rules]
    missing_hooks = [h for h in profile.hooks if h not in have_hooks]
    missing_mcp = [m for m in profile.mcp if m not in have_mcp]
    if missing_skills:
        dangling["skills"] = missing_skills
    if missing_rules:
        dangling["rules"] = missing_rules
    if missing_hooks:
        dangling["hooks"] = missing_hooks
    if missing_mcp:
        dangling["mcp"] = missing_mcp
    return dangling
