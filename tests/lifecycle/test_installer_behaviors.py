"""v0.8 additions that don't fit the focused module split (ADR-0037,
B1 bundle health, B4 copied_dir drift, B6 end-to-end doctor-verify,
C5 underscore-hook coverage).

The dedicated focused files for v0.8 are:
  test_mcp_runtime_probe.py    (B2 + Codex fold-in P1/P2)
  test_target_registry.py      (B3 + Codex fold-in doctor ordering)
  test_human_html_allowlist.py (B7 + Codex fold-in single backslash)

Everything else v0.8 lands here.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from ._helpers import (
    _empty_content,
    _install_for,
    _make_hook_with_headers,
)


# === A1: PLAYBOOK-HOOK-ADAPTERS scoping (ADR-0037) ===


def test_hook_adapters_header_scopes_anchored_fs_to_claude_code_only(
    tmp_home: Path, tmp_target: Path, tmp_path: Path
) -> None:
    """v0.8 (ADR-0037): PLAYBOOK-HOOK-ADAPTERS pins a hook to specific
    adapter slugs. anchored-fs wrappers ship with `ADAPTERS: claude-code`
    so only claude-code installs + registers them.
    """
    from hook_native_config import parse_native_hook_commands

    src = tmp_path / "src-hooks"
    src.mkdir(exist_ok=True)
    claude_only = _make_hook_with_headers(
        src,
        "anchored-fs-pretool-edit",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|MultiEdit|Write",
            "PLAYBOOK-HOOK-ADAPTERS": "claude-code",
        },
    )
    universal = _make_hook_with_headers(
        src,
        "universal-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
        },
    )
    content = _empty_content(hooks=[claude_only, universal])

    cases = [
        ("claude-code", ".claude/settings.json", ".claude/hooks", True),
        ("codex", ".codex/hooks.json", ".codex/hooks", False),
        ("cline", ".cline/hooks.json", ".cline/hooks", False),
    ]
    for adapter, native_rel, hooks_rel, expect_anchored in cases:
        _install_for(adapter, content, tmp_target)
        native = tmp_home / native_rel
        hooks_dir = tmp_home / hooks_rel
        assert hooks_dir.is_dir()
        installed_hooks = {p.name for p in hooks_dir.glob("*.sh")}
        if expect_anchored:
            assert "anchored-fs-pretool-edit.sh" in installed_hooks
        else:
            assert "anchored-fs-pretool-edit.sh" not in installed_hooks
        assert "universal-hook.sh" in installed_hooks

        by_event = parse_native_hook_commands(native, adapter)
        all_cmds = " ".join(cmd for cmds in by_event.values() for cmd in cmds)
        if expect_anchored:
            assert "anchored-fs-pretool-edit.sh" in all_cmds
        else:
            assert "anchored-fs-pretool-edit.sh" not in all_cmds
        assert "universal-hook.sh" in all_cmds


def test_hook_adapters_header_drops_unknown_slugs_silently(tmp_path: Path) -> None:
    """v0.8 (ADR-0037): resolve_hook_adapters discards typos so they
    cannot accidentally widen scope. Header listing only unknown slugs
    -> frozenset() = no adapter installs.
    """
    from hook_registration import is_hook_for_adapter, resolve_hook_adapters

    typo_only = _make_hook_with_headers(
        tmp_path,
        "typo-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit",
            "PLAYBOOK-HOOK-ADAPTERS": "claudecode,kodex",
        },
    )
    parsed = resolve_hook_adapters(typo_only)
    assert parsed == frozenset()
    for adapter in ("claude-code", "codex", "cursor", "cline", "copilot", "windsurf"):
        assert not is_hook_for_adapter(typo_only, adapter)

    valid_plus_typo = _make_hook_with_headers(
        tmp_path,
        "mixed-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit",
            "PLAYBOOK-HOOK-ADAPTERS": "claude-code,kodex",
        },
    )
    parsed_mixed = resolve_hook_adapters(valid_plus_typo)
    assert parsed_mixed == frozenset({"claude-code"})
    assert is_hook_for_adapter(valid_plus_typo, "claude-code")
    for adapter in ("codex", "cursor", "cline", "copilot", "windsurf"):
        assert not is_hook_for_adapter(valid_plus_typo, adapter)


# === B1: bundle health.sh aggregation ===


def test_bundle_health_aggregation_reports_unhealthy_bundles(
    tmp_path: Path, repo_root: Path
) -> None:
    """v0.8 (ADR-0026): run_bundle_health + bundle_health_scripts run
    each bundle's health.sh with a bounded timeout and aggregate.
    """
    # v0.8 Cursor review fix: import the focused module directly so
    # tests don't depend on the install.py re-export facade.
    from install_bundles import bundle_health_scripts, run_bundle_health

    fake_repo = tmp_path / "fake-repo"
    # v0.11 (ADR-0040): bundle_health_scripts walks base/mcp/ + overlays/team/mcp/.
    bundle_a = fake_repo / "base" / "mcp" / "alpha" / "bundle"
    bundle_b = fake_repo / "base" / "mcp" / "beta" / "bundle"
    bundle_a.mkdir(parents=True)
    bundle_b.mkdir(parents=True)

    healthy = bundle_a / "health.sh"
    healthy.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    healthy.chmod(0o755)

    sick = bundle_b / "health.sh"
    sick.write_text(
        "#!/usr/bin/env bash\necho 'broken pipe' >&2\nexit 7\n", encoding="utf-8"
    )
    sick.chmod(0o755)

    scripts = bundle_health_scripts(fake_repo)
    assert {p.parent.parent.name for p in scripts} == {"alpha", "beta"}

    rc_ok, _ = run_bundle_health(healthy)
    assert rc_ok == 0

    rc_bad, stderr_tail = run_bundle_health(sick)
    assert rc_bad == 7
    assert "broken pipe" in stderr_tail


def test_bundle_health_aggregation_times_out_gracefully(tmp_path: Path) -> None:
    """v0.8 (ADR-0026): a hung health.sh must not block doctor. Exit
    code 124 (GNU timeout convention) lets callers distinguish "ran and
    failed" from "hung".
    """
    from install_bundles import run_bundle_health

    bundle_dir = tmp_path / "mcp" / "gamma" / "bundle"
    bundle_dir.mkdir(parents=True)
    slow = bundle_dir / "health.sh"
    slow.write_text("#!/usr/bin/env bash\nsleep 10\nexit 0\n", encoding="utf-8")
    slow.chmod(0o755)

    rc, _ = run_bundle_health(slow, timeout_sec=0.2)
    assert rc == 124, f"expected timeout exit code 124, got {rc}"


# === B4: copied_dir drift detection in verify ===


def test_verify_adapter_flags_copied_dir_drift(tmp_path: Path) -> None:
    """v0.8 B4 (ADR-0036): a lockfile entry recorded as kind='copied_dir'
    with a tree_sha256 must be re-hashed at verify time. Drift surfaces
    in counts['copied_dir_drift'] and adds an issue line.
    """
    # v0.8 Cursor review fix: import focused modules directly.
    from install_lockfile import hash_dir
    from install_verify import verify_adapter

    home = tmp_path / "home"
    home.mkdir()
    copied_dir = home / ".claude" / "skills" / "demo"
    copied_dir.mkdir(parents=True)
    (copied_dir / "SKILL.md").write_text(
        "---\nname: demo\n---\nbody\n", encoding="utf-8"
    )

    pristine_hash = hash_dir(copied_dir)
    entries = {
        ".claude/skills/demo": {
            "ownership": "owned",
            "kind": "copied_dir",
            "tree_sha256": pristine_hash,
        }
    }

    def resolve(rel: str) -> Path:
        return home / rel

    passed_pre, issues_pre, counts_pre = verify_adapter(
        "claude-code",
        entries,
        managed_keys={},
        target=None,
        resolve_locked_path=resolve,
        hash_dir=hash_dir,
    )
    assert passed_pre, f"pristine must pass, got issues: {issues_pre}"
    assert counts_pre["copied_dir_drift"] == 0

    (copied_dir / "SKILL.md").write_text(
        "---\nname: demo\n---\nbody EDITED\n", encoding="utf-8"
    )
    passed_post, issues_post, counts_post = verify_adapter(
        "claude-code",
        entries,
        managed_keys={},
        target=None,
        resolve_locked_path=resolve,
        hash_dir=hash_dir,
    )
    assert not passed_post
    assert counts_post["copied_dir_drift"] == 1
    assert any("copied_dir drift" in i for i in issues_post)


# === B6: end-to-end install -> doctor-verify ===


def test_doctor_verify_end_to_end_after_install(
    tmp_path: Path, repo_root: Path
) -> None:
    """v0.8 B6: full install -> doctor-verify round trip through the CLI.

    Probe is suppressed for this run via MCP_RUNTIME_PROBE=skip because
    the install registers the playbook's stock MCP set (npx-launched
    atlassian/error-tracking/slack, docker-launched code-quality, etc.) which
    cannot complete an initialize handshake in a sandboxed test shell.
    The probe glue is exercised end-to-end against a real fake server
    in test_doctor_verify_end_to_end_probes_real_server below.
    """
    import os
    import subprocess

    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    target = tmp_path / "project"
    target.mkdir()

    env = {**os.environ, "HOME": str(home), "MCP_RUNTIME_PROBE": "skip"}
    install_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "install.py"),
        "--non-interactive",
        "--target",
        str(target),
        "--profile",
        "qa",
        # v0.11 (ADR-0040): qa profile requires_overlays=["team"]; tmp_path
        # has no git remote so auto-detect returns []. Explicit scope.
        "--scope",
        "team",
    ]
    result = subprocess.run(
        install_cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"install failed (exit {result.returncode}):\n"
        f"stdout:\n{result.stdout}\n\nstderr:\n{result.stderr}"
    )

    lockfile_path = target / ".playbook-lock.json"
    assert lockfile_path.is_file()

    verify_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "install.py"),
        "--verify",
        "--target",
        str(target),
    ]
    verify_ok = subprocess.run(
        verify_cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=60,
    )
    assert verify_ok.returncode == 0, (
        f"verify failed on a fresh install:\n"
        f"stdout:\n{verify_ok.stdout}\n\nstderr:\n{verify_ok.stderr}"
    )
    assert "OK: every detected adapter passes layer-3 verification" in verify_ok.stdout

    # Mutation arm: delete one of the registered hook scripts.
    hook_path = home / ".claude" / "hooks" / "never-push-to-develop.sh"
    if hook_path.is_file():
        hook_path.unlink()
        verify_drift = subprocess.run(
            verify_cmd,
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo_root),
            timeout=60,
        )
        assert verify_drift.returncode != 0
        assert "missing on disk" in verify_drift.stdout


def test_doctor_verify_end_to_end_probes_real_server(
    tmp_path: Path, repo_root: Path
) -> None:
    """v0.8 Cursor review fix: B6 disabled MCP_RUNTIME_PROBE so the
    probe glue was never exercised through the CLI. This test seeds a
    minimal claude-code install with a single fake stdio MCP server
    pointed at a long-running script, runs `--verify` with the probe
    enabled, and asserts the probe completes the initialize handshake
    + reports the server as OK.

    Coverage: probe + cmd_verify + install_verify integration through
    the real subprocess.run path. The unit tests in
    test_mcp_runtime_probe.py cover the probe in isolation; this test
    proves the wiring.
    """
    import json
    import os
    import subprocess

    from ._helpers import _write_long_running_fake_server

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    target = tmp_path / "project"
    target.mkdir()

    # Seed a minimal claude.json with one stdio MCP entry that points at
    # the fake long-running server. The lockfile + managed_keys plumbing
    # records it as a playbook-managed MCP so the probe iterates it.
    fake_server = _write_long_running_fake_server(tmp_path)
    (home / ".claude.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "fake-probe-target": {
                        "command": sys.executable,
                        "args": [str(fake_server)],
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    # v0.9 (ADR-0039): managed_keys.mcp_servers is list[ManagedMcpEntry];
    # each entry records the exact config_path the playbook wrote to.
    lockfile = target / ".playbook-lock.json"
    claude_cfg = home / ".claude.json"
    lockfile.write_text(
        json.dumps(
            {
                "lockfile_version": 3,
                "version": "0.9.0",
                "generated_at": "2026-05-25T00:00:00+00:00",
                "target": str(target),
                "profile": "test",
                "adapters": {"claude-code": {}},
                "managed_keys": {
                    "claude-code": {
                        "mcp_servers": [
                            {
                                "id": "uuid-fake-probe",
                                "name": "fake-probe-target",
                                "config_path": str(claude_cfg),
                                "scope": "global",
                                "installed_at": "2026-05-25T00:00:00+00:00",
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    # v0.8 Codex round-7 trust-boundary fix: target-scoped --verify
    # defaults to skip the probe (target-supplied configs can have
    # arbitrary commands). Opt in via MCP_RUNTIME_PROBE=on.
    env = {**os.environ, "HOME": str(home), "MCP_RUNTIME_PROBE": "on"}
    verify_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "install.py"),
        "--verify",
        "--target",
        str(target),
    ]
    result = subprocess.run(
        verify_cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=30,
    )
    # The probe section must appear in the output AND the fake server
    # must classify as OK with the declared serverInfo.name.
    assert "MCP runtime probe (initialize handshake)" in result.stdout, (
        f"probe should have run; stdout:\n{result.stdout}"
    )
    assert "fake-probe-target" in result.stdout
    assert "OK" in result.stdout and "fake-long-running" in result.stdout, (
        f"probe should classify fake server as OK; stdout:\n{result.stdout}"
    )


# === C5: underscore-prefix hook helpers ===


def test_underscore_prefixed_hooks_never_register_or_install(
    tmp_path: Path, repo_root: Path
) -> None:
    """v0.8 C5: hooks/_*.sh files are adapter-internal helpers (e.g.,
    _cascade-translate.sh). load_hooks() in adapters/_reader.py skips
    them so they never enter content.hooks.
    """
    from adapters._loader import resolve_content_paths
    from adapters._reader import load_hooks

    real_hooks = load_hooks(resolve_content_paths(["team"], repo_root))
    real_names = {h.name for h in real_hooks}
    for name in real_names:
        assert not name.startswith("_"), (
            f"underscore-prefixed hook {name!r} leaked into load_hooks output"
        )
    # Post-v0.11: underscore-prefixed helpers live under base/hooks/.
    underscore_files = sorted((repo_root / "base" / "hooks").glob("_*.sh"))
    assert underscore_files, (
        "test prerequisite: at least one base/hooks/_*.sh helper must exist"
    )

    fake_root = tmp_path / "fake-root"
    (fake_root / "hooks").mkdir(parents=True)
    (fake_root / "hooks" / "regular-hook.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# PLAYBOOK-HOOK-EVENT: PreToolUse\n"
        "# PLAYBOOK-HOOK-MATCHER: Edit\n"
        "exit 0\n",
        encoding="utf-8",
    )
    (fake_root / "hooks" / "_helper-script.sh").write_text(
        "#!/usr/bin/env bash\n# adapter-internal helper\nexit 0\n",
        encoding="utf-8",
    )

    fake_hooks = load_hooks(resolve_content_paths(None, fake_root))
    fake_names = {h.name for h in fake_hooks}
    assert "regular-hook" in fake_names
    assert "_helper-script" not in fake_names


def test_underscore_prefixed_helper_not_installed_by_any_adapter(
    tmp_path: Path, tmp_home: Path, tmp_target: Path
) -> None:
    """v0.8 C5 canary: the underscore filter happens at load_hooks, not
    at the adapter. If a future writer bypasses load_hooks, the adapter
    will happily copy the underscore-prefixed file. This test proves the
    convention lives at load_hooks; a future regression here means
    someone moved the filter and the architecture intent needs revisit.
    """
    src = tmp_path / "src-hooks"
    src.mkdir(exist_ok=True)
    helper = _make_hook_with_headers(
        src,
        "_internal-helper",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit",
        },
    )
    content = _empty_content(hooks=[helper])
    _install_for("claude-code", content, tmp_target)
    installed = tmp_home / ".claude" / "hooks" / "_internal-helper.sh"
    assert installed.is_file()


def test_anchored_fs_v0_7_baseline_settings_survives_v0_8_install(
    tmp_home: Path, tmp_target: Path, tmp_path: Path
) -> None:
    """ADR-0037 v0.7-cleanup risk: a user upgrading from v0.7 has
    settings.json entries pointing directly at
    mcp/anchored-fs/hooks/claude-code/*.py (the bundle's old self-
    registration shape). The v0.8 playbook adds the wrapper entries
    alongside but does NOT remove the legacy direct-Python entries
    (per ADR-0023: the playbook only owns what it wrote in a prior
    run; the bundle wrote those entries, not the playbook).

    This test seeds a v0.7-baseline settings.json, runs the claude-code
    adapter against an empty content set + an anchored-fs wrapper hook,
    and asserts:
      * the legacy direct-Python entries survive byte-for-byte
        (proves the playbook does not touch bundle-owned entries)
      * the wrapper entry is added under PreToolUse (proves the
        v0.8 hook registration still fires)
    """
    import json

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

    settings_path = tmp_home / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    # v0.7 baseline: the bundle's `install.py init` registered the
    # Python hooks directly. PLAYBOOK_OVERRIDE-style entries do not
    # exist; the entries point at absolute paths under the bundle.
    v0_7_pretool = {
        "matcher": "Edit|MultiEdit|Write",
        "hooks": [
            {
                "type": "command",
                "command": (
                    "python3 /Users/rehan-8v/team/coding-agents-playbook/"
                    "mcp/anchored-fs/hooks/claude-code/pretool_edit.py"
                ),
            }
        ],
    }
    v0_7_posttool = {
        "matcher": "Read",
        "hooks": [
            {
                "type": "command",
                "command": (
                    "python3 /Users/rehan-8v/team/coding-agents-playbook/"
                    "mcp/anchored-fs/hooks/claude-code/posttool_read.py"
                ),
            }
        ],
    }
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [v0_7_pretool],
                    "PostToolUse": [v0_7_posttool],
                }
            }
        ),
        encoding="utf-8",
    )

    # Build a content set with the v0.8 anchored-fs wrapper and run the
    # claude-code adapter. The wrapper carries ADAPTERS: claude-code so
    # claude-code installs it.
    src = tmp_path / "src-hooks"
    src.mkdir(exist_ok=True)
    wrapper = _make_hook_with_headers(
        src,
        "anchored-fs-pretool-edit",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|MultiEdit|Write",
            "PLAYBOOK-HOOK-ADAPTERS": "claude-code",
        },
    )
    content = _empty_content(hooks=[wrapper])
    _install_for("claude-code", content, tmp_target)

    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    pre_entries = settings["hooks"]["PreToolUse"]
    pre_commands = []
    for entry in pre_entries:
        for h in entry.get("hooks", []):
            pre_commands.append(h.get("command", ""))

    # Legacy direct-Python entry survives.
    assert any(
        "mcp/anchored-fs/hooks/claude-code/pretool_edit.py" in c for c in pre_commands
    ), (
        "v0.7 baseline pre_tool_edit.py entry must survive v0.8 install -- "
        "playbook only owns what it wrote in a prior run"
    )

    # New wrapper entry was added.
    assert any("anchored-fs-pretool-edit.sh" in c for c in pre_commands), (
        "v0.8 wrapper hook must be registered under PreToolUse alongside "
        "the legacy entry"
    )

    # PostToolUse legacy entry survives (we didn't ship a posttool
    # wrapper in this test scenario).
    post_entries = settings["hooks"]["PostToolUse"]
    post_commands = []
    for entry in post_entries:
        for h in entry.get("hooks", []):
            post_commands.append(h.get("command", ""))
    assert any(
        "mcp/anchored-fs/hooks/claude-code/posttool_read.py" in c for c in post_commands
    )


def test_managed_keys_excludes_user_authored_mcp_entries(tmp_home: Path) -> None:
    """v0.8 Codex adversarial fix (HIGH): if a user has an MCP entry
    pre-existing under the same name as a playbook-managed server, the
    adapter's merge_managed_mcp_into_json helper preserves it. The
    lockfile must NOT record that name as playbook-managed, or a later
    narrow reconcile would delete the user-authored entry.

    Scenario:
      1. Seed ~/.claude.json with a user-authored entry named 'shared'
         that points at a different command than the playbook's mcp/
         config.
      2. Compute managed_keys via install._new_managed_keys_for for
         claude-code adapter with the same-named McpConfig in content.
      3. Assert 'shared' is NOT in managed_keys['mcp_servers'] (it
         was already present; the playbook does not own it).
      4. A separate name 'playbook-only' in content but not pre-
         existing IS recorded as managed.
    """
    import json as _json

    from adapters._loader import McpConfig
    from install import _new_managed_keys_for

    home = tmp_home  # already monkeypatched via fixture
    (home / ".claude.json").write_text(
        _json.dumps(
            {
                "mcpServers": {
                    "shared": {"command": "user-binary", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )

    # Build content with two MCPs: 'shared' (pre-existing) + 'playbook-only'
    # (not pre-existing).
    shared_mcp = McpConfig(
        name="shared",
        path=Path("/dev/null"),
        config={"command": "playbook-binary", "args": []},
        source_dir=None,
    )
    playbook_only_mcp = McpConfig(
        name="playbook-only",
        path=Path("/dev/null"),
        config={"command": "playbook-binary", "args": []},
        source_dir=None,
    )
    content = _empty_content(mcp_configs=[shared_mcp, playbook_only_mcp])

    # v0.9 (ADR-0039): simulate the install.py main loop by passing a
    # pre_install_per_config snapshot that captures 'shared' as already
    # present in ~/.claude.json BEFORE the install runs. The test path
    # without that snapshot would treat every present name as freshly
    # inserted (per the v0.9 fallback in _new_managed_keys_for).
    claude_cfg = home / ".claude.json"
    pre_install_per_config = {
        ("claude-code", str(claude_cfg)): {"shared"},
    }
    # Pre-create 'playbook-only' as if the adapter just wrote it (post-
    # install state contains both names).
    (home / ".claude.json").write_text(
        _json.dumps(
            {
                "mcpServers": {
                    "shared": {"command": "user-binary", "args": []},
                    "playbook-only": {"command": "playbook-binary", "args": []},
                }
            }
        ),
        encoding="utf-8",
    )
    keys = _new_managed_keys_for(
        "claude-code",
        content,
        None,
        pre_install_per_config=pre_install_per_config,
        prior_entries=[],
    )
    managed = {e["name"] for e in keys.get("mcp_servers", []) if isinstance(e, dict)}
    assert "shared" not in managed, (
        "'shared' was pre-existing; recording it as managed would let a "
        "later narrow reconcile delete the user-authored entry"
    )
    assert "playbook-only" in managed, (
        "'playbook-only' was not pre-existing; the playbook owns it"
    )


def test_managed_keys_records_freshly_installed_mcp_servers(
    tmp_home: Path, tmp_target: Path, repo_root: Path
) -> None:
    """v0.8 Codex round-3 P1 fix: when install adds a NEW MCP entry that
    was not previously in the user's config, managed_keys.mcp_servers
    must record it. The previous fix snapshotted pre_existing AFTER
    install ran, so freshly-written entries appeared as pre-existing
    and managed_keys came out empty -- breaking narrow reconcile and
    runtime probe.

    End-to-end through scripts/install.py (the adversarial review
    explicitly asked for this coverage, not just _new_managed_keys_for
    unit coverage).
    """
    import json as _json
    import os
    import subprocess

    home = tmp_home
    (home / ".claude").mkdir()
    target = tmp_target

    # Start with a CLEAN ~/.claude.json so no MCPs are pre-existing.
    (home / ".claude.json").write_text("{}", encoding="utf-8")

    env = {**os.environ, "HOME": str(home), "MCP_RUNTIME_PROBE": "skip"}
    install_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "install.py"),
        "--non-interactive",
        "--target",
        str(target),
        "--profile",
        "qa",
        # v0.11 (ADR-0040): qa profile requires_overlays=["team"]; tmp_path
        # has no git remote so auto-detect returns []. Explicit scope.
        "--scope",
        "team",
    ]
    result = subprocess.run(
        install_cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, f"install failed: {result.stdout}\n{result.stderr}"

    lockfile = _json.loads((target / ".playbook-lock.json").read_text())
    managed = (
        lockfile.get("managed_keys", {}).get("claude-code", {}).get("mcp_servers", [])
    )
    assert managed, (
        "managed_keys.mcp_servers must include at least one entry; "
        "freshly-installed MCPs should be recorded as playbook-owned. "
        f"Got managed_keys: {lockfile.get('managed_keys')}"
    )

    # v0.9 (ADR-0039): each entry is a ManagedMcpEntry dict; extract the
    # name field for the native-config presence check.
    native = _json.loads((home / ".claude.json").read_text())
    native_servers = set((native.get("mcpServers") or {}).keys())
    managed_names = [e["name"] for e in managed if isinstance(e, dict) and "name" in e]
    for name in managed_names:
        assert name in native_servers, (
            f"managed_keys records {name!r} but it is not in native config"
        )


def test_managed_keys_survives_repeat_install_and_narrow(
    tmp_home: Path, tmp_target: Path, repo_root: Path
) -> None:
    """v0.8 Codex round-4 adversarial fix: repeat installs of the SAME
    profile must preserve managed_keys.mcp_servers. After the first
    install, the playbook MCPs are now pre-existing; without the
    prior_owned carry-forward, the second run computes
    `configured - pre_existing = {}` and overwrites the lockfile with
    empty ownership. Later profile narrow then leaves stale MCP
    registrations in the agent's native config.

    Repeats install, then narrows to a smaller profile, and asserts:
      * after repeat install, managed_keys.mcp_servers still has the
        full configured set (carry-forward works).
      * after narrow, dropped MCPs are removed from the native config
        (reconcile fires because they were correctly in prior managed).
    """
    import json as _json
    import os
    import subprocess

    home = tmp_home
    (home / ".claude").mkdir()
    target = tmp_target

    (home / ".claude.json").write_text("{}", encoding="utf-8")

    env = {**os.environ, "HOME": str(home), "MCP_RUNTIME_PROBE": "skip"}
    install_cmd_base = [
        sys.executable,
        str(repo_root / "scripts" / "install.py"),
        "--non-interactive",
        "--target",
        str(target),
        # v0.11 (ADR-0040): explicit scope so the narrow-to-qa step (which
        # uses a profile with requires_overlays=["team"]) succeeds; tmp_path
        # has no git remote so auto-detect would return [].
        "--scope",
        "team",
    ]

    # First install with full set (no --profile = everything).
    result = subprocess.run(
        install_cmd_base,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"first install failed: {result.stdout}\n{result.stderr}"
    )
    # v0.9 (ADR-0039): each entry is a ManagedMcpEntry; extract the name
    # field for comparison sets.
    lock1 = _json.loads((target / ".playbook-lock.json").read_text())
    managed1 = {
        e["name"]
        for e in (
            (lock1.get("managed_keys", {}).get("claude-code") or {}).get(
                "mcp_servers", []
            )
        )
        if isinstance(e, dict) and "name" in e
    }
    assert managed1, "first install must record managed MCP servers"

    # Repeat install (same args).
    result = subprocess.run(
        install_cmd_base,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"repeat install failed: {result.stdout}\n{result.stderr}"
    )
    lock2 = _json.loads((target / ".playbook-lock.json").read_text())
    managed2 = {
        e["name"]
        for e in (
            (lock2.get("managed_keys", {}).get("claude-code") or {}).get(
                "mcp_servers", []
            )
        )
        if isinstance(e, dict) and "name" in e
    }
    assert managed2 == managed1, (
        f"repeat install must preserve managed MCP ownership. "
        f"first={managed1}, second={managed2}"
    )

    # Narrow to qa profile.
    narrow_cmd = install_cmd_base + ["--profile", "qa"]
    result = subprocess.run(
        narrow_cmd,
        capture_output=True,
        text=True,
        env=env,
        cwd=str(repo_root),
        timeout=120,
    )
    assert result.returncode == 0, (
        f"narrow install failed: {result.stdout}\n{result.stderr}"
    )

    # After narrow, only the qa-profile MCPs should remain in
    # ~/.claude.json. The ones that fell out should have been removed
    # via reconcile_managed_json_mcp (which depends on managed_keys
    # being populated -- the very thing this regression protects).
    native_after = _json.loads((home / ".claude.json").read_text())
    native_servers_after = set((native_after.get("mcpServers") or {}).keys())
    dropped = managed1 - native_servers_after
    assert dropped, (
        "narrow profile must drop SOME managed MCP entries. If managed_keys "
        "carried forward correctly, the names that fell out of qa will be "
        "removed from the native config. "
        f"managed1={managed1}, native_after={native_servers_after}"
    )


def test_uninstall_blocks_on_v0_7_legacy_python_entries(tmp_path: Path) -> None:
    """v0.8 Codex round-5 fix: uninstall must refuse when v0.7-baseline
    direct-Python hook entries are still in settings.json. The original
    guard only checked the new wrapper basenames; if an upgrading user
    removed wrappers but kept the legacy entries, uninstall would
    unload the daemon while Claude Code kept invoking the dead Python
    hooks. Refuse + tell the user how to clean up.
    """
    import json as _json
    import os
    import subprocess

    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    # Seed legacy v0.7 settings.json with direct-Python entries.
    legacy_settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|MultiEdit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": (
                                "python3 /some/path/mcp/anchored-fs/hooks/"
                                "claude-code/pretool_edit.py"
                            ),
                        }
                    ],
                }
            ]
        }
    }
    (home / ".claude" / "settings.json").write_text(_json.dumps(legacy_settings))

    env = {"HOME": str(home), "PATH": os.environ["PATH"]}
    # v0.11 (ADR-0040): mcp/anchored-fs/ moved to base/mcp/anchored-fs/
    project_root = Path(__file__).resolve().parents[2] / "base" / "mcp" / "anchored-fs"

    # init succeeds (init does not touch settings.json post-ADR-0037).
    subprocess.run(
        [sys.executable, "install.py", "init"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(project_root),
        timeout=30,
    )

    # uninstall must REFUSE because legacy entries still present.
    result = subprocess.run(
        [sys.executable, "install.py", "uninstall"],
        env=env,
        capture_output=True,
        text=True,
        cwd=str(project_root),
        timeout=30,
    )
    assert result.returncode == 1, (
        f"uninstall must refuse with legacy v0.7 entries; got {result.returncode}"
    )
    assert "REFUSE" in (result.stdout + result.stderr)
    # Legacy entries survived the refusal.
    settings_after = _json.loads((home / ".claude" / "settings.json").read_text())
    assert settings_after == legacy_settings


def test_verify_flags_copied_dir_replaced_by_file(tmp_path: Path) -> None:
    """v0.8 Codex round-5 fix: a lockfile copied_dir entry whose on-
    disk path was replaced by a regular file is real drift. The
    existence check above passes (file exists), copied_dir_drift()
    returns 'missing' (it isn't a dir), and the verify pass must NOT
    silently accept that as OK.
    """
    from install_lockfile import hash_dir
    from install_verify import verify_adapter

    home = tmp_path / "home"
    home.mkdir()
    copied_dir = home / ".claude" / "skills" / "demo"
    copied_dir.mkdir(parents=True)
    (copied_dir / "SKILL.md").write_text("body\n", encoding="utf-8")
    pristine = hash_dir(copied_dir)
    entries = {
        ".claude/skills/demo": {
            "ownership": "owned",
            "kind": "copied_dir",
            "tree_sha256": pristine,
        }
    }

    # Replace the dir with a regular file. The path "still exists" but
    # is no longer a directory.
    import shutil

    shutil.rmtree(copied_dir)
    copied_dir.write_text("oops not a dir anymore", encoding="utf-8")

    def resolve(rel: str) -> Path:
        return home / rel

    passed, issues, counts = verify_adapter(
        "claude-code",
        entries,
        managed_keys={},
        target=None,
        resolve_locked_path=resolve,
    )
    assert not passed, "verify must FAIL when copied_dir is replaced by a file"
    assert counts["copied_dir_drift"] == 1
    assert any("copied_dir replaced" in i for i in issues)


def test_cursor_mcp_pre_existing_in_user_config_not_claimed_as_managed(
    tmp_home: Path, tmp_target: Path
) -> None:
    """v0.8 Codex round-6 HIGH: Cursor writes MCP entries to BOTH
    ~/.cursor/mcp.json (user) AND <target>/.cursor/mcp.json (project).
    If a name pre-exists in user config but not project, install adds
    it to project. The per-config diff would record it as managed in
    project; reconcile on narrow then walks BOTH configs and could
    delete the user's user-level entry.

    Fix: Cursor uses UNION pre-existing -- a name pre-existing in ANY
    config is never claimed as managed. This loses probe coverage for
    that name but eliminates the data-loss risk. This test pins the
    safer semantic.
    """
    import json as _json

    from adapters._loader import McpConfig
    from install import _new_managed_keys_for

    home = tmp_home
    target = tmp_target
    (home / ".cursor").mkdir()
    (target / ".cursor").mkdir()

    # User has 'shared' in user config; project config is empty.
    (home / ".cursor" / "mcp.json").write_text(
        _json.dumps({"mcpServers": {"shared": {"command": "user-binary"}}}),
        encoding="utf-8",
    )
    (target / ".cursor" / "mcp.json").write_text(
        _json.dumps({"mcpServers": {}}),
        encoding="utf-8",
    )

    shared_mcp = McpConfig(
        name="shared",
        path=Path("/dev/null"),
        config={"command": "playbook-binary"},
        source_dir=None,
    )
    content = _empty_content(mcp_configs=[shared_mcp])

    # v0.9 (ADR-0039): simulate install.py main loop by passing
    # pre_install_per_config snapshot. 'shared' pre-exists at user level
    # (~/.cursor/mcp.json) but NOT at project level. Per-config logic
    # means it's owned by the user at the user-level path AND can be a
    # fresh project-level entry. The test asserts the user-level entry
    # is not claimed.
    from mcp_native_config import mcp_config_paths_for, parse_native_mcp_servers

    pre_install_per_config: dict[tuple[str, str], set[str]] = {}
    for cfg_path, fmt in mcp_config_paths_for("cursor", target):
        pre_install_per_config[("cursor", str(cfg_path))] = parse_native_mcp_servers(
            cfg_path, fmt
        )

    keys = _new_managed_keys_for(
        "cursor",
        content,
        target,
        pre_install_per_config=pre_install_per_config,
        prior_entries=[],
    )
    # v0.9 per-config schema: the user-level 'shared' entry must not be
    # claimed at user-level. Project-level 'shared' MAY be claimed (it
    # was freshly inserted there). The reconcile-on-narrow path now uses
    # per-config managed names, so the project entry being managed does
    # NOT affect the user-level entry.
    user_cfg_str = str(Path.home() / ".cursor" / "mcp.json")
    user_level_claimed = [
        e
        for e in keys.get("mcp_servers", [])
        if isinstance(e, dict)
        and e.get("name") == "shared"
        and e.get("config_path") == user_cfg_str
    ]
    assert not user_level_claimed, (
        "'shared' pre-existed at user-level; cursor must NOT claim ownership "
        "of the user-level entry. project-level claim is OK in v0.9 (per-config "
        "ownership). Got user-level claims: " + str(user_level_claimed)
    )


def test_doctor_verify_target_scoped_default_does_not_spawn_target_commands(
    tmp_path: Path, repo_root: Path
) -> None:
    """v0.8 Codex round-7 + round-9 trust boundary: target-scoped MCP
    configs (entries under <target>/.cursor/mcp.json,
    <target>/.windsurf/mcp.json) must NOT be probed by default. Only
    user-level configs (which the user themselves controls) probe by
    default; target configs are opt-in via MCP_RUNTIME_PROBE=on.

    Test: seed a target with a malicious project-level cursor mcp.json
    declaring a command that would write a sentinel file. Run --verify
    without MCP_RUNTIME_PROBE. Sentinel must NOT be created (default
    skip for target-scoped configs).

    Sanity arm: re-run with MCP_RUNTIME_PROBE=on. Sentinel is created.
    """
    import json as _json
    import os
    import subprocess

    home = tmp_path / "home"
    (home / ".claude").mkdir(parents=True)
    (home / ".cursor").mkdir(parents=True)
    # User-level cursor mcp.json clean to keep the only probe target
    # the project-level one.
    (home / ".cursor" / "mcp.json").write_text(
        _json.dumps({"mcpServers": {}}), encoding="utf-8"
    )
    target = tmp_path / "project"
    target.mkdir()
    (target / ".cursor").mkdir()
    sentinel = tmp_path / "sentinel-probe-fired"

    # Target-scoped: project-level cursor mcp.json with the malicious entry.
    (target / ".cursor" / "mcp.json").write_text(
        _json.dumps(
            {
                "mcpServers": {
                    "evil": {
                        "command": "bash",
                        "args": [
                            "-c",
                            f"touch {sentinel}; sleep 30",
                        ],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    # v0.9 (ADR-0039): list[ManagedMcpEntry] with config_path recording
    # the exact native config file the playbook owns.
    project_cfg = target / ".cursor" / "mcp.json"
    lockfile = target / ".playbook-lock.json"
    lockfile.write_text(
        _json.dumps(
            {
                "lockfile_version": 3,
                "version": "0.9.0",
                "generated_at": "2026-05-25T00:00:00+00:00",
                "target": str(target),
                "adapters": {"cursor": {}},
                "managed_keys": {
                    "cursor": {
                        "mcp_servers": [
                            {
                                "id": "uuid-evil",
                                "name": "evil",
                                "config_path": str(project_cfg),
                                "scope": "project",
                                "installed_at": "2026-05-25T00:00:00+00:00",
                            }
                        ]
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    verify_cmd = [
        sys.executable,
        str(repo_root / "scripts" / "install.py"),
        "--verify",
        "--target",
        str(target),
    ]

    # Default: target-scoped configs are NOT probed.
    env_default = {**os.environ, "HOME": str(home)}
    result = subprocess.run(
        verify_cmd,
        capture_output=True,
        text=True,
        env=env_default,
        cwd=str(repo_root),
        timeout=20,
    )
    assert not sentinel.exists(), (
        "Target-scoped --verify must NOT spawn target-controlled "
        "commands by default. Sentinel was created: trust boundary "
        "violated."
    )
    assert "target-scoped" in result.stdout, (
        f"Default skip message must mention target-scoped; got:\n{result.stdout}"
    )

    # Opt-in: target-scoped probe runs.
    env_opt_in = {**os.environ, "HOME": str(home), "MCP_RUNTIME_PROBE": "on"}
    subprocess.run(
        verify_cmd,
        capture_output=True,
        text=True,
        env=env_opt_in,
        cwd=str(repo_root),
        timeout=20,
    )
    assert sentinel.exists(), (
        "MCP_RUNTIME_PROBE=on must opt in for target-scoped configs"
    )


def test_cursor_project_level_writes_target_dependent_mcp_for_each_target(
    tmp_home: Path, tmp_path: Path
) -> None:
    """v0.8 Codex round-8 HIGH: target-dependent MCPs (anchored-fs
    expands {{PLAYBOOK_TARGET}} into --allowed-dir <target>) must
    appear in EACH target's project mcp.json. Round-7's project-level
    skip would have broken this by suppressing project writes for
    names pre-existing at user level. Round-8 reverts that skip.

    Two-target scenario: install with target_a, then with target_b.
    Each target's .cursor/mcp.json should have its OWN 'shared'
    entry pointing at the right target.

    Known trade-off (v0.9 work): the project entry can orphan after
    profile narrow because managed_keys uses union pre-existing to
    avoid user-data loss. Per-(adapter, config_path) schema fixes
    both ends.
    """
    import json as _json

    from adapters._loader import McpConfig
    from adapters.cursor import CursorAdapter

    home = tmp_home
    target_a = tmp_path / "project-a"
    target_b = tmp_path / "project-b"
    target_a.mkdir()
    target_b.mkdir()
    (home / ".cursor").mkdir()

    shared_mcp = McpConfig(
        name="shared",
        path=Path("/dev/null"),
        config={
            "command": "playbook-binary",
            "args": ["--allowed-dir", "{{PLAYBOOK_TARGET}}"],
        },
        source_dir=None,
    )
    content = _empty_content(mcp_configs=[shared_mcp])

    list(CursorAdapter().install(content, target=target_a))
    list(CursorAdapter().install(content, target=target_b))

    proj_a = _json.loads((target_a / ".cursor" / "mcp.json").read_text())
    proj_b = _json.loads((target_b / ".cursor" / "mcp.json").read_text())
    assert "shared" in (proj_a.get("mcpServers") or {})
    assert "shared" in (proj_b.get("mcpServers") or {})
    args_a = " ".join(proj_a["mcpServers"]["shared"]["args"])
    args_b = " ".join(proj_b["mcpServers"]["shared"]["args"])
    assert str(target_a) in args_a, (
        f"target_a's project mcp.json must contain target_a in args; got {args_a}"
    )
    assert str(target_b) in args_b, (
        f"target_b's project mcp.json must contain target_b in args; got {args_b}"
    )


def test_hook_metadata_check_fails_on_unknown_adapter_slug(tmp_path: Path) -> None:
    """v0.8 Codex round-9 medium: PLAYBOOK-HOOK-ADAPTERS with all-typo
    slugs would otherwise silently disable the hook for every adapter
    while passing make check. The hook_metadata gate must FAIL when
    the declared set parses to an empty valid slug set.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from check_hook_metadata import main as hook_metadata_main

    fake_root = tmp_path / "fake-root"
    # v0.11 (ADR-0040): hook_metadata check walks base/hooks/ + overlays/team/hooks/.
    (fake_root / "base" / "hooks").mkdir(parents=True)
    (fake_root / "base" / "hooks" / "typo-hook.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# PLAYBOOK-HOOK-EVENT: PreToolUse\n"
        "# PLAYBOOK-HOOK-MATCHER: Edit\n"
        "# PLAYBOOK-HOOK-ADAPTERS: claudecode,kodex\n"
        "exit 0\n",
        encoding="utf-8",
    )

    rc = hook_metadata_main(fake_root)
    assert rc == 1, "hook_metadata must fail when ADAPTERS contains only typos"


def test_hook_metadata_check_passes_when_adapters_header_absent(tmp_path: Path) -> None:
    """When PLAYBOOK-HOOK-ADAPTERS is absent the hook applies to every
    hook-capable adapter; the gate must NOT fail.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from check_hook_metadata import main as hook_metadata_main

    fake_root = tmp_path / "fake-root"
    (fake_root / "hooks").mkdir(parents=True)
    (fake_root / "hooks" / "regular-hook.sh").write_text(
        "#!/usr/bin/env bash\n"
        "# PLAYBOOK-HOOK-EVENT: PreToolUse\n"
        "# PLAYBOOK-HOOK-MATCHER: Edit\n"
        "exit 0\n",
        encoding="utf-8",
    )

    rc = hook_metadata_main(fake_root)
    assert rc == 0
