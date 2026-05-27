"""
Detection helpers + target resolution.

Per ADR-0031: this module owns the read-only probes that adapter
detect() methods call to decide whether to activate, plus the user-
facing target-directory resolver invoked by scripts/install.py.

Distinguished from _reader.py (which loads playbook content) by intent:
this module probes the user's machine (~/.vscode/extensions, $PATH,
$HOME) rather than the playbook repository tree.
"""

from __future__ import annotations

import os
from pathlib import Path


def which(cmd: str) -> Path | None:
    """Return Path to `cmd` on $PATH, or None. Reimplements shutil.which
    minimally to avoid stat overhead in batch detect() calls.
    """
    for p in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(p) / cmd
        if candidate.exists():
            return candidate
    return None


def vscode_extension_present(ext_id_prefix: str) -> bool:
    """True if any directory in ~/.vscode/extensions starts with ext_id_prefix."""
    ext_root = Path.home() / ".vscode" / "extensions"
    if not ext_root.is_dir():
        return False
    return any(
        d.name.startswith(ext_id_prefix) for d in ext_root.iterdir() if d.is_dir()
    )


def resolve_target(
    repo_root: Path, *, cli_target: str | None = None, non_interactive: bool = False
) -> Path:
    """Pick the target project directory.

    Per ADR-0024: PLAYBOOK_TARGET env var retired. Priority is now:
    CLI arg > interactive prompt > cwd-with-safety.

    Hard-fails if the resolved path equals the playbook checkout itself
    (writing there would overwrite the playbook's own AGENTS.md / hand-
    authored rules). In non-interactive mode with no CLI override, refuses
    to fall back to cwd when cwd is the playbook root.
    """
    repo_root_r = repo_root.resolve()

    if cli_target:
        target = Path(cli_target).expanduser().resolve()
        _validate_target(target, repo_root_r)
        return target

    if not non_interactive:
        return _prompt_for_target(repo_root_r)

    cwd = Path.cwd().resolve()
    if cwd == repo_root_r:
        raise SystemExit(
            "[installer] Refusing to write into the playbook checkout itself.\n"
            "Pass --target /path/to/project, or cd into the project first."
        )
    _validate_target(cwd, repo_root_r)
    return cwd


def _validate_target(target: Path, repo_root: Path) -> None:
    if target == repo_root:
        raise ValueError(
            f"Target ({target}) is the playbook checkout itself; refusing to "
            f"overwrite playbook source. Pick a different directory."
        )
    if not target.exists():
        raise ValueError(f"Target ({target}) does not exist.")
    if not target.is_dir():
        raise ValueError(f"Target ({target}) is not a directory.")


def _prompt_for_target(repo_root: Path) -> Path:
    cwd = Path.cwd().resolve()
    default: Path | None = cwd
    if default == repo_root:
        print()
        print("  Warning: current directory is the playbook checkout itself.")
        print("  The playbook installs INTO a target project, not into itself.")
        default = None

    while True:
        if default is not None:
            prompt = f"  Target project directory [default: {default}]: "
        else:
            prompt = "  Target project directory: "
        response = input(prompt).strip()
        if not response:
            if default is None:
                print("  Please enter a path.")
                continue
            candidate = default
        else:
            candidate = Path(response).expanduser().resolve()
        try:
            _validate_target(candidate, repo_root)
            return candidate
        except ValueError as exc:
            print(f"  {exc}")
