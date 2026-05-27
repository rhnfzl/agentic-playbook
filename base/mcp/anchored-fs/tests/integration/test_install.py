import json
import os
import subprocess
import sys
from pathlib import Path


def run_install(tmp_home: Path, subcommand: str) -> subprocess.CompletedProcess:
    """Invoke the documented `python install.py <subcommand>` entry point.

    v0.8 (C4 follow-up): exercises the root compat shim that forwards to
    bundle/install.py so the documented commands in mcp/anchored-fs/
    README.md keep working. The shim is load-bearing per Codex review
    until every external invocation has migrated to bundle/install.py.
    """
    env = {"HOME": str(tmp_home), "PATH": os.environ["PATH"]}
    project_root = Path(__file__).resolve().parents[2]
    return subprocess.run(
        [sys.executable, "install.py", subcommand],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(project_root),
    )


def test_init_creates_state_dirs_and_skips_settings(tmp_path: Path):
    """v0.8 (ADR-0037): init no longer mutates ~/.claude/settings.json.
    Hook registration moved to the playbook adapter pipeline via the
    hooks/anchored-fs-{pretool-edit,posttool-read}.sh wrappers. init still
    creates state/run dirs, default config, and the launchd plist.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    sentinel = '{"sentinel": true}'
    (home / ".claude" / "settings.json").write_text(sentinel)

    result = run_install(home, "init")
    assert result.returncode == 0, result.stderr

    settings = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings == {"sentinel": True}, (
        "bundle/install.py init mutated ~/.claude/settings.json; v0.8 owns "
        "that via the playbook hook adapter, not the bundle"
    )
    assert (home / ".config" / "agent-shared" / "state").is_dir()


def test_check_returns_0_when_playbook_wrapper_present(tmp_path: Path):
    """v0.8 (ADR-0037): check looks for the playbook-installed wrapper at
    ~/.claude/hooks/anchored-fs-pretool-edit.sh as the proof-of-install
    signal (the playbook owns the registration; check just verifies the
    wrapper landed).
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    run_install(home, "init")

    # Simulate the playbook adapter having copied the wrapper into place.
    hooks_dir = home / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "anchored-fs-pretool-edit.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n"
    )

    result = run_install(home, "check")
    assert result.returncode == 0, result.stderr


def test_check_fails_without_playbook_wrapper(tmp_path: Path):
    """v0.8 (ADR-0037): check fails loudly when the playbook hasn't installed
    the wrapper into ~/.claude/hooks/. This is the single signal that says
    `make install` has not been run with the claude-code adapter enabled.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    run_install(home, "init")

    result = run_install(home, "check")
    assert result.returncode == 1
    assert "playbook wrapper" in result.stderr


def test_uninstall_leaves_settings_alone(tmp_path: Path):
    """v0.8 (ADR-0037 + Codex adversarial fix): uninstall REFUSES to
    complete when the playbook-installed wrapper hooks are still
    registered. The bundle cannot safely remove them (playbook owns
    them); leaving them registered after a "successful" uninstall
    means Claude Code keeps invoking the now-dead Python hooks. The
    safer contract: refuse + tell the user how to clean up first.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    # Seed sentinel settings simulating an active playbook install.
    sentinel_settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Edit|MultiEdit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": str(
                                home
                                / ".claude"
                                / "hooks"
                                / "anchored-fs-pretool-edit.sh"
                            ),
                        }
                    ],
                }
            ]
        }
    }
    (home / ".claude" / "settings.json").write_text(json.dumps(sentinel_settings))

    run_install(home, "init")
    result = run_install(home, "uninstall")
    # New contract: uninstall refuses + returns non-zero.
    assert result.returncode == 1, result.stderr
    assert "REFUSE" in result.stderr or "REFUSE" in result.stdout
    assert "anchored-fs-pretool-edit.sh" in (result.stderr + result.stdout)

    # Settings must SURVIVE the refusal byte-for-byte.
    settings_after = json.loads((home / ".claude" / "settings.json").read_text())
    assert settings_after == sentinel_settings


