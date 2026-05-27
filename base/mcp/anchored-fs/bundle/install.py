"""Install / repair / check / uninstall / status for anchored-fs framework.

Manifest-driven: every entry in ~/.claude/settings.json is described in
manifest.json and identified by the absolute path of this anchored-fs
install.

v0.6 (ADR-0026 follow-through, ADR-0032): MCP registration in
~/.claude.json + ~/.codex/config.toml is now owned by the coding-agents-
playbook installer (scripts/install.py + each adapter). bundle/install.py
keeps Claude-Code hook registration because the anchored-fs hooks are
Python files coupled to the daemon socket and don't fit the playbook's
shell-script hook model (yet). The ~80 lines of MCP-registration code
that previously lived here are gone; users run `make install` from the
playbook root to register the MCP server across their installed agents.
"""

from __future__ import annotations
import argparse
import json
import os
import shutil
import sys
from pathlib import Path

# Per ADR-0026 (v0.5 extension): install.py lives under bundle/, so the
# anchored-fs framework root is one level up. Everything else in this file
# (template paths, manifest writes, plist generation) is anchored from
# ANCHORED_FS_ROOT, so the move is contained to this one constant.
ANCHORED_FS_ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get("HOME", str(Path.home())))
STATE_DIR = HOME / ".config" / "agent-shared" / "state"
RUN_DIR = HOME / ".config" / "agent-shared" / "run"

sys.path.insert(0, str(ANCHORED_FS_ROOT))
from core import manifest as manifest_module  # noqa: E402


# v0.8 (ADR-0037): hook ownership moved to the playbook. The settings.json
# read/write helpers (_load_settings, _write_json, _backup, _add_hook,
# _remove_owned_hooks) lived here through v0.7 to mutate
# ~/.claude/settings.json; the playbook adapter pipeline now owns those
# writes via hooks/anchored-fs-{pretool-edit,posttool-read}.sh. The
# helpers were removed to prevent silent re-introduction of the parallel
# hook system.


MCP_SERVER_NAME = "anchored-fs"


def _write_default_anchored_fs_toml(config_dir: Path) -> None:
    """Write default anchored-fs.toml only if it does not already exist (preserve user edits)."""
    dest = config_dir / "anchored-fs.toml"
    if dest.exists():
        return
    template = ANCHORED_FS_ROOT / "templates" / "anchored-fs.toml"
    shutil.copy2(template, dest)


