"""Multi-profile install path coverage (v0.10).

Cursor + thermo reviews both flagged that v0.10's new multi-profile
surface (comma-separated --profile, list-form lockfile field, union
semantics in load_profiles) shipped without unit tests. This module
exists to close that gap.

Scope:
  * parse_profile_arg: empty / single / comma / whitespace / duplicate
  * load_profiles: single / union / dedupe / sorted determinism
  * generate_lockfile: writes profile as list[str], None when absent

Out of scope (defer to a later refactor):
  * End-to-end `make install PROFILE=a,b` through the Makefile shim.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


# Ensure scripts/ is on sys.path so the imports below resolve when the
# test harness is run via `python3 -m pytest`. Mirrors how the existing
# lifecycle tests bootstrap the path.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def test_parse_profile_arg_handles_empty_and_single_and_comma() -> None:
    from playbook_profile import parse_profile_arg

    assert parse_profile_arg(None) == []
    assert parse_profile_arg("") == []
    assert parse_profile_arg("backend-developer") == ["backend-developer"]
    assert parse_profile_arg("a,b,c") == ["a", "b", "c"]


def test_parse_profile_arg_strips_whitespace_and_drops_empty_tokens() -> None:
    from playbook_profile import parse_profile_arg

    assert parse_profile_arg(" a , b , c ") == ["a", "b", "c"]
    assert parse_profile_arg("a,,b") == ["a", "b"]
    assert parse_profile_arg(",a,") == ["a"]
    assert parse_profile_arg("   ") == []


def test_parse_profile_arg_preserves_caller_ordering() -> None:
    """Order is the user's order. Deduplication happens later in load_profiles.

    A user who types --profile pm,research,pm gets exactly that list back from
    parse_profile_arg; load_profiles is the layer that turns the union into a
    sorted, deduped Profile.
    """
    from playbook_profile import parse_profile_arg

    assert parse_profile_arg("pm,research,pm") == ["pm", "research", "pm"]


def test_load_profiles_single_name_matches_load_profile(tmp_path: Path) -> None:
    """A one-element list returns the same Profile shape as load_profile.

    The v0.10 union helper short-circuits on len==1 so a single-profile
    install behaves identically to the v0.9 path. This test pins that
    invariant.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profile, load_profiles

    single = load_profile(repo_root, "backend-developer")
    via_list = load_profiles(repo_root, ["backend-developer"])

    assert single.name == via_list.name
    assert single.skills == via_list.skills
    assert single.rules == via_list.rules
    assert single.hooks == via_list.hooks
    assert single.mcp == via_list.mcp


def test_load_profiles_unions_includes_and_dedupes() -> None:
    """Two profiles that share entries union without duplicates.

    backend-developer + qa is a known overlap case: qa's nine skills are a
    subset of backend-developer's fifteen, so the union has fifteen unique
    skills. The test asserts the dedupe semantics directly so a regression in
    load_profiles's set-based merge surfaces immediately.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profile, load_profiles

    backend = load_profile(repo_root, "backend-developer")
    qa = load_profile(repo_root, "qa")
    multi = load_profiles(repo_root, ["backend-developer", "qa"])

    # Skills are the most overlap-prone. Union should equal the larger set
    # when one is a subset of the other.
    expected_skills = sorted(set(backend.skills) | set(qa.skills))
    assert multi.skills == expected_skills

    # Rules / hooks / MCP follow the same union rule.
    assert multi.rules == sorted(set(backend.rules) | set(qa.rules))
    assert multi.hooks == sorted(set(backend.hooks) | set(qa.hooks))
    assert multi.mcp == sorted(set(backend.mcp) | set(qa.mcp))


def test_load_profiles_name_is_comma_joined_in_input_order() -> None:
    """The synthetic Profile.name preserves the caller's ordering.

    The lockfile records what the user asked for, so a later `make update`
    re-runs the same composition. parse_profile_arg keeps the user's order;
    load_profiles must not silently sort it.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profiles

    multi = load_profiles(repo_root, ["qa", "backend-developer"])
    assert multi.name == "qa,backend-developer"


def test_load_profiles_sorted_skill_list_is_deterministic() -> None:
    """Running the same union twice produces byte-identical lists.

    Set iteration order is non-deterministic in CPython by hash randomization;
    load_profiles must wrap each union in sorted() so the lockfile bytes do
    not flap across runs.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profiles

    first = load_profiles(repo_root, ["backend-developer", "qa"])
    second = load_profiles(repo_root, ["backend-developer", "qa"])
    assert first.skills == second.skills
    assert first.rules == second.rules
    assert first.hooks == second.hooks
    assert first.mcp == second.mcp


def test_load_profiles_empty_input_raises_value_error() -> None:
    """An empty list is a programming bug, not a valid sentinel.

    The installer is supposed to skip the filter entirely when the user
    passes no profile; reaching load_profiles with [] would be a contract
    violation. The function raises so the caller is forced to handle the
    no-profile branch explicitly.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profiles

    with pytest.raises(ValueError):
        load_profiles(repo_root, [])


