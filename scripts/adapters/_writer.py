"""
File-writing primitives + content composition helpers.

Per ADR-0031: this module owns every write a stock adapter performs:
managed-block upsert/remove on shared files (AGENTS.md, .clinerules,
codex AGENTS.md, etc.), copy_skill_payload, MCP source symlinking,
agent->TOML conversion, and the JSON-MCP merge helper
that 8+ adapters previously open-coded.

Read-only style helpers live here too (find_em_dashes) because they
operate on file contents and have no other natural home.

Other split partners:
  _protocol.py: types + Adapter Protocol + JSON MCP reconciliation.
  _reader.py: playbook content scanners.
  _detect.py: detection helpers + target resolution.
  _loader.py: re-export shim.
"""

from __future__ import annotations

import errno
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from ._protocol import MARKER_ID, Agent, McpConfig, Rule, Skill


AGENT_SHARED_MCP_DIR = Path.home() / ".config" / "agent-shared" / "mcp_servers"
AGENT_SHARED_PLACEHOLDER = "{{AGENT_SHARED_MCP_DIR}}"
PLAYBOOK_TARGET_PLACEHOLDER = "{{PLAYBOOK_TARGET}}"
MCP_BUNDLE_SKIP_NAMES = {
    "server.json",
    "README.md",
    "CUSTOMIZE.md",
    "LICENSE",
    ".gitignore",
    ".python-version",
}