def init() -> int:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RUN_DIR.mkdir(parents=True, exist_ok=True)

    template = manifest_module.load_template()
    rendered = manifest_module.render(
        template,
        anchored_fs_root=str(ANCHORED_FS_ROOT),
        allowed_root=str(HOME),
    )

    # v0.8 (ADR-0037): Claude Code hook registration also moved to the
    # coding-agents-playbook installer. The wrappers at
    # `<playbook>/hooks/anchored-fs-pretool-edit.sh` +
    # `<playbook>/hooks/anchored-fs-posttool-read.sh` declare
    # PLAYBOOK-HOOK-ADAPTERS: claude-code and are installed by the
    # claude-code adapter into ~/.claude/hooks/ alongside every other
    # playbook hook. bundle/install.py no longer writes to
    # ~/.claude/settings.json.
    #
    # The manifest is still written (for `bundle/install.py status` and any
    # external auditing) but its "hooks" block is now documentation-only;
    # the playbook adapter pipeline is the source of truth.
    (ANCHORED_FS_ROOT / "manifest.json").write_text(json.dumps(rendered, indent=2))

    print(
        "anchored-fs hooks + MCP entry are registered by the coding-agents-playbook installer; "
        "run `make install` from the playbook root for any adapter you want it on."
    )

    # Write default config TOML if not already present
    config_dir = HOME / ".config" / "agent-shared"
    config_dir.mkdir(parents=True, exist_ok=True)
    _write_default_anchored_fs_toml(config_dir)

    # launchd plist install (Task 13)
    import subprocess

    plist_template = (
        ANCHORED_FS_ROOT / "daemon" / "com.anchored-fs.daemon.plist.template"
    ).read_text()
    log_dir = HOME / ".config" / "agent-shared" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_content = (
        plist_template.replace("{python_executable}", sys.executable)
        .replace("{socket_path}", str(RUN_DIR / "anchored-fs.sock"))
        .replace("{anchored_fs_root}", str(ANCHORED_FS_ROOT))
        .replace("{log_dir}", str(log_dir))
    )
    plist_path = HOME / "Library" / "LaunchAgents" / "com.anchored-fs.daemon.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_path.write_text(plist_content)
    try:
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        subprocess.run(
            ["launchctl", "load", str(plist_path)], check=True, capture_output=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        print(
            "WARNING: launchctl unavailable; daemon must be started manually",
            file=sys.stderr,
        )

    print(f"anchored-fs installed; manifest at {ANCHORED_FS_ROOT / 'manifest.json'}")
    return 0


def _playbook_hook_present() -> bool:
    """Return True iff the playbook installed an anchored-fs hook wrapper.

    The wrappers ship at hooks/anchored-fs-pretool-edit.sh and
    hooks/anchored-fs-posttool-read.sh in the playbook root; the claude-code
    adapter copies them to ~/.claude/hooks/ and registers them in
    ~/.claude/settings.json. The bundle's health check just confirms one of
    the wrappers landed (full registration verification belongs to the
    playbook's `make doctor-verify` per ADR-0036).
    """
    candidate = HOME / ".claude" / "hooks" / "anchored-fs-pretool-edit.sh"
    return candidate.is_file()


def _is_installed_ok() -> bool:
    """Return True if the playbook hook wrapper and bundle manifest are present."""
    return _playbook_hook_present() and (ANCHORED_FS_ROOT / "manifest.json").exists()


def check() -> int:
    if not _is_installed_ok():
        if not _playbook_hook_present():
            print(
                "ERROR: playbook wrapper hooks/anchored-fs-pretool-edit.sh not "
                "found under ~/.claude/hooks/; run `make install` from the "
                "playbook root with the claude-code adapter enabled",
                file=sys.stderr,
            )
        if not (ANCHORED_FS_ROOT / "manifest.json").exists():
            print("ERROR: manifest.json missing", file=sys.stderr)
        return 1
    print("ok")
    return 0


def status() -> int:
    settings_ok = _is_installed_ok()
    state_dir = HOME / ".config" / "agent-shared" / "state"
    adoption_path = state_dir / "adoption.jsonl"
    print("anchored-fs status")
    print(f"  install: {'ok' if settings_ok else 'BROKEN'}")
    print(f"  manifest: {(ANCHORED_FS_ROOT / 'manifest.json').exists()}")
    print()
    print("Validator modes (default from anchored-fs.toml):")
    print("  edit_anchor: auto_rescue (default; graduates per telemetry)")
    print("  stale_read_guard: warn (default; graduates per telemetry)")
    print("  path_resolver: silent_rewrite=false")
    print()
    if adoption_path.exists():
        lines = adoption_path.read_text().strip().splitlines()
        recent = [json.loads(line) for line in lines[-100:]]
        total_oversize = sum(1 for r in recent if r.get("old_lines", 0) >= 25)
        voluntary = sum(
            1 for r in recent if r.get("used_upto") and r.get("old_lines", 0) >= 25
        )
        pct = (voluntary / total_oversize * 100) if total_oversize else 0.0
        print(
            f"Adoption (last 100 records, edits >= 25 lines): {voluntary}/{total_oversize} = {pct:.1f}% voluntary [upto]"
        )
    else:
        print("Adoption: no records yet")
    return 0


def uninstall() -> int:
    """Uninstall the bundle's local-only artifacts AND, if the playbook
    is reachable, refuse to leave wrapper hook registrations active.

    v0.8 Codex adversarial fix: the previous uninstall unloaded the
    daemon plist but explicitly preserved the playbook-installed
    wrapper hooks. Users running `python install.py uninstall`
    reasonably believe they have removed anchored-fs entirely; leaving
    the wrappers wired means Claude Code still tries to execute the
    bundle's Python hooks after every Edit, which then fail because
    the daemon is gone. We now refuse to complete uninstall when the
    wrappers are still registered and tell the user how to remove
    them.
    """
    import subprocess

    plist_path = HOME / "Library" / "LaunchAgents" / "com.anchored-fs.daemon.plist"
    settings_path = HOME / ".claude" / "settings.json"
    # v0.8 Codex round-4 + round-5 fix: check BOTH new wrapper basenames
    # (pretool + posttool) AND the legacy v0.7 direct-Python paths
    # (mcp/anchored-fs/hooks/claude-code/*.py). An upgraded user who
    # removed the wrappers but still has the legacy v0.7 entries in
    # settings.json would otherwise see uninstall unload the daemon
    # while Claude Code keeps invoking the dead Python hooks.
    wrapper_basenames = (
        "anchored-fs-pretool-edit.sh",
        "anchored-fs-posttool-read.sh",
    )
    legacy_path_fragments = (
        "anchored-fs/hooks/claude-code/pretool_edit.py",
        "anchored-fs/hooks/claude-code/posttool_read.py",
    )
    blocker_fragments = wrapper_basenames + legacy_path_fragments

    settings_has_blocker = False
    if settings_path.is_file():
        try:
            import json as _json

            settings = _json.loads(settings_path.read_text(encoding="utf-8"))
            for entries in (settings.get("hooks") or {}).values():
                for entry in entries:
                    for h in entry.get("hooks", []):
                        cmd = h.get("command", "")
                        if any(name in cmd for name in blocker_fragments):
                            settings_has_blocker = True
                            break
        except (OSError, ValueError):
            settings_has_blocker = False
    wrapper_files_present = [
        HOME / ".claude" / "hooks" / name
        for name in wrapper_basenames
        if (HOME / ".claude" / "hooks" / name).is_file()
    ]
    if settings_has_blocker or wrapper_files_present:
        print(
            "REFUSE: anchored-fs hooks (wrapper or legacy v0.7 direct-"
            "Python) are still registered in settings.json or on disk. "
            "Remove them first so uninstall does not leave a half-wired "
            "install:",
            file=sys.stderr,
        )
        print(
            "  1. `make install --profile <no-anchored-fs>` from the playbook root, "
            "OR",
            file=sys.stderr,
        )
        print(
            f"  2. delete {settings_path} entries matching any of "
            f"{wrapper_basenames!r} + `rm` the wrapper files under "
            f"~/.claude/hooks/ manually.",
            file=sys.stderr,
        )
        if wrapper_files_present:
            print("  Wrapper files still on disk:", file=sys.stderr)
            for w in wrapper_files_present:
                print(f"    - {w}", file=sys.stderr)
        print(
            "Re-run `python install.py uninstall` after the wrappers are gone.",
            file=sys.stderr,
        )
        return 1

    if plist_path.exists():
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        plist_path.unlink()

    # MCP registration is still playbook-owned; the user removes it by
    # narrowing their playbook profile and re-running `make install`.
    print(
        "anchored-fs uninstalled (state files + MCP registration preserved; "
        "use `make install` with a narrower profile to drop the MCP entry)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "subcommand", choices=["init", "check", "uninstall", "repair", "status"]
    )
    args = parser.parse_args()
    return {
        "init": init,
        "check": check,
        "uninstall": uninstall,
        "repair": init,
        "status": status,
    }[args.subcommand]()


if __name__ == "__main__":
    sys.exit(main())