def test_uninstall_completes_when_wrapper_already_removed(tmp_path: Path):
    """v0.8 (Codex adversarial fix): once the wrapper is removed by the
    playbook (via `make install --profile <no-anchored-fs>` or manual
    cleanup), uninstall completes successfully and removes the daemon
    plist.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    # No wrapper registered -> uninstall can proceed.
    (home / ".claude" / "settings.json").write_text("{}")

    run_install(home, "init")
    result = run_install(home, "uninstall")
    assert result.returncode == 0, result.stderr


def test_init_writes_launchd_plist(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")

    result = run_install(home, "init")
    assert result.returncode == 0, result.stderr

    plist = home / "Library" / "LaunchAgents" / "com.anchored-fs.daemon.plist"
    assert plist.exists()
    content = plist.read_text()
    assert "com.anchored-fs.daemon" in content
    assert "KeepAlive" in content


def test_init_does_not_register_mcp_directly(tmp_path: Path):
    """v0.6 (ADR-0026): MCP registration moved to the coding-agents-playbook
    installer. bundle/install.py must NOT touch ~/.claude.json or
    ~/.codex/config.toml itself; the playbook scans mcp/anchored-fs/server.json
    and writes the MCP entry through each adapter on `make install`.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    (home / ".codex").mkdir()
    # Pre-populate with a sentinel so we can confirm bundle/install.py
    # leaves it untouched.
    sentinel_claude = {"mcpServers": {"other-server": {"command": "other"}}}
    (home / ".claude.json").write_text(json.dumps(sentinel_claude))
    sentinel_codex = '[mcp_servers.other-server]\ncommand = "other"\n'
    (home / ".codex" / "config.toml").write_text(sentinel_codex)

    result = run_install(home, "init")
    assert result.returncode == 0, result.stderr

    # Both files must be byte-equivalent to the sentinels we wrote.
    claude_after = json.loads((home / ".claude.json").read_text())
    assert claude_after == sentinel_claude, (
        "bundle/install.py mutated ~/.claude.json; v0.6 owns that via the "
        "playbook installer, not the anchored-fs bundle"
    )
    codex_after = (home / ".codex" / "config.toml").read_text()
    assert codex_after == sentinel_codex, (
        "bundle/install.py mutated ~/.codex/config.toml; v0.6 owns that "
        "via the playbook installer, not the anchored-fs bundle"
    )


def test_init_writes_default_anchored_fs_toml(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")

    result = run_install(home, "init")
    assert result.returncode == 0, result.stderr

    config_toml = home / ".config" / "agent-shared" / "anchored-fs.toml"
    assert config_toml.exists(), "anchored-fs.toml not written"
    content = config_toml.read_text()
    assert "[validators.edit_anchor]" in content
    assert "[validators.stale_read_guard]" in content
    assert "[graduation]" in content


def test_init_does_not_overwrite_existing_anchored_fs_toml(tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    config_dir = home / ".config" / "agent-shared"
    config_dir.mkdir(parents=True)
    sentinel = "# user custom config\n"
    (config_dir / "anchored-fs.toml").write_text(sentinel)

    result = run_install(home, "init")
    assert result.returncode == 0, result.stderr

    assert (config_dir / "anchored-fs.toml").read_text() == sentinel, (
        "user config was overwritten"
    )


def test_uninstall_leaves_mcp_registrations_alone(tmp_path: Path):
    """v0.6 (ADR-0026): uninstall removes hooks + plist but not MCP entries.
    MCP registration is owned by the coding-agents-playbook installer; the
    user removes it by narrowing their playbook profile, not by running
    bundle/install.py uninstall.
    """
    home = tmp_path / "home"
    home.mkdir()
    (home / ".claude").mkdir()
    (home / ".claude" / "settings.json").write_text("{}")
    (home / ".codex").mkdir()
    # Seed sentinel MCP entries simulating a prior playbook install.
    sentinel_claude = {"mcpServers": {"anchored-fs": {"command": "x"}}}
    (home / ".claude.json").write_text(json.dumps(sentinel_claude))
    sentinel_codex = '[mcp_servers.anchored-fs]\ncommand = "x"\n'
    (home / ".codex" / "config.toml").write_text(sentinel_codex)

    run_install(home, "init")
    result = run_install(home, "uninstall")
    assert result.returncode == 0, result.stderr

    # MCP entries must SURVIVE uninstall (playbook owns them).
    claude_after = json.loads((home / ".claude.json").read_text())
    assert claude_after == sentinel_claude, (
        "bundle/install.py uninstall removed an MCP entry it doesn't own"
    )
    codex_after = (home / ".codex" / "config.toml").read_text()
    assert codex_after == sentinel_codex, (
        "bundle/install.py uninstall mutated ~/.codex/config.toml"
    )