def ensure_dir(path: Path) -> Path:
    """Create directory if missing; return the path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def _is_windows_symlink_privilege_error(exc: OSError) -> bool:
    """True when an OSError from Path.symlink_to is the Windows privilege case.

    Windows requires Developer Mode (or admin) to let a process create a
    symlink. Without it, CreateSymbolicLinkW returns ERROR_PRIVILEGE_NOT_HELD
    (1314), which Python surfaces as OSError with winerror=1314. On POSIX the
    same surface error never fires; we only treat it as the fallback trigger
    on Windows.
    """
    if os.name != "nt":
        return False
    winerror = getattr(exc, "winerror", None)
    if winerror == 1314:
        return True
    return exc.errno == errno.EPERM


def safe_symlink_or_copy(
    link_path: Path,
    target: Path,
    *,
    target_is_directory: bool = False,
) -> Literal["symlink", "copy"]:
    """Create link_path as a symlink to target; fall back to copy on Windows.

    On any platform where symlinks work normally, this is `Path.symlink_to`.
    On Windows without Developer Mode the syscall raises OSError(WinError 1314),
    which we catch and convert to a copy: directories via shutil.copytree,
    files via shutil.copy2. Returns "symlink" on the normal path or "copy"
    on the Windows-privilege fallback so callers can log the degradation if
    they care.

    Genuine permission errors (no write access, parent dir missing, etc.)
    still surface as OSError; the helper only swallows the specific
    privilege-not-held case so the install can still complete on a
    non-developer-mode Windows machine.
    """
    try:
        link_path.symlink_to(target, target_is_directory=target_is_directory)
        return "symlink"
    except OSError as exc:
        if not _is_windows_symlink_privilege_error(exc):
            raise
        # v0.7 Codex review fix: relative targets like
        # `../../.agents/skills/<name>` (Cursor) or `../.agents/<subdir>`
        # (TargetMaterializer) are valid as symlink targets relative to
        # link_path.parent, but shutil.copytree / copy2 resolve them
        # against the process CWD. Re-anchor before copying so the
        # fallback writes the content the symlink would have pointed at.
        if target.is_absolute():
            source = target
        else:
            source = (link_path.parent / target).resolve()
        if source.is_dir():
            shutil.copytree(source, link_path, symlinks=False)
        else:
            shutil.copy2(source, link_path)
        print(
            f"   note:    symlink to {target} not permitted on Windows; "
            f"copied content from {source} to {link_path} (enable "
            "Developer Mode for symlink installs)"
        )
        return "copy"


PLAYBOOK_OWNERSHIP_MARKER = ".playbook-owned"


def first_heading_or_default(body: str, *, default: str) -> str:
    """Return the first markdown heading line (stripped of leading '#'s) or
    `default`. Shared helper for adapters and the target materializer to
    derive a Cursor/Windsurf rule description from the rule body without
    requiring a separate metadata file. Per v0.6 review-2 fixup: was
    duplicated across cursor.py / windsurf.py / target_materializer.py
    as `_rule_description` and `_first_heading_or_default`.
    """
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            text = stripped.lstrip("# ").strip()
            if text:
                return text
    return default


def is_playbook_owned_skill_dir(skill_dir: Path, install_name: str) -> bool:
    """Return True when skill_dir looks like a playbook-managed install,
    False when it appears to be user-authored content.

    Two proof paths (per ADR-0034 / 0035 adversarial review hardening):
      1. Marker file: `<dir>/.playbook-owned` exists (v0.6+ writes this).
      2. Legacy frontmatter match: `<dir>/SKILL.md` exists, starts with a
         YAML frontmatter block, and the frontmatter declares
         `name: <install_name>` (v0.5 installs predate the marker).

    When neither is true, the directory is treated as user content and
    the adapter MUST NOT overwrite it. Adapter raises a warning + skips
    instead.
    """
    if (skill_dir / PLAYBOOK_OWNERSHIP_MARKER).exists():
        return True
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return False
    try:
        head = skill_md.read_text(encoding="utf-8")[:400]
    except OSError:
        return False
    if not head.lstrip().startswith("---"):
        return False
    return f"name: {install_name}" in head


def copy_skill_payload(skill: Skill, target_dir: Path) -> list[Path]:
    """Copy a skill's SKILL.md plus references/ and scripts/ into target_dir.

    The graphify split (v0.3) moved deep content into references/; adapters
    that only copy SKILL.md leave the skill unable to follow its own workflow.
    This helper ensures the full payload travels together. Falls back gracefully
    when references/ or scripts/ are absent.

    v0.6 ownership marker (per ADR-0034 adversarial review): every
    playbook-installed skill dir gets a sentinel `.playbook-owned` file
    so adapters can prove ownership before destructive ops. Callers that
    need to overwrite an existing target dir MUST check ownership via
    is_playbook_owned_skill_dir() first.

    Returns the list of every file actually written under target_dir so the
    caller can yield InstalledPath entries for each one (per ADR-0024; the
    lockfile must record every file or status / remove silently drop them).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    skill_md_target = target_dir / "SKILL.md"
    shutil.copy2(skill.path, skill_md_target)
    written.append(skill_md_target)
    skill_root = skill.path.parent
    for sub in ("references", "scripts"):
        src = skill_root / sub
        if src.is_dir():
            dest = target_dir / sub
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
            for path in sorted(dest.rglob("*")):
                if path.is_file():
                    written.append(path)
    marker = target_dir / PLAYBOOK_OWNERSHIP_MARKER
    marker.write_text(f"{skill.install_name or skill.name}\n", encoding="utf-8")
    written.append(marker)
    return written


