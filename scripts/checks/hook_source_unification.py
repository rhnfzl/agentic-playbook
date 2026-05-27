"""Hook source unification check (ADR-0035 layer-1 integrity).

ADR-0035 says: every hook has exactly one canonical body on disk. If a hook
has a skill owner, the canonical lives under skills/<cat>/<name>/hooks/ and
the root hooks/<name>.sh is a symlink back to it. Orphan hooks (no skill
owner) keep their canonical at the root.

This check enforces that contract so it cannot silently drift. It fails
when:
  * A root hooks/<name>.sh exists alongside a skills/.../hooks/<name>.sh
    with the same basename, but root is NOT a symlink (two canonical
    sources, next edit drifts).
  * A root hooks/<name>.sh is a symlink to a path that does not exist or
    does not point at a skill-owned canonical.
  * A hook declares PLAYBOOK-HOOK-CURSOR-WRAPPER: <wrapper>.sh and the
    named wrapper cannot be located in either root or any skill-owned
    hooks/ directory.

Underscore-prefixed files (e.g. hooks/_cascade-translate.sh) are helpers,
not hooks, and are skipped per ADR-0035.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import CheckContext, CheckResult


def _skill_owned_hooks(repo_root: Path) -> dict[str, Path]:
    """Return basename -> canonical-path for every skill-owned hook source.

    v0.11 (ADR-0040): skills moved to base/ + overlays/team/; walk both.
    """
    result: dict[str, Path] = {}
    for skill_root in (
        repo_root / "base" / "skills",
        repo_root / "overlays" / "team" / "skills",
    ):
        if not skill_root.exists():
            continue
        for path in skill_root.rglob("hooks/*.sh"):
            if path.name.startswith("_"):
                continue
            result[path.name] = path
    return result


def _wrapper_locations(
    hook_roots: list[Path], skill_owned: dict[str, Path]
) -> set[Path]:
    """All directories that may contain a Cursor wrapper hook."""
    dirs: set[Path] = set(hook_roots)
    for canonical in skill_owned.values():
        dirs.add(canonical.parent)
    return dirs


def _wrapper_name_from_header(line: str) -> str:
    """Parse the value of PLAYBOOK-HOOK-CURSOR-WRAPPER from a header line."""
    after_colon = line.split(":", 1)[1] if ":" in line else ""
    return after_colon.strip().lstrip("#").strip()


def run(ctx: CheckContext) -> CheckResult:
    repo_root = ctx.repo_root
    # v0.11 (ADR-0040): hooks moved to base/ + overlays/team/. Walk both
    # for unification (skill-owned hooks live under base/skills/).
    hook_roots = [
        repo_root / "base" / "hooks",
        repo_root / "overlays" / "team" / "hooks",
    ]
    hook_roots = [r for r in hook_roots if r.exists()]
    if not hook_roots:
        return CheckResult(
            status="ok",
            summary="hook source unification (no hooks dirs at base/ or overlays/team/)",
            details=[],
        )

    skill_owned = _skill_owned_hooks(repo_root)
    wrapper_search_dirs = _wrapper_locations(hook_roots, skill_owned)
    failures: list[str] = []

    canonical_root = 0
    canonical_skill = 0
    symlinked_root = 0

    root_hooks: list = []
    for root in hook_roots:
        root_hooks.extend(sorted(root.glob("*.sh")))
    for root_hook in root_hooks:
        if root_hook.name.startswith("_"):
            continue
        name = root_hook.name

        if name in skill_owned:
            target = skill_owned[name]
            if not root_hook.is_symlink():
                failures.append(
                    f"hooks/{name}: skill-owned canonical at "
                    f"{target.relative_to(repo_root)} exists but root is NOT a "
                    "symlink; two canonical bodies will drift"
                )
                continue
            try:
                resolved = root_hook.resolve(strict=True)
            except (OSError, RuntimeError) as exc:
                failures.append(f"hooks/{name}: symlink resolution failed ({exc})")
                continue
            if resolved != target.resolve():
                failures.append(
                    f"hooks/{name}: symlink resolves to {resolved}, expected {target}"
                )
                continue
            symlinked_root += 1
        else:
            if root_hook.is_symlink():
                link_target = os.readlink(root_hook)
                failures.append(
                    f"hooks/{name}: symlinked to {link_target} but no skill-owned "
                    "canonical with that basename exists"
                )
                continue
            canonical_root += 1

    canonical_skill = len(skill_owned)

    candidates = list(root_hooks) + list(skill_owned.values())
    for hook in candidates:
        if hook.name.startswith("_"):
            continue
        try:
            text = hook.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            failures.append(f"{hook}: cannot read ({exc})")
            continue
        for line in text.splitlines()[:30]:
            if "PLAYBOOK-HOOK-CURSOR-WRAPPER:" not in line:
                continue
            wrapper_name = _wrapper_name_from_header(line)
            if not wrapper_name:
                rel = hook.relative_to(repo_root)
                failures.append(f"{rel}: PLAYBOOK-HOOK-CURSOR-WRAPPER header is empty")
                continue
            located = any(
                (search_dir / wrapper_name).exists()
                for search_dir in wrapper_search_dirs
            )
            if not located:
                rel = hook.relative_to(repo_root)
                failures.append(
                    f"{rel}: PLAYBOOK-HOOK-CURSOR-WRAPPER points at "
                    f"'{wrapper_name}' but no such hook exists in hooks/ or any "
                    "skill-owned hooks/"
                )

    if failures:
        return CheckResult(
            status="fail",
            summary="hook source unification (ADR-0035 layer-1 integrity)",
            details=failures,
        )

    summary = (
        f"hook source unification: {canonical_root} root-canonical, "
        f"{symlinked_root} symlinked-to-skill, {canonical_skill} skill-owned"
    )
    return CheckResult(status="ok", summary=summary, details=[])
