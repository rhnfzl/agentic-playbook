"""ADR-0036 layer-3 verification: lockfile vs native config vs on-disk.

Extracted from `scripts/install.py` per the post-Cursor-review
decomposition. install.py owns argparse + orchestration; this module owns
the verify command and its per-adapter check helper. All adapter-specific
shape knowledge lives in `scripts/hook_native_config.py`; this module is
the policy layer that consumes that shape contract.

`cmd_verify(target)` reads the lockfile, walks every detected adapter,
compares the recorded paths/registrations against the actual native
config files + on-disk script paths + skill ownership markers, and
prints a per-adapter pass/fail map. Exits 0 on full pass, non-zero on
any drift.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from hook_native_config import (
    command_registers,
    config_paths_for,
    lockfile_to_native_event,
    parse_native_hook_commands,
)


# v0.8 Cursor review C3-cleanup: the per-adapter MCP config path + parse
# logic moved to scripts/mcp_native_config.py so install_verify and
# mcp_runtime_probe share one implementation. The thin module-level
# aliases below preserve internal-import compatibility.

from mcp_native_config import (  # noqa: E402
    mcp_config_paths_for as _mcp_config_paths_for,
    parse_native_mcp_servers as _parse_native_mcp_servers,
)


def verify_adapter(
    adapter_name: str,
    entries: dict,
    managed_keys: dict,
    target: Path | None,
    *,
    resolve_locked_path: Callable[[str], Path],
    hash_dir: Callable[[Path], str] | None = None,
) -> tuple[bool, list[str], dict]:
    """Return (passed, issues, counts) for one adapter's layer-3 verification.

    Checks performed:
      1. Every file recorded in the lockfile exists on disk.
      2. Every managed hook in the lockfile is present in every native
         config the adapter writes (user-level AND project-level for
         Cursor / Windsurf when target is set).
      3. Every installed skill directory carries the `.playbook-owned`
         marker (which is the playbook's layer-2 ownership signal;
         layer-3 runtime discovery for skills additionally needs a new
         chat session, but that is out of scope for an offline check).
      4. v0.8 (ADR-0036 + B4): every lockfile entry recorded as a
         copied directory (kind="copied_dir" with a tree_sha256) is
         re-hashed and compared. Drift here means a Windows fallback
         copy that diverged from canonical source since the last
         install. Requires `hash_dir` to be injected (None disables
         the drift check, matching v0.7 behavior).

    `resolve_locked_path` and `hash_dir` are dependency-injected from
    install.py so this module stays import-cycle free.
    """
    issues: list[str] = []
    counts: dict = {
        "lockfile_files": len(entries),
        "missing_files": 0,
        "copied_dir_drift": 0,
        "lockfile_hooks": 0,
        "native_hooks_per_config": {},  # rel_path -> count
        "lockfile_mcps": 0,
        "native_mcps_per_config": {},  # rel_path -> count
        "skill_dirs": 0,
        "skill_missing_marker": 0,
    }

    for rel, locked in entries.items():
        full = resolve_locked_path(rel)
        if not (full.exists() or full.is_symlink()):
            counts["missing_files"] += 1
            issues.append(
                f"lockfile entry missing on disk: {rel} (inspect: ls -la {full.parent})"
            )
            continue
        # v0.8 (B4 + Cursor C3-cleanup + Codex round-5 fix): copied_dir
        # drift detection via shared install_lockfile.copied_dir_drift().
        # Round-5 case: when a copied_dir path is replaced by a regular
        # file, the entry's path still exists so the missing-files
        # branch above doesn't fire, but the dir is no longer there.
        # We treat "missing" from copied_dir_drift (which checks
        # is_dir()) as a real drift now, not a silent no-op.
        if isinstance(locked, dict) and locked.get("kind") == "copied_dir":
            from install_lockfile import copied_dir_drift as _drift

            drift = _drift(full, locked)
            if drift == "drift":
                expected = locked.get("tree_sha256", "")
                counts["copied_dir_drift"] += 1
                issues.append(
                    f"copied_dir drift at {rel}: lockfile tree_sha256={expected[:12]}... "
                    f"differs from on-disk (re-run `make install` to refresh)"
                )
            elif drift == "missing":
                # The path exists but it's no longer a directory (turned
                # into a file or symlink). That's drift the round-5
                # review specifically flagged: doctor-verify would say
                # OK while the layer-2 state is broken.
                counts["copied_dir_drift"] += 1
                issues.append(
                    f"copied_dir replaced at {rel}: path exists but is no "
                    f"longer a directory (re-run `make install` to refresh)"
                )

    locked_hooks: dict = managed_keys.get("hooks", {}) or {}
    windsurf_hooks: dict = managed_keys.get("windsurf_hooks", {}) or {}
    cfg_paths = config_paths_for(adapter_name, target)
    if cfg_paths and (locked_hooks or windsurf_hooks):
        if windsurf_hooks:
            counts["lockfile_hooks"] = len(windsurf_hooks)
        else:
            counts["lockfile_hooks"] = sum(len(v) for v in locked_hooks.values())

        for config_path in cfg_paths:
            native = parse_native_hook_commands(config_path, adapter_name)
            cfg_key = str(config_path)
            counts["native_hooks_per_config"][cfg_key] = sum(
                len(v) for v in native.values()
            )

            if windsurf_hooks:
                for hook_name in sorted(windsurf_hooks.keys()):
                    expected_basename = f"{hook_name}.sh"
                    # Windsurf reconcile is name-based across all Cascade
                    # events (Cascade derives event from matcher tokens),
                    # so a basename scan across every event is the right
                    # semantic here even though it would be wrong for
                    # Claude-shaped adapters.
                    found_any = False
                    for cmds in native.values():
                        for cmd in cmds:
                            if command_registers(cmd, expected_basename):
                                found_any = True
                                break
                        if found_any:
                            break
                    if not found_any:
                        issues.append(
                            f"lockfile records Cascade hook {hook_name!r} but "
                            f"{config_path} has no entry pointing at it "
                            f"(inspect: cat {config_path})"
                        )
            else:
                for event, paths in locked_hooks.items():
                    native_event = lockfile_to_native_event(adapter_name, event)
                    native_paths = native.get(native_event, [])
                    for path in paths:
                        if any(
                            command_registers(native_cmd, path)
                            for native_cmd in native_paths
                        ):
                            continue
                        # Layer-3 contract is event-specific: the hook
                        # must register under the SAME event the lockfile
                        # records, not just anywhere in the config. A
                        # hook that exists under the wrong event is the
                        # exact "fires at the wrong time" failure mode
                        # the verifier is meant to catch.
                        expected_name = Path(path).name
                        wrong_event = _find_other_event_registering(
                            native, expected_name, native_event
                        )
                        if wrong_event:
                            issues.append(
                                f"lockfile records {event}={path!r} but "
                                f"{config_path} registers it under "
                                f"{wrong_event!r} instead of {native_event!r} "
                                f"(layer-3 event drift; fires at the wrong time. "
                                f"inspect: cat {config_path})"
                            )
                        else:
                            issues.append(
                                f"lockfile records {event}={path!r} but "
                                f"{config_path} does not contain it under "
                                f"{native_event!r} or any other event "
                                f"(inspect: cat {config_path})"
                            )

    # v0.9 (ADR-0039): managed_keys.mcp_servers is list[ManagedMcpEntry];
    # each entry's config_path tells us where the playbook wrote it. Per-
    # config expected sets replace v0.8's "every name must be in every
    # config the adapter writes to" check.
    #
    # v0.9 regular review P2-2 fix: normalize both sides before string
    # comparison. The lockfile records config_path as the absolute path
    # at install time; _mcp_config_paths_for can yield a path built from
    # an unresolved relative `--target ../project`. A raw str() compare
    # leaves `expected` empty for project MCP files and lets missing
    # entries pass verification. Resolving both via Path.resolve()
    # canonicalizes /Users/<me>/project vs ../project.
    raw_entries = managed_keys.get("mcp_servers", []) or []
    typed_entries = [e for e in raw_entries if isinstance(e, dict)]

    def _canonical(path_like: object) -> str:
        try:
            return str(Path(str(path_like)).resolve())
        except (OSError, TypeError):
            return str(path_like)

    if typed_entries:
        counts["lockfile_mcps"] = len(typed_entries)
        for config_path, fmt in _mcp_config_paths_for(adapter_name, target):
            canonical_cfg = _canonical(config_path)
            expected = {
                e["name"]
                for e in typed_entries
                if _canonical(e.get("config_path", "")) == canonical_cfg
                and isinstance(e.get("name"), str)
            }
            native_servers = _parse_native_mcp_servers(config_path, fmt)
            counts["native_mcps_per_config"][str(config_path)] = len(native_servers)
            for server_name in sorted(expected - native_servers):
                issues.append(
                    f"lockfile records MCP server {server_name!r} at "
                    f"{config_path} but the file does not contain it "
                    f"(inspect: cat {config_path})"
                )

    for rel in entries:
        if Path(rel).name != "SKILL.md":
            continue
        skill_dir = resolve_locked_path(rel).parent
        counts["skill_dirs"] += 1
        if not (skill_dir / ".playbook-owned").is_file():
            counts["skill_missing_marker"] += 1
            issues.append(
                f"skill {skill_dir.name!r} at {skill_dir} has no "
                ".playbook-owned marker; next install will skip it as "
                f"user-owned (inspect: ls -la {skill_dir})"
            )

    return (not issues), issues, counts


def _find_other_event_registering(
    native: dict[str, list[str]],
    expected_basename: str,
    expected_event: str,
) -> str | None:
    """When a hook is missing under its expected event, look for it under
    OTHER events. Returns the wrong-event key when found, None otherwise.

    Catches layer-3 drift where the hook exists in the native config but
    fires at the wrong moment (the regression Codex review flagged: the
    previous cross-event fallback let wrong-event registrations pass
    silently).
    """
    for event, cmds in native.items():
        if event == expected_event:
            continue
        for cmd in cmds:
            if command_registers(cmd, expected_basename):
                return event
    return None


def cmd_verify(
    target: Path | None,
    *,
    load_lockfile: Callable[[Path | None, Path], dict | None],
    detected_adapters: Callable[[], list],
    resolve_locked_path: Callable[[str], Path],
    repo_root: Path,
    hash_dir: Callable[[Path], str] | None = None,
) -> int:
    """ADR-0036 layer-3 runtime verification.

    Walks the lockfile for every detected Tier-1/2 adapter and confirms
    every recorded file exists, every managed hook appears in every
    native config the adapter writes, and every skill carries the
    `.playbook-owned` marker. Exits 0 if every detected adapter passes;
    non-zero on any drift.

    Dependencies (load_lockfile, detected_adapters, resolve_locked_path)
    are injected from install.py so this module stays import-cycle free.
    """
    lock = load_lockfile(target, repo_root)
    if not lock:
        print("No .playbook-lock.json found. Run `make install` first.")
        return 1

    detected = {a.name for a in detected_adapters()}
    print("Verify report (ADR-0036 layer-3: lockfile vs native config vs on-disk)")
    print(f"Lockfile: {lock['generated_at']} (version {lock['version']})")
    if lock.get("target"):
        print(f"Target: {lock['target']}")
    if lock.get("profile"):
        print(f"Profile: {lock['profile']}")
    print()

    overall_pass = True
    any_skipped = False
    any_verified = False

    for adapter_name, entries in lock.get("adapters", {}).items():
        if adapter_name not in detected:
            print(f"  [{adapter_name}] SKIP (not detected on this machine)")
            any_skipped = True
            continue
        any_verified = True

        managed_keys = lock.get("managed_keys", {}).get(adapter_name, {})
        passed, issues, counts = verify_adapter(
            adapter_name,
            entries,
            managed_keys,
            target,
            resolve_locked_path=resolve_locked_path,
            hash_dir=hash_dir,
        )
        status = "OK" if passed else "FAIL"
        if not passed:
            overall_pass = False

        print(f"  [{adapter_name}] {status}")
        files_line = (
            f"    files:  {counts['lockfile_files']} in lockfile, "
            f"{counts['missing_files']} missing on disk"
        )
        if counts.get("copied_dir_drift"):
            files_line += f", {counts['copied_dir_drift']} copied-dir drift(s)"
        print(files_line)
        per_config = counts["native_hooks_per_config"]
        if counts["lockfile_hooks"] or per_config:
            print(f"    hooks:  {counts['lockfile_hooks']} in lockfile")
            for cfg_path_str, hook_count in per_config.items():
                print(f"            {hook_count} in {cfg_path_str}")
        mcp_per_config = counts["native_mcps_per_config"]
        if counts["lockfile_mcps"] or mcp_per_config:
            print(f"    mcps:   {counts['lockfile_mcps']} in lockfile")
            for cfg_path_str, mcp_count in mcp_per_config.items():
                print(f"            {mcp_count} in {cfg_path_str}")
        if counts["skill_dirs"]:
            owned = counts["skill_dirs"] - counts["skill_missing_marker"]
            print(
                f"    skills: {owned}/{counts['skill_dirs']} with "
                f".playbook-owned marker"
            )
        for issue in issues:
            print(f"    - {issue}")
        print()

    # v0.8 (ADR-0036 v0.8 extension): MCP runtime probe. cmd_verify
    # historically confirmed the MCP entry existed in the agent's native
    # config; this added pass spawns each registered server and checks
    # the MCP initialize handshake. Skipped probes (command path absent
    # because the venv hasn't been bootstrapped) do not fail the verify
    # exit code; "fail" and "timeout" outcomes do.
    #
    # v0.8 Codex round-7 trust-boundary fix: when --target is provided
    # (target-scoped verify), the probe is OPT-IN. A target-supplied
    # lockfile + .cursor/mcp.json or .windsurf/mcp.json can contain
    # arbitrary command + args; cmd_verify defaulting to spawn those
    # is a code-execution surface. Default behavior with --target is
    # to skip the probe; user opts in via MCP_RUNTIME_PROBE=on.
    #
    # User-level (no --target) probes still default ON because the
    # native configs are owned by the user themselves; spawning their
    # own commands is not a trust-boundary crossing.
    #
    # The opt-out env values (skip/0/off/false) still work for both
    # modes. The opt-in env value (on/1/true/yes) re-enables the probe
    # for target-scoped runs.
    import os as _os

    raw_env = _os.environ.get("MCP_RUNTIME_PROBE", "").lower()
    probe_explicit_off = raw_env in {"skip", "0", "off", "false"}
    probe_explicit_on = raw_env in {"on", "1", "true", "yes"}
    # v0.8 Codex round-9 fix: probe_disabled now only gates the
    # EXPLICITLY-OFF case. Per-config trust scoping (target vs user)
    # happens further down so user-level configs always probe by
    # default, even when --target is set.
    probe_disabled = probe_explicit_off
    from mcp_runtime_probe import ProbeResult, probe_all_servers

    # v0.9 (ADR-0039): each ManagedMcpEntry records the exact config_path
    # the playbook wrote to, so we probe (name, recorded_config_path)
    # directly instead of over-probing by walking every config the
    # adapter touches. A name installed at user level but absent from
    # the project file no longer gets a spurious probe against the
    # project file.
    probe_entries: list[tuple[str, Path]] = []
    seen_pairs: set[tuple[str, str]] = set()
    for adapter_name in lock.get("managed_keys", {}):
        if adapter_name not in detected:
            continue
        raw_entries = (
            lock.get("managed_keys", {}).get(adapter_name, {}).get("mcp_servers", [])
        )
        for entry in raw_entries:
            if not isinstance(entry, dict):
                continue
            name = entry.get("name")
            cfg_path_str = entry.get("config_path")
            if not isinstance(name, str) or not isinstance(cfg_path_str, str):
                continue
            key = (cfg_path_str, name)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            probe_entries.append((name, Path(cfg_path_str)))

    # v0.8 Codex round-9 fix + v0.9 round-1 HIGH-1 + round-3 Codex P3
    # + round-9 adversarial HIGH-2 fix: trust boundary is per (adapter,
    # config_path), not per --verify invocation. User-level configs
    # (~/.claude.json, ~/.codex/config.toml, ~/.cursor/mcp.json) are
    # owned by the user. Target-scoped configs (<target>/.cursor/mcp.json,
    # <target>/.windsurf/mcp.json) are target-supplied; probe is opt-in.
    #
    # Round-1 fix: classify against target dir, not just $HOME.
    # Round-3 fix (Codex P3): target==$HOME falls back to user-scope.
    #
    # Round-9 fix (adversarial HIGH-2): the target lockfile is
    # target-controlled input. A malicious or accidentally-bad target
    # lockfile could set config_path to a $HOME native config (e.g.,
    # ~/.cursor/mcp.json) so the resolved path passes the under-$HOME
    # user-scope check and the probe spawns target-controlled commands
    # by default. The fix: when a target is active (and not == $HOME),
    # treat EVERY probe entry sourced from THE TARGET LOCKFILE as
    # target-scoped, regardless of where config_path resolves to. The
    # default-skip + MCP_RUNTIME_PROBE=on gate then applies uniformly.
    home_resolved = Path.home().resolve()
    target_resolved = target.resolve() if target is not None else None
    target_is_home = target_resolved is not None and target_resolved == home_resolved
    # Did we load the lockfile from the target dir specifically? When
    # the answer is yes, the lockfile is target-controlled input. This
    # is true exactly when target is set + target != home + a lockfile
    # exists under target (cmd_verify only reaches this point with a
    # successfully-loaded lockfile, and load_lockfile prefers
    # target/.playbook-lock.json over repo_root/).
    lockfile_came_from_target = (
        target is not None
        and target_resolved is not None
        and not target_is_home
        and (target / ".playbook-lock.json").exists()
    )

    def _is_target_scoped(cfg_path: Path) -> bool:
        # Round-9 HIGH fix: if the lockfile itself is target-controlled,
        # every probe entry it contributes is target-scoped regardless
        # of where config_path resolves to. This prevents a
        # target-supplied lockfile from naming ~/.cursor/mcp.json and
        # bypassing the MCP_RUNTIME_PROBE=on gate.
        if lockfile_came_from_target:
            return True
        try:
            resolved = cfg_path.resolve()
        except OSError:
            return True  # safer default
        if target_resolved is not None and not target_is_home:
            try:
                resolved.relative_to(target_resolved)
                return True
            except ValueError:
                pass
        try:
            resolved.relative_to(home_resolved)
            return False
        except ValueError:
            return True

    if probe_entries and not probe_explicit_off:
        # Split probe entries by trust scope.
        user_scope: list[tuple[str, Path]] = []
        target_scope: list[tuple[str, Path]] = []
        for name, cfg_path in probe_entries:
            if _is_target_scoped(cfg_path):
                target_scope.append((name, cfg_path))
            else:
                user_scope.append((name, cfg_path))

        runnable: list[tuple[str, Path]] = list(user_scope)
        if probe_explicit_on:
            runnable.extend(target_scope)

        if runnable:
            print("MCP runtime probe (initialize handshake):")
            results: list[ProbeResult] = probe_all_servers(runnable)
            for res in results:
                tag = res.status.upper()
                print(
                    f"  [{res.server_name:<14}] {tag:<8} "
                    f"{res.config_path}  {res.detail}"
                )
                if res.status in {"fail", "timeout"}:
                    overall_pass = False
            print()
        skipped_target = [
            (name, cfg) for name, cfg in target_scope if not probe_explicit_on
        ]
        if skipped_target:
            print(
                f"MCP runtime probe: {len(skipped_target)} target-scoped entr(ies) "
                f"SKIPPED (opt in with MCP_RUNTIME_PROBE=on if you trust the "
                f"target's MCP configs)"
            )
            print()
    elif probe_disabled:
        if target is not None and not probe_explicit_off:
            print(
                "MCP runtime probe: SKIPPED (target-scoped verify defaults off; "
                "opt in with MCP_RUNTIME_PROBE=on if you trust the target's "
                "MCP configs)"
            )
        else:
            print("MCP runtime probe: SKIPPED (MCP_RUNTIME_PROBE env var disables it)")
        print()

    if not any_verified:
        print(
            "No detected adapters had lockfile sections to verify; install "
            "may not have been run on this machine yet."
        )
        return 0

    if overall_pass:
        msg = "OK: every detected adapter passes layer-3 verification."
        if any_skipped:
            msg += " (Some adapters skipped: not detected on this machine.)"
        print(msg)
        return 0

    print("FAIL: at least one adapter has lockfile <-> runtime drift.")
    print("Re-run `make install` (or `make update`) to re-materialize.")
    return 1


__all__ = ["cmd_verify", "verify_adapter"]