def merge_managed_mcp_into_json(
    config_path: Path,
    *,
    block_key: str,
    mcp_configs: list,
    target: Path | None,
    skip_names: set[str] | None = None,
) -> tuple[int, int, list[str]]:
    """Upsert MCP server entries into a JSON config file (v0.8 / C2).

    Used by every Tier-1 adapter that maintains a JSON-shaped MCP
    registry (claude-code -> ~/.claude.json, cursor -> ~/.cursor/mcp.json
    + per-target .cursor/mcp.json, windsurf -> <target>/.windsurf/mcp.json).

    Semantics:
      - Load existing config (empty dict on missing file or parse failure).
      - For each McpConfig, skip if the name already exists in the
        `block_key` block (preserve user-authored entries by name)
        OR if the name is in skip_names (explicit overlay -- used by
        cursor's project-level write to avoid inserting names the
        user already has at user level).
      - Otherwise expand placeholders + add it.
      - Write back with a trailing newline.

    Returns (added, skipped, inserted_names). The 3rd field is the
    exact names this run inserted; install.py uses it to compute
    managed_keys.mcp_servers correctly without claiming ownership of
    user-authored entries.
    """
    existing: dict = {}
    if config_path.is_file():
        try:
            existing = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    block = existing.setdefault(block_key, {})
    added = 0
    skipped = 0
    inserted_names: list[str] = []
    overlay = skip_names or set()
    for mcp in mcp_configs:
        if mcp.name in block or mcp.name in overlay:
            skipped += 1
            continue
        block[mcp.name] = expand_agent_shared_placeholder(
            mcp.config, mcp.name, target=target
        )
        added += 1
        inserted_names.append(mcp.name)
    # v0.9 (ADR-0039 + round-3 Cursor #5): write a native managedBy
    # marker so an operator reading the file directly can identify
    # playbook-managed entries without consulting the lockfile. Key is
    # underscore-prefixed for safety against collisions in shared files
    # like ~/.claude.json that carry non-MCP content. The lockfile
    # remains authoritative for ownership decisions; this marker is
    # informational.
    #
    # Idempotency: last_updated_at refreshes only when entries were
    # actually inserted this run. Otherwise the existing timestamp is
    # preserved so re-install of an unchanged profile produces a
    # byte-identical file.
    #
    # Round-3 Cursor #5: marker write is wrapped in try/except to honor
    # the ADR-promised silent degrade. If a vendor schema rejects the
    # extra _playbook_metadata key, install proceeds with lockfile-only
    # ownership rather than failing hard.
    try:
        existing_meta = existing.get("_playbook_metadata", {})
        existing_meta_is_ours = (
            isinstance(existing_meta, dict)
            and existing_meta.get("managedBy") == "coding-agents-playbook"
        )
        if added > 0 or not existing_meta_is_ours:
            last_updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        else:
            last_updated_at = existing_meta.get(
                "last_updated_at",
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            )
        existing["_playbook_metadata"] = {
            "managedBy": "coding-agents-playbook",
            "lockfile_version": 3,
            "last_updated_at": last_updated_at,
        }
    except (TypeError, ValueError, AttributeError) as exc:
        # Silent degrade: lockfile is authoritative, marker is informational.
        # Surface the reason for debuggers but don't block install.
        print(
            f"  warn: could not write _playbook_metadata marker in "
            f"{config_path}: {exc}; continuing with lockfile-only ownership"
        )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
    return added, skipped, inserted_names


def expand_agent_shared_placeholder(
    config: dict, name: str, target: Path | None = None
) -> dict:
    """Return a copy of an MCP server config with {{AGENT_SHARED_MCP_DIR}} and
    {{PLAYBOOK_TARGET}} resolved.

    AGENT_SHARED_MCP_DIR expands to ~/.config/agent-shared/mcp_servers/<name>.
    PLAYBOOK_TARGET expands to the resolved per-project target dir (or HOME if
    no target is set). Adapters then write the expanded config into their own
    MCP registry (~/.codex/config.toml, ~/.claude.json, etc.).

    PLAYBOOK_TARGET is used by bundles like anchored-fs to narrow filesystem
    write scope to the target project rather than defaulting to home-wide
    access (per ADR-0023 and the v0.3 adversarial-review finding).
    """
    expansion = str((AGENT_SHARED_MCP_DIR / name).resolve())
    target_expansion = str(target.resolve()) if target is not None else str(Path.home())
    serialized = json.dumps(config)
    serialized = serialized.replace(AGENT_SHARED_PLACEHOLDER, expansion)
    serialized = serialized.replace(PLAYBOOK_TARGET_PLACEHOLDER, target_expansion)
    return json.loads(serialized)