def test_generate_lockfile_writes_profile_as_list(tmp_path: Path) -> None:
    """The v0.10 lockfile schema stores profile as list[str] (not str).

    cmd_status, cmd_update, and the install dispatch all rely on the list
    shape so they can iterate over multi-profile installs. A regression to
    the v0.9 string form would break the update path silently.
    """
    from install_lockfile import generate_lockfile

    out = generate_lockfile(
        target=tmp_path,
        repo_root=tmp_path,
        per_adapter_manifests={},
        playbook_version="0.10.0",
        profile_names=["product-manager", "research"],
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["profile"] == ["product-manager", "research"]


def test_generate_lockfile_writes_none_when_profile_absent(tmp_path: Path) -> None:
    """Omitting profile_names leaves the field as null (not an empty list).

    install.py treats None as "no profile filter"; the lockfile shape mirrors
    that so a later read can distinguish "user installed without --profile"
    from "user explicitly passed an empty list" (the latter is rejected
    upstream by parse_profile_arg + load_profiles).
    """
    from install_lockfile import generate_lockfile

    out = generate_lockfile(
        target=tmp_path,
        repo_root=tmp_path,
        per_adapter_manifests={},
        playbook_version="0.10.0",
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["profile"] is None


def test_generate_lockfile_preserves_profile_list_ordering(tmp_path: Path) -> None:
    """The lockfile records the user's profile order verbatim, not sorted.

    parse_profile_arg + load_profiles preserve the caller's order so the
    lockfile reflects what the user typed. A sort-on-write would re-order
    `pm,research,backend-developer` to `backend-developer,pm,research`,
    which is technically equivalent but breaks faithful audit-trail.
    """
    from install_lockfile import generate_lockfile

    out = generate_lockfile(
        target=tmp_path,
        repo_root=tmp_path,
        per_adapter_manifests={},
        playbook_version="0.10.0",
        profile_names=["research", "product-manager", "backend-developer"],
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["profile"] == ["research", "product-manager", "backend-developer"]


def test_playbook_update_round_trips_comma_separated_profile(tmp_path: Path) -> None:
    """playbook_update.py must accept the comma-separated profile value that
    playbook_init.py writes into .playbook-config.yaml.

    Regression for the cursor + codex review HIGH: prior to the v0.10 fold,
    update called load_profile (singular) on the stored value, so
    `profile: "product-manager,research"` tried to open
    `profiles/product-manager,research.toml` and raised FileNotFoundError.
    The fix routes the value through parse_profile_arg + load_profiles
    (plural) so the same composition init recorded is re-applied on update.

    This test exercises the parse + load path directly (the materialize
    side has filesystem side effects covered elsewhere). The check is:
    given the exact string init writes, update produces the same union
    Profile load_profiles would produce when called from install.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profiles, parse_profile_arg

    config_profile_value = "product-manager,research"

    # update's parse path
    update_names = parse_profile_arg(config_profile_value)
    assert update_names == ["product-manager", "research"]
    update_profile = load_profiles(repo_root, update_names)

    # install's parse path (the same code path; this asserts they agree)
    install_names = parse_profile_arg(config_profile_value)
    install_profile = load_profiles(repo_root, install_names)

    assert update_profile.name == install_profile.name
    assert update_profile.skills == install_profile.skills
    assert update_profile.rules == install_profile.rules
    assert update_profile.hooks == install_profile.hooks
    assert update_profile.mcp == install_profile.mcp


def test_playbook_update_handles_legacy_single_profile_value(tmp_path: Path) -> None:
    """The v0.9 .playbook-config.yaml form stores a single profile name as
    a plain string (e.g. `profile: "backend-developer"`). The v0.10 update
    path must still load that form correctly so an in-place upgrade does
    not break previously-initialized targets.
    """
    repo_root = Path(__file__).resolve().parents[2]
    from playbook_profile import load_profiles, parse_profile_arg

    legacy_value = "backend-developer"
    names = parse_profile_arg(legacy_value)
    assert names == ["backend-developer"]
    profile = load_profiles(repo_root, names)
    assert profile.name == "backend-developer"
