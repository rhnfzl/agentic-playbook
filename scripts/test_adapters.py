#!/usr/bin/env python3
"""
Smoke test for the installer adapters.

Verifies:
  - Every Tier 1 / Tier 2 / Tier 3 adapter imports cleanly.
  - Each adapter writes the expected files into a temporary target.
  - Re-running an adapter is idempotent (managed blocks replace, do not duplicate).
  - Pre-existing user content in shared files (AGENTS.md, .clinerules, config.toml)
    is preserved across installs.
  - Codex config.toml stays parseable after re-install (the P2 regression check).
  - PLAYBOOK_TARGET pointing at the playbook checkout is rejected.

Runs entirely in tmpdirs with HOME and PLAYBOOK_TARGET redirected, so no real
user files are touched. Exit code 0 on success, 1 on failure.
"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import tomllib
from pathlib import Path


HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
sys.path.insert(0, str(HERE))

ADAPTERS = [
    "claude_code",
    "codex",
    "cursor",
    "windsurf",
    "copilot",
    "gemini_cli",
    "aider",
    "cline",
    "pi",
]


class Reporter:
    def __init__(self) -> None:
        self.failures: list[tuple[str, str]] = []
        self.passes = 0

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passes += 1
            print(f"    PASS  {label}")
        else:
            self.failures.append((label, detail))
            print(f"    FAIL  {label} :: {detail}")

    def summary(self) -> int:
        total = self.passes + len(self.failures)
        if self.failures:
            print(f"\nFAILED: {len(self.failures)} of {total}")
            for label, detail in self.failures:
                print(f"  - {label}: {detail}")
            return 1
        print(f"\nAll {total} checks passed.")
        return 0


def _scoped_env(home: Path):
    """Save and restore HOME around an install run.

    Per ADR-0024 PLAYBOOK_TARGET env var is retired; target is now passed
    explicitly into adapter.install(). HOME is still scoped so adapters
    that write to home-relative paths (claude_code, codex, cursor user-level,
    pi) land in tmpdirs rather than the user's real home.
    """
    saved = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        yield
    finally:
        if saved is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved


def _install_adapter(name: str, target: Path) -> None:
    """Run every Adapter in the module's ADAPTERS list against target.

    Per ADR-0024: adapters expose `ADAPTERS: list[Adapter]` (most modules
    one element; tier3 has twenty). install() takes a pre-loaded
    PlaybookContent and the explicit target.
    """
    from adapters._loader import PlaybookContent

    module = importlib.import_module(f"adapters.{name}")
    content = PlaybookContent.load(REPO_ROOT)
    for adapter in getattr(module, "ADAPTERS", []):
        list(adapter.install(content, target))


def _file_section_count(path: Path, marker: str) -> int:
    if not path.exists():
        return 0
    return path.read_text(encoding="utf-8").count(marker)


def test_adapters_import_cleanly(r: Reporter) -> None:
    print("\n[adapters import cleanly]")
    importlib.import_module("adapters._loader")
    for name in ADAPTERS + ["tier3"]:
        module = importlib.import_module(f"adapters.{name}")
        r.check(
            f"{name}.ADAPTERS exists",
            hasattr(module, "ADAPTERS") and isinstance(module.ADAPTERS, list),
            "missing or wrong type",
        )
        for adapter in getattr(module, "ADAPTERS", []):
            r.check(
                f"{name}.ADAPTERS[*].name set",
                isinstance(getattr(adapter, "name", None), str),
                "no name",
            )
            r.check(
                f"{name}.ADAPTERS[*].install callable",
                callable(getattr(adapter, "install", None)),
                "no install",
            )


def test_target_safety_rejects_playbook_root(r: Reporter) -> None:
    """Per ADR-0024 resolve_target reads cli_target only (env var retired)."""
    print("\n[target safety]")
    from adapters import _loader

    try:
        _loader.resolve_target(REPO_ROOT, cli_target=str(REPO_ROOT))
        r.check("resolve_target rejects repo_root via cli arg", False, "no exception")
    except ValueError as exc:
        r.check(
            "resolve_target rejects repo_root via cli arg",
            "playbook checkout itself" in str(exc),
            str(exc),
        )


def test_adapter_round_trip(r: Reporter, name: str) -> None:
    print(f"\n[round-trip: {name}]")
    with (
        tempfile.TemporaryDirectory() as home_str,
        tempfile.TemporaryDirectory() as target_str,
    ):
        home = Path(home_str).resolve()
        target = Path(target_str).resolve()

        gen = _scoped_env(home)
        next(gen)
        try:
            # Inject pre-existing user content where the adapter touches shared files.
            _seed_user_content(name, target, home)

            _install_adapter(name, target)
            paths_first = _snapshot(target, home)
            r.check(
                f"{name}: produced output files", bool(paths_first), "no files written"
            )

            # Idempotent re-install, managed blocks should replace, not duplicate.
            _install_adapter(name, target)
            paths_second = _snapshot(target, home)

            for path, content_first in paths_first.items():
                content_second = paths_second.get(path)
                if content_second is None:
                    r.check(
                        f"{name}: {path.name} still present after re-install",
                        False,
                        f"{path} disappeared",
                    )
                    continue
                r.check(
                    f"{name}: {path.name} re-install is byte-identical (idempotent)",
                    content_first == content_second,
                    "content changed between identical runs",
                )

            # No duplicated managed blocks (only for files that use the managed-block
            # pattern; .aider.conf.yml uses an idempotent `read:` directive instead;
            # SKILL.md files + per-command .md files are verbatim copies from source,
            # not managed blocks).
            verbatim_dirs = (
                str(home / ".cursor" / "commands"),
                str(home / ".claude" / "commands"),
            )
            for path in paths_second.keys():
                if path.name in (".aider.conf.yml", "SKILL.md"):
                    continue
                if any(str(path).startswith(d + os.sep) for d in verbatim_dirs):
                    continue
                if path.suffix in (".md", ".toml") or path.name == ".clinerules":
                    marker = "coding-agents-playbook BEGIN"
                    count = _file_section_count(path, marker)
                    r.check(
                        f"{name}: {path.name} has exactly one managed block",
                        count == 1,
                        f"found {count} BEGIN markers",
                    )

            # Pre-existing user content preserved (where seeded).
            _verify_seeded_content_preserved(r, name, target, home)

            # Codex-specific: config.toml stays parseable.
            if name == "codex":
                config_toml = home / ".codex" / "config.toml"
                if config_toml.exists():
                    try:
                        parsed = tomllib.loads(config_toml.read_text(encoding="utf-8"))
                        r.check("codex: config.toml parses after re-install", True)
                        r.check(
                            "codex: mcp_servers table present",
                            "mcp_servers" in parsed,
                            str(list(parsed.keys())),
                        )
                        # Pre-existing [mcp_servers.tavily] outside the managed
                        # block must survive untouched (the installer skips
                        # names that already exist outside the markers, instead
                        # of emitting a duplicate placeholder that would fail
                        # TOML parse).
                        tavily = parsed.get("mcp_servers", {}).get("tavily", {})
                        url = tavily.get("url", "")
                        r.check(
                            "codex: pre-existing mcp_servers.tavily preserved",
                            "PRE_EXISTING" in url,
                            f"tavily.url = {url!r}",
                        )
                    except tomllib.TOMLDecodeError as exc:
                        r.check(
                            "codex: config.toml parses after re-install",
                            False,
                            str(exc),
                        )
        finally:
            try:
                next(gen)
            except StopIteration:
                pass


def _seed_user_content(name: str, target: Path, home: Path) -> None:
    """Pre-create files with hand-authored content where the adapter will write."""
    seeds = {
        "cursor": [
            (
                target / "AGENTS.md",
                "# AGENTS.md (user-authored)\n\nDo not eat the user content.\n",
            )
        ],
        "windsurf": [
            (
                target / "AGENTS.md",
                "# AGENTS.md (user-authored)\n\nWindsurf rules below.\n",
            )
        ],
        "copilot": [
            (target / "AGENTS.md", "# AGENTS.md (user-authored)\n\nKeep this line.\n"),
            (
                target / ".github" / "copilot-instructions.md",
                "# Copilot (user-authored)\n\nPreserved line.\n",
            ),
        ],
        "gemini_cli": [
            (
                target / "AGENTS.md",
                "# AGENTS.md (user-authored)\n\nGemini preserves this.\n",
            )
        ],
        "aider": [
            (
                target / "AGENTS.md",
                "# AGENTS.md (user-authored)\n\nAider preserves this.\n",
            )
        ],
        "cline": [
            (
                target / "AGENTS.md",
                "# AGENTS.md (user-authored)\n\nCline preserves this.\n",
            ),
            (
                target / ".clinerules",
                "# .clinerules (user-authored)\n\nProject baseline.\n",
            ),
        ],
        "codex": [
            (
                home / ".codex" / "config.toml",
                '[model]\nname = "gpt-5"\n\n'
                "[mcp_servers.tavily]\n"
                'url = "https://example.invalid/tavily?token=PRE_EXISTING"\n',
            )
        ],
        "claude_code": [
            (
                home / "AGENTS.md",
                "# Global Agent Rules (user-authored)\n\nPersonal lint guard.\n",
            )
        ],
    }
    for path, content in seeds.get(name, []):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _verify_seeded_content_preserved(
    r: Reporter, name: str, target: Path, home: Path
) -> None:
    checks = {
        "cursor": [(target / "AGENTS.md", "Do not eat the user content")],
        "windsurf": [(target / "AGENTS.md", "Windsurf rules below")],
        "copilot": [
            (target / "AGENTS.md", "Keep this line"),
            (target / ".github" / "copilot-instructions.md", "Preserved line"),
        ],
        "gemini_cli": [(target / "AGENTS.md", "Gemini preserves this")],
        "aider": [(target / "AGENTS.md", "Aider preserves this")],
        "cline": [
            (target / "AGENTS.md", "Cline preserves this"),
            (target / ".clinerules", "Project baseline"),
        ],
        "codex": [(home / ".codex" / "config.toml", "[model]")],
        "claude_code": [(home / "AGENTS.md", "Personal lint guard")],
    }
    for path, needle in checks.get(name, []):
        if not path.exists():
            r.check(f"{name}: seeded {path.name} survived", False, f"{path} missing")
            continue
        text = path.read_text(encoding="utf-8")
        r.check(
            f"{name}: seeded user content in {path.name} preserved",
            needle in text,
            f"'{needle}' missing from {path}",
        )


def _snapshot(target: Path, home: Path) -> dict[Path, str]:
    """Return {path: content} for every file the adapter could have written."""
    interesting = [
        target / "AGENTS.md",
        target / ".github" / "copilot-instructions.md",
        target / ".clinerules",
        target / ".aider.conf.yml",
        target / ".gemini" / "settings.json",
        home / ".codex" / "AGENTS.md",
        home / ".codex" / "config.toml",
        home / "AGENTS.md",
        home / ".claude" / "CLAUDE.md",
        home / ".cline" / "rules" / "playbook.md",
        home / ".cursor" / "mcp.json",
        home / ".codeium" / "windsurf" / "memories" / "global_rules.md",
    ]
    snap = {p: p.read_text(encoding="utf-8") for p in interesting if p.exists()}
    # For adapters that primarily write a directory of skills (pi), include the
    # first SKILL.md so 'produced output files' is non-empty.
    for skills_root in [
        home / ".pi" / "agent" / "skills",
        home / ".cursor" / "skills",
        home / ".agents" / "skills",  # Codex per ADR P2 #4
    ]:
        if skills_root.is_dir():
            for skill_md in sorted(skills_root.rglob("SKILL.md")):
                snap[skill_md] = skill_md.read_text(encoding="utf-8")
                break  # one sentinel is enough to prove the adapter wrote skills
    # Include the first command file each commands-supporting adapter wrote,
    # so the round-trip test can prove commands/ content actually landed.
    for commands_root in [
        home / ".cursor" / "commands",
        home / ".claude" / "commands",
    ]:
        if commands_root.is_dir():
            for cmd_md in sorted(commands_root.glob("*.md")):
                snap[cmd_md] = cmd_md.read_text(encoding="utf-8")
                break
    return snap


def test_materialize_mcp_sources(r: Reporter) -> None:
    """Verify _loader.materialize_mcp_sources symlinks bundled Python MCPs.

    Cursor R2 missing: the materialize path was untested. Cover:
      - "created" action on first install (symlink placed at empty target)
      - "unchanged" action on second install (symlink already points correctly)
      - "updated" action when an existing symlink points elsewhere
      - "skipped-real-file" action when a real file is in the way
    All four cases must NOT touch the user's actual ~/.config/agent-shared/.
    """
    print("\n[materialize_mcp_sources]")
    from adapters import _loader

    bundled = [
        m
        for m in _loader.load_mcp_configs(
            _loader.resolve_content_paths(["team"], REPO_ROOT)
        )
        if m.source_dir is not None
    ]
    r.check(
        "materialize_mcp_sources: at least one bundle exists",
        len(bundled) > 0,
        f"found {len(bundled)} bundled MCP(s)",
    )
    if not bundled:
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        target_dir = Path(tmpdir) / "mcp_servers"

        actions = _loader.materialize_mcp_sources(bundled, target_dir=target_dir)
        created = [a for a in actions if a[2] == "created"]
        r.check(
            "materialize_mcp_sources: first run creates symlinks",
            len(created) > 0,
            f"{len(actions)} actions, {len(created)} created",
        )
        for _, link_path, _ in created:
            r.check(
                f"materialize: {link_path.name} is a symlink after first run",
                link_path.is_symlink(),
                f"{link_path}",
            )

        actions_second = _loader.materialize_mcp_sources(bundled, target_dir=target_dir)
        unchanged = [a for a in actions_second if a[2] == "unchanged"]
        r.check(
            "materialize_mcp_sources: idempotent (second run is unchanged)",
            len(unchanged) == len(actions),
            f"{len(unchanged)}/{len(actions)} unchanged",
        )

        first_action = next(iter(actions), None)
        if first_action is not None:
            _, link_path, _ = first_action
            link_path.unlink()
            decoy_dir = Path(tmpdir) / "decoy"
            decoy_dir.mkdir()
            decoy = decoy_dir / "decoy.py"
            decoy.write_text("# unrelated file\n", encoding="utf-8")
            link_path.symlink_to(decoy)
            actions_third = _loader.materialize_mcp_sources(
                bundled, target_dir=target_dir
            )
            updated = [a for a in actions_third if a[2] == "updated"]
            r.check(
                "materialize_mcp_sources: replaces wrong-target symlinks",
                len(updated) >= 1,
                f"{len(updated)} updated",
            )

        first_action = next(iter(actions), None)
        if first_action is not None:
            _, link_path, _ = first_action
            link_path.unlink()
            link_path.write_text("# real file blocking the symlink\n", encoding="utf-8")
            actions_fourth = _loader.materialize_mcp_sources(
                bundled, target_dir=target_dir
            )
            skipped = [a for a in actions_fourth if a[2] == "skipped-real-file"]
            r.check(
                "materialize_mcp_sources: refuses to overwrite real files",
                len(skipped) >= 1,
                f"{len(skipped)} skipped-real-file",
            )
            r.check(
                "materialize_mcp_sources: real file content preserved",
                "real file blocking" in link_path.read_text(encoding="utf-8"),
                "real file got overwritten",
            )


def test_expand_agent_shared_placeholder(r: Reporter) -> None:
    """Verify {{AGENT_SHARED_MCP_DIR}} expansion produces machine-correct paths."""
    print("\n[expand_agent_shared_placeholder]")
    from adapters import _loader

    sample = {
        "command": "python3",
        "args": ["{{AGENT_SHARED_MCP_DIR}}/server.py"],
        "env": {"PYTHONPATH": "{{AGENT_SHARED_MCP_DIR}}"},
    }
    expanded = _loader.expand_agent_shared_placeholder(sample, "my-mcp")
    expected_root = str(
        (Path.home() / ".config" / "agent-shared" / "mcp_servers" / "my-mcp").resolve()
    )
    r.check(
        "expand_placeholder: args[0] resolves to expected absolute path",
        expanded["args"][0] == f"{expected_root}/server.py",
        f"got {expanded['args'][0]!r}",
    )
    r.check(
        "expand_placeholder: env value resolves",
        expanded["env"]["PYTHONPATH"] == expected_root,
        f"got {expanded['env']['PYTHONPATH']!r}",
    )
    r.check(
        "expand_placeholder: leaves original config dict untouched",
        sample["args"][0] == "{{AGENT_SHARED_MCP_DIR}}/server.py",
        "expand_placeholder mutated its input",
    )


def test_agent_to_toml_roundtrip(r: Reporter) -> None:
    """Verify _loader.agent_to_toml produces parseable Codex TOML for every Agent.

    Cursor audit a2 (MEDIUM): agent_to_toml was only covered indirectly via
    install snapshots. This test reads each authored agents/<name>.md, converts
    to TOML, parses with tomllib, and checks that name / description /
    developer_instructions survive intact. Important for agents whose body
    contains regex backslashes (R8-\\d+ matchers, escape sequences) since the
    P1 #2 fix routes those through literal triple-quote TOML strings.
    """
    print("\n[agent_to_toml roundtrip]")
    from adapters import _loader

    agents = _loader.load_agents(
        _loader.resolve_content_paths(["team"], REPO_ROOT)
    )
    r.check(
        "agent_to_toml: agents directory has loadable content",
        len(agents) > 0,
        f"loaded {len(agents)} agents",
    )
    for agent in agents:
        rendered = _loader.agent_to_toml(agent)
        try:
            parsed = tomllib.loads(rendered)
        except tomllib.TOMLDecodeError as exc:
            r.check(f"agent_to_toml: {agent.name} parses", False, str(exc))
            continue
        r.check(
            f"agent_to_toml: {agent.name} parses", True, f"{len(rendered)} byte TOML"
        )
        r.check(
            f"agent_to_toml: {agent.name} name preserved",
            parsed.get("name") == agent.frontmatter.get("name", agent.name),
            f"got {parsed.get('name')!r}",
        )
        r.check(
            f"agent_to_toml: {agent.name} description preserved",
            parsed.get("description") == agent.frontmatter.get("description"),
            f"got {parsed.get('description', '')[:80]!r}",
        )
        instructions = parsed.get("developer_instructions", "")
        r.check(
            f"agent_to_toml: {agent.name} developer_instructions non-empty",
            len(instructions) > 0,
            f"len={len(instructions)}",
        )
        # Body content survives the round-trip (compare a first non-empty line
        # from the body against the rendered instructions).
        body_signal = next(
            (line for line in agent.body.splitlines() if line.strip()), ""
        )
        if body_signal:
            r.check(
                f"agent_to_toml: {agent.name} body signal '{body_signal[:40]}...' present",
                body_signal in instructions,
                f"'{body_signal[:60]}' not found in instructions",
            )


def test_hook_coverage_per_adapter(r: Reporter) -> None:
    """v0.6 smoke check (per Cursor review Spec (a)): every adapter in
    _HOOK_REGISTERING_ADAPTERS reports the expected hook count after a
    clean install.

    Of 11 hook files on disk (v0.8):
      * 8 are "regular" (one event/matcher pair per hook)
      * 1 is the human-html-advisory.sh core paired with a sibling
        wrapper human-html-advisory-cursor.sh; the wrapper has
        PLAYBOOK-HOOK-CURSOR-ONLY: true and the core has
        PLAYBOOK-HOOK-CURSOR-WRAPPER pointing at the wrapper.
      * 2 are anchored-fs wrappers (pretool-edit + posttool-read) added
        in v0.8 (ADR-0037); they declare PLAYBOOK-HOOK-ADAPTERS: claude-code
        and are dead weight under any non-claude adapter.

    Resulting per-adapter registrations:
      * claude-code: 10 (8 regular + 2 anchored-fs wrappers; cursor-only
        wrapper filtered out)
      * codex / cline / copilot / windsurf: 8 (cursor-only wrapper AND
        anchored-fs wrappers filtered out; the cursor-wrapped core is
        still inherited)
      * cursor: 8 (cursor-wrapped core filtered, cursor-only wrapper
        takes its slot; anchored-fs wrappers excluded by ADAPTERS scope)

    The check exercises _new_managed_keys_for() which is what the
    installer uses to record managed paths in the lockfile, so a
    regression in either the filter (is_hook_for_adapter /
    is_wrapped_core) or the per-adapter event resolver gets caught at
    smoke time, not at user install time.
    """
    sys.path.insert(0, str(HERE))
    import install as install_module
    from adapters._loader import PlaybookContent, resolve_content_paths
    from adapters._reader import load_hooks

    repo_root = HERE.parent
    hooks = load_hooks(resolve_content_paths(["team"], repo_root))
    content = PlaybookContent(
        skills=[],
        rules=[],
        hooks=hooks,
        mcp_configs=[],
        agents=[],
        commands=[],
        prompts=[],
        trajectories=[],
    )

    total = len(hooks)
    # 11 expected: 8 regular + 1 cursor-only wrapper + 2 anchored-fs claude-only wrappers.
    r.check(
        "load_hooks finds 11 registerable hooks (8 + cursor wrapper + 2 anchored-fs)",
        total == 11,
        f"got {total} hooks",
    )

    expected_non_cursor = 8
    expected_claude_code = 10  # 8 + anchored-fs pretool/posttool wrappers
    for adapter_name in ("claude-code", "codex", "cline", "copilot"):
        keys = install_module._new_managed_keys_for(adapter_name, content, None)
        count = sum(len(paths) for paths in keys.get("hooks", {}).values())
        expected = (
            expected_claude_code
            if adapter_name == "claude-code"
            else expected_non_cursor
        )
        r.check(
            f"{adapter_name} registers {expected} hooks",
            count == expected,
            f"got {count} hooks",
        )

    cursor_keys = install_module._new_managed_keys_for("cursor", content, None)
    cursor_count = sum(len(paths) for paths in cursor_keys.get("hooks", {}).values())
    r.check(
        "cursor registers 8 hooks (wrapper replaces wrapped core; anchored-fs excluded)",
        cursor_count == 8,
        f"got {cursor_count} hooks",
    )

    windsurf_keys = install_module._new_managed_keys_for("windsurf", content, None)
    windsurf_count = len(windsurf_keys.get("windsurf_hooks", {}))
    r.check(
        "windsurf registers 8 hooks (cursor-only + anchored-fs filtered)",
        windsurf_count == expected_non_cursor,
        f"got {windsurf_count} hooks",
    )


def main() -> int:
    r = Reporter()
    test_adapters_import_cleanly(r)
    test_target_safety_rejects_playbook_root(r)
    test_agent_to_toml_roundtrip(r)
    test_materialize_mcp_sources(r)
    test_expand_agent_shared_placeholder(r)
    test_hook_coverage_per_adapter(r)
    for adapter in ADAPTERS:
        test_adapter_round_trip(r, adapter)
    return r.summary()


if __name__ == "__main__":
    raise SystemExit(main())