def materialize_mcp_sources(
    mcp_configs: list[McpConfig],
    target_dir: Path | None = None,
    *,
    prior_owned_paths: set[Path] | None = None,
) -> list[tuple[str, Path, str]]:
    """Symlink Python-source MCPs into ~/.config/agent-shared/mcp_servers/<name>/.

    For each McpConfig with source_dir set, iterate its source files (excluding
    server.json, README.md, CUSTOMIZE.md) and create a symlink at
    <target_dir>/<name>/<file> pointing to the source in the playbook repo.

    Idempotent. Returns a list of (mcp_name, link_path, action) tuples where
    action is one of: "created", "updated", "unchanged", "skipped-real-file".
    Real (non-symlink) files at a target path are skipped by default to avoid
    clobbering user-authored content; the installer skips them and surfaces
    a warning the caller can print.

    `prior_owned_paths` is the set of link_path values the playbook recorded
    as owned in the prior install (typically passed from `_bundles`
    lockfile entries). Paths in that set are NOT user-authored content;
    they are this installer's own Windows-fallback copies from the
    previous run. We replace them instead of treating them as foreign, so
    repeat installs on Windows do not leak or orphan playbook-owned bundle
    files.

    Coexists with ~/.config/agent-shared/sync_mcp_configs.py: this function
    only places the source files; sync_mcp_configs.py distributes the
    registration metadata into Claude/Codex configs.
    """
    if target_dir is None:
        target_dir = AGENT_SHARED_MCP_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    prior_owned = prior_owned_paths or set()
    actions: list[tuple[str, Path, str]] = []
    for mcp in mcp_configs:
        if mcp.source_dir is None:
            continue
        server_target = target_dir / mcp.name
        server_target.mkdir(parents=True, exist_ok=True)
        source_real = mcp.source_dir.resolve()
        for source_file in sorted(mcp.source_dir.iterdir()):
            if source_file.name in MCP_BUNDLE_SKIP_NAMES:
                continue
            if not (source_file.is_file() or source_file.is_dir()):
                continue
            link_path = server_target / source_file.name
            source_target = source_real / source_file.name
            if link_path.is_symlink():
                if link_path.resolve() == source_target:
                    actions.append((mcp.name, link_path, "unchanged"))
                    continue
                link_path.unlink()
                safe_symlink_or_copy(link_path, source_target)
                actions.append((mcp.name, link_path, "updated"))
                continue
            if link_path.exists():
                # The path exists but is NOT a symlink; either it is a
                # user-authored real file (skip with warning) or it is
                # the playbook's own Windows-fallback copy from the prior
                # install (replace). The latter is provable from the
                # prior lockfile; without that check, a repeat install
                # would treat its own copy as foreign and either skip
                # it or orphan-delete it.
                if link_path in prior_owned:
                    if link_path.is_dir():
                        shutil.rmtree(link_path)
                    else:
                        link_path.unlink()
                    safe_symlink_or_copy(link_path, source_target)
                    actions.append((mcp.name, link_path, "updated"))
                    continue
                actions.append((mcp.name, link_path, "skipped-real-file"))
                continue
            safe_symlink_or_copy(link_path, source_target)
            actions.append((mcp.name, link_path, "created"))
    return actions


