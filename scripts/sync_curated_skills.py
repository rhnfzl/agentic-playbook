#!/usr/bin/env python3
"""Sync curated upstream PM / research skill imports into skills/imported/<set>/.

Per ADR-0019, vendored content keeps its upstream SKILL.md body verbatim and
injects three additional frontmatter fields the playbook installer expects:
`version`, `owner`, `last_reviewed`. The mattpocock sync (sync_mattpocock.sh)
does this for bulk-imported subtrees; this Python helper does the same for
curated picks where the playbook only imports a hand-selected subset of the
upstream repo.

Each imported set has a SOURCES.toml at its root listing the (upstream, path)
pairs the script reads in. The upstream registry is a small dict in this
file:

    UPSTREAMS = {
        "phuryn": ("https://github.com/phuryn/pm-skills.git", <pin>, "MIT"),
        ...
    }

Workflow:

    1. For each upstream named in any SOURCES.toml, shallow-clone into a temp
       directory (idempotent across sets in one run).
    2. For each (upstream, path) entry, read the upstream SKILL.md, inject
       version + owner + last_reviewed into the YAML frontmatter, write to
       `skills/imported/<set>/<slug>/SKILL.md`.
    3. Print a diff summary of inserted / unchanged / removed slugs.

Run as `python3 scripts/sync_curated_skills.py` from the repo root.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent

UPSTREAMS: dict[str, dict[str, str]] = {
    "phuryn": {
        "url": "https://github.com/phuryn/pm-skills.git",
        "pin": "f9eaa51000a65e04494aeaf90355d30f2080ebf2",
        "license": "MIT",
    },
    "product-on-purpose": {
        "url": "https://github.com/product-on-purpose/pm-skills.git",
        "pin": "498cad9418a7ca50d0132b93ec77e8f0d66f7166",
        "license": "Apache 2.0",
    },
}

INJECTED_VERSION = "1.0.0"
INJECTED_OWNER = "rehan (vendored)"
INJECTED_LAST_REVIEWED = date.today().isoformat()


def clone_upstream(name: str, dest: Path) -> Path:
    """Shallow-fetch the upstream at the exact pinned SHA into dest/name.

    The first version of this helper did `git clone --depth 1 <url>` and
    silently fetched whatever was at the upstream's default-branch HEAD.
    That meant `make sync-curated-skills` could vendor entirely different
    bytes than the PROVENANCE.md + UPSTREAMS dict claimed, breaking the
    reproducibility promise.

    The current version initializes an empty repo, adds the upstream as a
    remote, fetches exactly the pinned SHA (shallow), checks it out, and
    verifies HEAD matches the pin. Failure to fetch the pin (e.g. the
    upstream force-pushed and the SHA is unreachable) raises SystemExit
    so the sync fails closed instead of silently picking up HEAD.
    """
    upstream = UPSTREAMS[name]
    clone_path = dest / name
    pin = upstream["pin"]
    url = upstream["url"]

    clone_path.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "init", "--quiet"],
        cwd=clone_path,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", url],
        cwd=clone_path,
        check=True,
    )

    try:
        subprocess.run(
            ["git", "fetch", "--depth", "1", "origin", pin],
            cwd=clone_path,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"failed to fetch pinned SHA {pin} from {url}: the upstream may "
            f"have force-pushed or rewritten history. Update UPSTREAMS in "
            f"scripts/sync_curated_skills.py with a current SHA and retry. "
            f"git stderr: {exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc

    subprocess.run(
        ["git", "checkout", "--quiet", pin],
        cwd=clone_path,
        check=True,
    )

    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=clone_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if head != pin:
        raise SystemExit(
            f"upstream pin verification failed for {name}: expected {pin}, "
            f"got {head}. This should not be reachable; report as a bug."
        )

    return clone_path


def inject_frontmatter(text: str) -> str:
    """Inject version, owner, last_reviewed into a SKILL.md's YAML frontmatter.

    The upstream files start with `---\nname: ...\n...\n---\n`. We insert the
    three new fields after the existing frontmatter fields, before the
    closing `---`. Fields the playbook already requires (name, description)
    are preserved verbatim.

    If frontmatter is missing (a malformed upstream file), the function
    raises ValueError so the caller can surface it loudly rather than
    write a broken skill into the playbook.
    """
    if not text.startswith("---\n"):
        raise ValueError("upstream SKILL.md does not start with --- frontmatter")
    end_marker = text.find("\n---\n", 4)
    if end_marker < 0:
        raise ValueError("upstream SKILL.md frontmatter is unclosed")
    head = text[4:end_marker]
    body = text[end_marker + 5 :]
    injected = (
        head.rstrip("\n")
        + f"\nversion: {INJECTED_VERSION}"
        + f"\nowner: {INJECTED_OWNER}"
        + f"\nlast_reviewed: {INJECTED_LAST_REVIEWED}\n"
    )
    return f"---\n{injected}---\n{body}"


def slug_from_path(path: str) -> str:
    """Derive the playbook-side slug from the upstream path.

    Upstream layouts vary:
      phuryn:               pm-execution/skills/sprint-plan        -> sprint-plan
      product-on-purpose:   skills/discover-market-sizing          -> discover-market-sizing
                            skills/utility-pm-critic               -> utility-pm-critic

    The slug is the basename of the upstream skill dir. Set-level
    collisions are surfaced by the caller (two entries map to the same
    target dir).
    """
    parts = path.strip("/").split("/")
    return parts[-1]


def sync_set(set_name: str, clones: dict[str, Path]) -> tuple[int, int]:
    """Sync one imported set (e.g. pm-curated). Returns (copied, removed).

    v0.11 (ADR-0040): imported sets moved to base/skills/imported/<set>/.
    """
    set_dir = REPO_ROOT / "base" / "skills" / "imported" / set_name
    sources_file = set_dir / "SOURCES.toml"
    if not sources_file.is_file():
        print(f"  skip: {set_name} (no SOURCES.toml at {sources_file})")
        return (0, 0)

    with sources_file.open("rb") as fh:
        sources = tomllib.load(fh)

    # First pass: detect slug collisions explicitly. Two SOURCES.toml entries
    # whose upstream paths share a basename map to the same local directory
    # and silently overwrite each other if the second write wins. Fail
    # loud so the curator either renames one or removes the duplicate.
    seen_slugs: dict[str, tuple[str, str]] = {}
    for entry in sources.get("skills", []):
        slug = slug_from_path(entry["path"])
        prior = seen_slugs.get(slug)
        if prior is not None:
            raise SystemExit(
                f"slug collision in {set_name}/SOURCES.toml: '{slug}' is "
                f"produced by both '{prior[0]}:{prior[1]}' and "
                f"'{entry['upstream']}:{entry['path']}'. Resolve by removing "
                f"one entry or renaming the target dir (the script does not "
                f"rename automatically)."
            )
        seen_slugs[slug] = (entry["upstream"], entry["path"])

    desired_slugs: set[str] = set()
    copied = 0
    for entry in sources.get("skills", []):
        upstream = entry["upstream"]
        path = entry["path"]
        slug = slug_from_path(path)
        desired_slugs.add(slug)

        if upstream not in clones:
            raise SystemExit(
                f"unknown upstream '{upstream}' referenced by {set_name}/{slug}; "
                f"add it to UPSTREAMS in sync_curated_skills.py"
            )
        upstream_skill = clones[upstream] / path / "SKILL.md"
        if not upstream_skill.is_file():
            raise SystemExit(
                f"upstream skill missing: {upstream_skill} (referenced by "
                f"{set_name}/{slug})"
            )

        target_dir = set_dir / slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target_file = target_dir / "SKILL.md"
        original = upstream_skill.read_text(encoding="utf-8")
        try:
            injected = inject_frontmatter(original)
        except ValueError as exc:
            raise SystemExit(
                f"malformed upstream frontmatter at {upstream_skill} "
                f"(referenced by {set_name}/{slug}): {exc}. Either fix the "
                f"upstream SKILL.md, switch to an upstream pin that predates "
                f"the breakage, or drop this entry from {set_name}/SOURCES.toml."
            ) from exc
        target_file.write_text(injected, encoding="utf-8")
        copied += 1

    removed = 0
    for child in sorted(set_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name not in desired_slugs:
            shutil.rmtree(child)
            removed += 1

    print(
        f"  {set_name}: {copied} skill(s) copied, "
        f"{removed} stale dir(s) removed"
    )
    return (copied, removed)


def main() -> int:
    # v0.11 (ADR-0040): imported skills moved to base/skills/imported/.
    sets_dir = REPO_ROOT / "base" / "skills" / "imported"
    if not sets_dir.is_dir():
        print(f"ERROR: {sets_dir} does not exist; nothing to sync.", file=sys.stderr)
        return 1

    set_dirs = [p for p in sorted(sets_dir.iterdir()) if (p / "SOURCES.toml").is_file()]
    if not set_dirs:
        print("No imported sets with SOURCES.toml found; nothing to sync.")
        return 0

    upstreams_needed: set[str] = set()
    for set_dir in set_dirs:
        with (set_dir / "SOURCES.toml").open("rb") as fh:
            data = tomllib.load(fh)
        for entry in data.get("skills", []):
            upstreams_needed.add(entry["upstream"])

    print(f"Syncing {len(set_dirs)} imported set(s): {', '.join(d.name for d in set_dirs)}")
    print(f"Upstreams needed: {', '.join(sorted(upstreams_needed))}")

    # Validate upstream names BEFORE the first clone. Without this, a typo in
    # SOURCES.toml crashes with a raw KeyError inside clone_upstream() once a
    # different upstream has already cloned, which is both a confusing error
    # and a wasted network round-trip. Surfacing the typo here lets the
    # curator fix SOURCES.toml in one pass.
    unknown_upstreams = sorted(upstreams_needed - UPSTREAMS.keys())
    if unknown_upstreams:
        print(
            f"\nERROR: unknown upstream(s) referenced by SOURCES.toml: "
            f"{', '.join(unknown_upstreams)}",
            file=sys.stderr,
        )
        print(
            f"Known upstreams: {', '.join(sorted(UPSTREAMS.keys()))}",
            file=sys.stderr,
        )
        print(
            "Add the missing entry to UPSTREAMS in scripts/sync_curated_skills.py "
            "(URL + pin + license), or fix the typo in the offending SOURCES.toml.",
            file=sys.stderr,
        )
        return 2

    with tempfile.TemporaryDirectory(prefix="sync-curated-skills-") as tmp:
        tmp_path = Path(tmp)
        clones: dict[str, Path] = {}
        for upstream in sorted(upstreams_needed):
            print(f"  cloning {upstream} ...")
            clones[upstream] = clone_upstream(upstream, tmp_path)

        total_copied = total_removed = 0
        for set_dir in set_dirs:
            copied, removed = sync_set(set_dir.name, clones)
            total_copied += copied
            total_removed += removed

    print(
        f"\nDone. {total_copied} skill(s) copied, {total_removed} stale dir(s) removed."
    )
    print(
        "Reminder: review the diff, run `make check`, then commit. Pin SHAs "
        "live in UPSTREAMS in this script; bump them when an upstream advances."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