def agent_to_toml(agent: Agent) -> str:
    """Convert an Agent (markdown frontmatter + body) to Codex TOML format.

    Codex subagents (per developers.openai.com/codex/subagents) require:
      - name (str)
      - description (str)
      - developer_instructions (multi-line str; we use the markdown body)
    Optional: model, model_reasoning_effort, sandbox_mode, mcp_servers, etc.
    Fields we drop on conversion: tools (Codex has no direct equivalent).

    Codex P1 #2 fix: developer_instructions uses a TOML LITERAL multi-line string
    ('''...''') instead of a basic multi-line string ("\"\"\"..."\""), so backslash
    sequences in the markdown body (regex patterns like R8-\\d+ in agents/VCS-
    pr-investigator.md, escape sequences in code examples) are not parsed as TOML
    escapes. Literal strings only end at the closing ''' delimiter.

    If the body happens to contain ''' (rare in markdown), falls back to the basic
    string form with backslashes escaped, since literal strings have no escape mechanism.
    """
    fm = agent.frontmatter
    lines: list[str] = []
    name = fm.get("name", agent.name)
    description = fm.get("description", "")
    lines.append(f'name = "{_toml_escape(name)}"')
    lines.append(f'description = "{_toml_escape(description)}"')
    if "model" in fm:
        lines.append(f'model = "{_toml_escape(fm["model"])}"')
    if "model_reasoning_effort" in fm:
        lines.append(
            f'model_reasoning_effort = "{_toml_escape(fm["model_reasoning_effort"])}"'
        )
    if "sandbox_mode" in fm:
        lines.append(f'sandbox_mode = "{_toml_escape(fm["sandbox_mode"])}"')
    lines.append("")
    body = agent.body.rstrip()
    if "'''" not in body:
        lines.append("developer_instructions = '''")
        lines.append(body)
        lines.append("'''")
    else:
        escaped_body = body.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
        lines.append('developer_instructions = """')
        lines.append(escaped_body)
        lines.append('"""')
    return "\n".join(lines) + "\n"


def _toml_escape(value: str) -> str:
    """Escape a string for use inside a TOML double-quoted scalar."""
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


_EM_DASH_CHARS = ("—", "–")  # em dash, en dash


def find_em_dashes(text: str) -> list[tuple[int, str]]:
    """Return [(line_number, line_text)] for every line containing an em or en dash.

    Per rules/no-em-dashes.md, em dashes are banned in authored files.
    """
    hits: list[tuple[int, str]] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if any(ch in line for ch in _EM_DASH_CHARS):
            hits.append((idx, line))
    return hits


def compose_agents_md(rules: list[Rule], header: str = "") -> str:
    """Concatenate rules into a single AGENTS.md body.

    Each rule's first heading becomes a section. Rules without headings
    get a heading derived from the filename slug.
    """
    parts: list[str] = []
    if header:
        parts.append(header.rstrip() + "\n")

    for rule in rules:
        body = rule.body.strip()
        if not body.startswith("#"):
            heading = "# " + rule.name.replace("-", " ").title()
            body = f"{heading}\n\n{body}"
        parts.append(body)

    return "\n\n".join(parts) + "\n"


def upsert_managed_block(
    path: Path,
    content: str,
    *,
    marker_id: str = MARKER_ID,
    comment_prefix: str = "<!--",
    comment_suffix: str = "-->",
    create_if_missing: bool = True,
    header: str = "",
) -> str:
    """Idempotently update a marker-delimited region in a text file.

    Inserts (or replaces) a block bracketed by:
        {comment_prefix} {marker_id} BEGIN {comment_suffix}
        ...content...
        {comment_prefix} {marker_id} END {comment_suffix}

    Behavior:
    - If both markers present, content between them is replaced.
    - If only BEGIN is present (no matching END), raises ValueError. Refuses
      to corrupt user content by auto-recovering.
    - If neither marker is present, block is appended at end of file.
    - If file does not exist and create_if_missing, the file (and parents)
      are created containing just the block (with optional header above).

    Returns one of: "created", "replaced", "appended", "unchanged".
    """
    begin = _marker_line(comment_prefix, comment_suffix, marker_id, "BEGIN")
    end = _marker_line(comment_prefix, comment_suffix, marker_id, "END")
    block = f"{begin}\n{content.rstrip()}\n{end}"

    if not path.exists():
        if not create_if_missing:
            raise FileNotFoundError(f"{path} does not exist")
        path.parent.mkdir(parents=True, exist_ok=True)
        prefix = (header.rstrip() + "\n\n") if header else ""
        path.write_text(prefix + block + "\n", encoding="utf-8")
        return "created"

    text = path.read_text(encoding="utf-8")
    begin_idx = text.find(begin)

    if begin_idx >= 0:
        end_idx = text.find(end, begin_idx + len(begin))
        if end_idx < 0:
            raise ValueError(
                f"{path} contains '{begin}' but no matching '{end}'. "
                f"Refusing to corrupt. Resolve the file manually."
            )
        stray = text.find(begin, end_idx + len(end))
        if stray >= 0:
            raise ValueError(
                f"{path} contains multiple '{begin}' markers. "
                f"Refusing to choose. Resolve the file manually."
            )
        new_text = text[:begin_idx] + block + text[end_idx + len(end) :]
        if new_text == text:
            return "unchanged"
        path.write_text(new_text, encoding="utf-8")
        return "replaced"

    separator = (
        "" if text.endswith("\n\n") else ("\n" if text.endswith("\n") else "\n\n")
    )
    new_text = text + separator + block + "\n"
    path.write_text(new_text, encoding="utf-8")
    return "appended"


def remove_managed_block(
    path: Path,
    *,
    marker_id: str = MARKER_ID,
    comment_prefix: str = "<!--",
    comment_suffix: str = "-->",
) -> str:
    """Remove a previously-inserted managed block. For uninstall flows.

    Returns "removed" or "absent". Raises on half-markers (same safety as upsert).
    """
    if not path.exists():
        return "absent"
    begin = _marker_line(comment_prefix, comment_suffix, marker_id, "BEGIN")
    end = _marker_line(comment_prefix, comment_suffix, marker_id, "END")
    text = path.read_text(encoding="utf-8")
    begin_idx = text.find(begin)
    if begin_idx < 0:
        return "absent"
    end_idx = text.find(end, begin_idx + len(begin))
    if end_idx < 0:
        raise ValueError(f"{path} has '{begin}' but no matching '{end}'.")
    cut_start = begin_idx
    cut_end = end_idx + len(end)
    while cut_start > 0 and text[cut_start - 1] == "\n":
        cut_start -= 1
    while cut_end < len(text) and text[cut_end] == "\n":
        cut_end += 1
    new_text = (
        text[:cut_start]
        + ("\n" if cut_start > 0 and cut_end < len(text) else "")
        + text[cut_end:]
    )
    path.write_text(new_text, encoding="utf-8")
    return "removed"


def existing_toml_tables_outside_block(
    path: Path,
    table_prefix: str,
    *,
    marker_id: str = MARKER_ID,
    comment_prefix: str = "#",
    comment_suffix: str = "",
) -> set[str]:
    """Return the set of top-level child names declared under ``[<table_prefix>.X]``
    that sit outside the managed block in ``path``.

    Sub-tables (``[<table_prefix>.X.env]``) resolve to the same name as their parent,
    matching TOML semantics. Returns an empty set if the file does not exist.

    Used by adapters that ship placeholder configs to detect pre-existing entries
    a user has already authored, so the adapter can skip them rather than emit a
    duplicate table header.
    """
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    begin = _marker_line(comment_prefix, comment_suffix, marker_id, "BEGIN")
    end = _marker_line(comment_prefix, comment_suffix, marker_id, "END")
    begin_idx = text.find(begin)
    if begin_idx >= 0:
        end_idx = text.find(end, begin_idx + len(begin))
        if end_idx >= 0:
            text = text[:begin_idx] + text[end_idx + len(end) :]
    pattern = re.compile(
        rf"^\[{re.escape(table_prefix)}\.([^.\]]+)",
        flags=re.MULTILINE,
    )
    return set(pattern.findall(text))


def _marker_line(prefix: str, suffix: str, marker_id: str, label: str) -> str:
    body = f"{prefix} {marker_id} {label}"
    return f"{body} {suffix}" if suffix else body
