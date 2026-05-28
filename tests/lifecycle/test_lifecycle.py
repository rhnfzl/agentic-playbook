"""Six v0.5 lifecycle scenarios.

Exercises the install -> narrow -> update cycle for the new behaviors
introduced in commits 1-7 of the v0.5 PR. Each scenario sets up a clean
$HOME or target directory, runs a small slice of content through the
relevant code path, and asserts the on-disk shape.

Scenarios:
  1. test_home_mcp_narrow_cleans_orphans                  managed_keys reconciliation
  2. test_agents_md_managed_block_idempotent              second AgentsMd save is no-op
  3. test_target_unified_materialization_symlink_mode     TargetMaterializer happy path
  4. test_target_narrow_cleans_orphans                    prune_orphans on profile narrow
  5. test_hook_reconciliation_removes_dropped_hooks       managed hook command cleanup
  6. test_agents_md_preserves_user_content_outside_managed_block  hand-edits survive

Adversarial review regression tests (locked in v0.5):
  7. test_claude_code_hook_dedup_preserves_user_hook_in_mixed_entry
  8. test_target_materializer_refuses_to_clobber_real_dir
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from adapters._loader import (
    Hook,
    PlaybookContent,
    Rule,
    Skill,
)
from adapters._protocol import (
    reconcile_managed_hook_commands,
    reconcile_managed_json_mcp,
)
from agents_md import AgentsMd
from target_materializer import (
    TargetMaterializer,
    prune_orphans,
    read_lockfile,
    write_lockfile,
)


# === Helpers ===


def _make_skill(repo_root: Path, install_name: str) -> Skill:
    """Materialize a minimal real skill in the playbook source tree, returning
    its Skill record. Tests use this to seed content without depending on the
    full playbook corpus.
    """
    # v0.11 (ADR-0040): skills moved to base/skills/. Glob covers post-refactor
    # layout and falls back to legacy skills/ if base/ is absent in the fixture.
    sample = next(
        repo_root.glob("base/skills/**/SKILL.md"),
        None,
    ) or next(repo_root.glob("skills/**/SKILL.md"))
    return Skill(
        path=sample,
        category=sample.parent.parent.name,
        name=sample.parent.name,
        frontmatter={},
        body="",
        install_name=install_name,
    )


def _make_rule(tmp_path: Path, name: str, body: str = "rule body") -> Rule:
    rule_path = tmp_path / f"{name}.md"
    rule_path.write_text(body, encoding="utf-8")
    return Rule(path=rule_path, name=name, body=body)


def _make_hook(
    tmp_path: Path,
    name: str,
    event: str,
    matcher: str = "Edit|Write",
) -> Hook:
    body = (
        f"#!/usr/bin/env bash\n"
        f"# PLAYBOOK-HOOK-EVENT: {event}\n"
        f"# PLAYBOOK-HOOK-MATCHER: {matcher}\n"
        f"echo {name}\n"
    )
    hook_path = tmp_path / f"{name}.sh"
    hook_path.write_text(body, encoding="utf-8")
    return Hook(path=hook_path, name=name, body=body)


def _empty_content(**overrides) -> PlaybookContent:
    base = dict(
        skills=[],
        rules=[],
        hooks=[],
        mcp_configs=[],
        agents=[],
        commands=[],
        prompts=[],
        trajectories=[],
    )
    base.update(overrides)
    return PlaybookContent(**base)


def _cursor_hook_commands(hooks_json: Path) -> list[str]:
    doc = json.loads(hooks_json.read_text(encoding="utf-8"))
    commands: list[str] = []
    for event_entries in doc.get("hooks", {}).values():
        if not isinstance(event_entries, list):
            continue
        commands.extend(
            entry["command"]
            for entry in event_entries
            if isinstance(entry, dict) and isinstance(entry.get("command"), str)
        )
    return commands


# === Scenario 1: HOME MCP narrow cleans orphans ===


def test_home_mcp_narrow_cleans_orphans(tmp_path: Path) -> None:
    """A prior install registered MCPs A + B. The current profile only ships A.
    reconcile_managed_json_mcp must remove B from the JSON config while
    preserving any user-authored entry (we add one named 'user-foo').
    """
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "atlassian": {"url": "https://example.com"},
                    "slack": {"url": "https://example.com"},
                    "user-foo": {"url": "user-authored"},
                }
            }
        ),
        encoding="utf-8",
    )

    prior_managed = {"atlassian", "slack"}
    new_managed = {"atlassian"}  # narrowed: only atlassian survives
    removed = reconcile_managed_json_mcp(
        claude_json, "mcpServers", new_managed, prior_managed
    )

    assert removed == 1, "slack should have been removed"
    final = json.loads(claude_json.read_text(encoding="utf-8"))["mcpServers"]
    assert "slack" not in final
    assert "atlassian" in final  # still managed, present
    assert "user-foo" in final  # user-authored, preserved


# === Scenario 2: HOME install idempotency (managed-block re-write is byte-stable) ===


def test_agents_md_managed_block_idempotent(tmp_path: Path) -> None:
    """Two consecutive with_managed_rules + save_to runs on the same rule set
    leave the file byte-identical (second save reports 'unchanged')."""
    agents_md_path = tmp_path / "AGENTS.md"
    rules = [_make_rule(tmp_path, "no-em-dashes", "# No Em Dashes\n\nbody")]

    first = (
        AgentsMd.load_or_empty(agents_md_path)
        .with_managed_rules(rules, label="test")
        .save_to(agents_md_path)
    )
    second_action = (
        AgentsMd.load_or_empty(agents_md_path)
        .with_managed_rules(rules, label="test")
        .save_to(agents_md_path)
    )

    assert first == "created"
    assert second_action == "unchanged", "re-run on same rules must be a no-op"


# === Scenario 3: target unified materialization (symlink mode) ===


def test_target_unified_materialization_symlink_mode(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """TargetMaterializer in symlink mode writes the unified .agents/ tree
    + per-tool projections + AGENTS.md managed block.
    """
    rules = [_make_rule(tmp_path, "demo-rule", "# Demo Rule\n\nbody")]
    hooks = [_make_hook(tmp_path, "demo-hook", "PostToolUse")]
    content = _empty_content(rules=rules, hooks=hooks)

    materializer = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    result = materializer.materialize(content)

    # Canonical store written
    assert (tmp_target / ".agents" / "rules" / "demo-rule.md").is_symlink()
    assert (tmp_target / ".agents" / "hooks" / "demo-hook.sh").is_symlink()
    # Per-tool projections (v0.6: cursor added per gap-analysis F5)
    assert (tmp_target / ".claude" / "hooks").is_symlink()
    assert (tmp_target / ".codex" / "skills").is_symlink()
    assert (tmp_target / ".cursor" / "hooks").is_symlink()
    assert (tmp_target / ".cursor" / "skills").is_symlink()
    # v0.6: cursor hooks.json generated alongside the projection
    assert (tmp_target / ".cursor" / "hooks.json").is_file()
    # v0.6 (Theme G): cursor .mdc rules + copilot single-file generation
    assert (tmp_target / ".cursor" / "rules" / "demo-rule.mdc").is_file()
    assert (tmp_target / ".github" / "copilot-instructions.md").is_file()
    mdc_body = (tmp_target / ".cursor" / "rules" / "demo-rule.mdc").read_text(
        encoding="utf-8"
    )
    assert mdc_body.startswith("---\n")
    assert "alwaysApply: true" in mdc_body
    assert "# Demo Rule" in mdc_body
    # AGENTS.md managed block created
    agents_md = (tmp_target / "AGENTS.md").read_text(encoding="utf-8")
    assert "coding-agents-playbook BEGIN" in agents_md
    assert "# Demo Rule" in agents_md
    # Result records counts
    assert result.counts["rules"] == 1
    assert result.counts["hooks"] == 1
    # 10 projections: .claude (4) + .codex (2) + .cursor (4)
    assert result.counts["projections"] == 10
    assert result.counts["cursor_hooks_json"] == 1


# === Scenario 4: target narrow cleans orphans ===


def test_target_narrow_cleans_orphans(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """First install ships two rules, second ships only one. The dropped
    rule's canonical entry must be removed by prune_orphans, and the
    lockfile must record only the surviving entries.
    """
    rule_a = _make_rule(tmp_path, "rule-a", "# A\n\nbody")
    rule_b = _make_rule(tmp_path, "rule-b", "# B\n\nbody")

    # First install: both rules
    first = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    first_result = first.materialize(_empty_content(rules=[rule_a, rule_b]))
    write_lockfile(tmp_target, first_result)
    assert (tmp_target / ".agents" / "rules" / "rule-a.md").exists()
    assert (tmp_target / ".agents" / "rules" / "rule-b.md").exists()

    # Second install: only rule_a (rule_b drops out)
    second = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    second_result = second.materialize(_empty_content(rules=[rule_a]))
    removed = prune_orphans(tmp_target, second_result.entries)
    write_lockfile(tmp_target, second_result)

    assert removed >= 1, "rule-b should have been pruned"
    assert (tmp_target / ".agents" / "rules" / "rule-a.md").exists()
    assert not (tmp_target / ".agents" / "rules" / "rule-b.md").exists()

    # Lockfile after second install should not list rule-b
    lock = read_lockfile(tmp_target)
    assert lock is not None
    assert not any("rule-b.md" in path for path in lock.get("entries", {})), (
        "rule-b should not appear in the post-narrow lockfile"
    )


# === Scenario 5: hook reconciliation removes dropped hooks ===


def test_hook_reconciliation_removes_dropped_hooks(tmp_path: Path) -> None:
    """settings.json has two playbook-managed hooks + one user-authored hook.
    On reconcile, the dropped playbook hook is removed; the surviving
    playbook hook and the user hook are preserved.
    """
    settings_path = tmp_path / "settings.json"
    hooks_dir = tmp_path / "hooks"
    hooks_dir.mkdir()
    managed_a = str(hooks_dir / "managed-a.sh")
    managed_b = str(hooks_dir / "managed-b.sh")
    user_hook = "/Users/test/.custom/my-hook.sh"

    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Edit",
                            "hooks": [{"type": "command", "command": managed_a}],
                        },
                        {
                            "matcher": "Edit",
                            "hooks": [{"type": "command", "command": managed_b}],
                        },
                        {
                            "matcher": "Bash",
                            "hooks": [{"type": "command", "command": user_hook}],
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    prior_hooks = {"PreToolUse": {managed_a, managed_b}}
    new_hooks = {"PreToolUse": {managed_a}}  # managed_b drops out

    removed = reconcile_managed_hook_commands(settings_path, new_hooks, prior_hooks)

    assert removed == 1
    final = json.loads(settings_path.read_text(encoding="utf-8"))
    entries = final["hooks"]["PreToolUse"]
    commands = [h["command"] for entry in entries for h in entry.get("hooks", [])]
    assert managed_a in commands
    assert managed_b not in commands
    assert user_hook in commands, "user-authored hook must be preserved"


# === Scenario 6: AgentsMd round-trip preserves user content outside the block ===


def test_agents_md_preserves_user_content_outside_managed_block(
    tmp_path: Path,
) -> None:
    """Hand-authored sections outside the managed-block markers must survive
    a with_managed_rules + save_to cycle. The first install creates the file;
    we then add a hand-authored section after the managed block, then
    re-materialize and confirm the hand-authored section is intact.
    """
    agents_md_path = tmp_path / "AGENTS.md"
    rules_v1 = [_make_rule(tmp_path, "rule-v1", "# Rule v1\n\nbody")]
    AgentsMd.load_or_empty(agents_md_path).with_managed_rules(
        rules_v1, label="test"
    ).save_to(agents_md_path)

    # Append a hand-authored section
    extra = "\n\n## Hand-Authored Section\n\nDo not delete this.\n"
    with agents_md_path.open("a", encoding="utf-8") as fh:
        fh.write(extra)
    assert "Hand-Authored Section" in agents_md_path.read_text(encoding="utf-8")

    # Re-materialize with different rules; hand-authored section must survive
    rules_v2 = [_make_rule(tmp_path, "rule-v2", "# Rule v2\n\nbody")]
    AgentsMd.load_or_empty(agents_md_path).with_managed_rules(
        rules_v2, label="test"
    ).save_to(agents_md_path)

    final_text = agents_md_path.read_text(encoding="utf-8")
    assert "Hand-Authored Section" in final_text
    assert "Do not delete this." in final_text
    assert "# Rule v2" in final_text
    assert "# Rule v1" not in final_text, "managed block must replace prior rules"


# === Scenario 7: install_mode=copy materializes independent deep copies ===


def test_target_unified_materialization_copy_mode(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """install_mode=copy must deep-copy canonical entries (not symlink).
    The dest file content must be byte-identical to the source on creation
    AND the dest must NOT track upstream changes (because it's a copy).
    """
    rule = _make_rule(tmp_path, "copy-rule", "# Copy Rule\n\noriginal body")
    content = _empty_content(rules=[rule])

    materializer = TargetMaterializer(tmp_target, repo_root, install_mode="copy")
    result = materializer.materialize(content)

    dest = tmp_target / ".agents" / "rules" / "copy-rule.md"
    assert dest.exists()
    assert not dest.is_symlink(), "copy mode must NOT produce a symlink"
    assert dest.read_text(encoding="utf-8") == rule.body, (
        "copy mode dest must be byte-identical to source on creation"
    )

    # Mutate the source AFTER materialization; copy-mode dest must not change
    rule.path.write_text("# Mutated\n\nupstream change", encoding="utf-8")
    assert dest.read_text(encoding="utf-8") == "# Copy Rule\n\noriginal body", (
        "copy mode dest must NOT track upstream source changes"
    )

    assert result.counts["rules"] == 1


# === Adversarial review regressions (locked in v0.5) ===


def test_claude_code_hook_dedup_preserves_user_hook_in_mixed_entry(
    tmp_home: Path,
) -> None:
    """settings.json entry contains a playbook hook AND a user-authored hook
    under the same matcher. The v0.5 upgrade must replace ONLY the playbook
    hook, not drop the whole entry. Locks the adversarial review high-severity
    finding (claude_code.py de-dupe loop).
    """
    from adapters.claude_code import _strip_command_from_entries

    user_authored = "/Users/test/.custom/keep-me.sh"
    playbook_old = str(tmp_home / ".claude" / "hooks" / "never-push-to-develop.sh")
    entries = [
        {
            "matcher": "Bash",
            "hooks": [
                {"type": "command", "command": playbook_old},
                {"type": "command", "command": user_authored},
            ],
        }
    ]

    stripped = _strip_command_from_entries(entries, playbook_old)
    assert len(stripped) == 1, "entry should survive when user hook remains"
    survivor_commands = [h["command"] for h in stripped[0]["hooks"]]
    assert user_authored in survivor_commands
    assert playbook_old not in survivor_commands


def test_target_materializer_refuses_to_clobber_real_dir(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """The TargetMaterializer must NOT replace a pre-existing real
    directory at a projection path. Locks the adversarial review
    high-severity finding (_refresh_symlink rmtree-without-ownership).
    """
    # User already has real content at target/.claude/commands/ (e.g. a
    # hand-authored command file the project ships).
    existing_dir = tmp_target / ".claude" / "commands"
    existing_dir.mkdir(parents=True)
    user_file = existing_dir / "my-command.md"
    user_file.write_text("# user command", encoding="utf-8")

    materializer = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    with pytest.raises(FileExistsError):
        materializer.materialize(
            _empty_content(rules=[_make_rule(tmp_path, "rule-x", "# X\n\nbody")])
        )

    # Verify user content survived
    assert user_file.exists(), "user-authored file must survive a refused materialize"
    assert user_file.read_text(encoding="utf-8") == "# user command", (
        "user content must be byte-identical"
    )


def test_prune_orphans_refuses_paths_outside_target(
    tmp_target: Path, tmp_path: Path
) -> None:
    """prune_orphans must NOT delete paths recorded in the lockfile that
    do not resolve under the target. Locks the Codex adversarial review
    round-2 [critical] finding (arbitrary file deletion via corrupted /
    malicious / cross-machine lockfile).
    """
    import json

    # Create a "victim" file outside the target tree
    victim = tmp_path / "victim.txt"
    victim.write_text("important user file", encoding="utf-8")

    # Forge a lockfile in the target that "owns" the victim path
    lockfile = tmp_target / ".playbook-state.json"
    lockfile.write_text(
        json.dumps(
            {
                "version": "0.5",
                "install_mode": "symlink",
                "entries": {
                    str(victim.resolve()): {"ownership": "owned", "kind": "skill"},
                    "../../../" + str(victim.name): {
                        "ownership": "owned",
                        "kind": "canonical",
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    # prune_orphans with empty new_entries should try to "clean up" both
    # forged entries; the path-escape guard must refuse them.
    removed = prune_orphans(tmp_target, {})

    assert removed == 0, "prune_orphans must refuse paths outside target"
    assert victim.exists(), "victim file outside target must survive prune_orphans"
    assert victim.read_text(encoding="utf-8") == "important user file"


def test_target_materializer_refuses_to_clobber_real_file(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """_write_file must NOT overwrite a real file at the canonical path
    that the prior lockfile does not record as owned. Locks the Codex
    adversarial review round-2 [high] finding (canonical file writes
    clobber unowned project content).
    """
    # Pre-existing real file at the canonical .agents/rules/ destination
    agents_rules = tmp_target / ".agents" / "rules"
    agents_rules.mkdir(parents=True)
    user_rule = agents_rules / "demo-rule.md"
    user_rule.write_text("# user-authored rule", encoding="utf-8")

    rule = _make_rule(tmp_path, "demo-rule", "# Playbook Rule\n\nbody")
    content = _empty_content(rules=[rule])

    materializer = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    with pytest.raises(FileExistsError):
        materializer.materialize(content)

    # User content survived
    assert user_rule.exists()
    assert user_rule.read_text(encoding="utf-8") == "# user-authored rule"


# === v0.6 Scenarios ========================================================
# v0.6 adds multi-agent hook parity (Cursor wrapper convention, Codex Bash-
# only auto-promote, Windsurf Cascade translator). The tests below lock the
# observable behaviors so future changes can't silently regress them.


def _make_hook_with_headers(
    tmp_path: Path, name: str, headers: dict, body_tail: str = "exit 0\n"
) -> Hook:
    """Variant of _make_hook that lets a test specify arbitrary PLAYBOOK-HOOK-*
    headers (CURSOR-MATCHER, CURSOR-WRAPPER, CURSOR-ONLY, WINDSURF-EVENT, etc.)
    """
    header_lines = "\n".join(f"# {k}: {v}" for k, v in headers.items())
    body = f"#!/usr/bin/env bash\n{header_lines}\n{body_tail}"
    hook_path = tmp_path / f"{name}.sh"
    hook_path.write_text(body, encoding="utf-8")
    return Hook(path=hook_path, name=name, body=body)


def test_codex_event_auto_promotes_edit_pretooluse_to_posttooluse(
    tmp_path: Path,
) -> None:
    """v0.6 (gap-analysis F20, ADR-0034): a hook declared as PreToolUse with
    a non-Bash matcher (Edit|Write) must register under PostToolUse for
    Codex because OpenAI Codex's PreToolUse reliably intercepts only Bash.
    Bash-matching hooks stay PreToolUse.
    """
    from hook_registration import codex_event_for

    edit_hook = _make_hook_with_headers(
        tmp_path,
        "edit-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write|MultiEdit",
        },
    )
    bash_hook = _make_hook_with_headers(
        tmp_path,
        "bash-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Bash",
        },
    )
    posttool_hook = _make_hook_with_headers(
        tmp_path,
        "posttool-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PostToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
        },
    )

    assert codex_event_for(edit_hook) == "PostToolUse", (
        "Edit-family PreToolUse must promote on Codex"
    )
    assert codex_event_for(bash_hook) == "PreToolUse", (
        "Bash PreToolUse must stay PreToolUse on Codex"
    )
    assert codex_event_for(posttool_hook) == "PostToolUse", (
        "Non-PreToolUse events are unchanged"
    )


def test_cursor_wrapper_replaces_core_in_registration(tmp_path: Path) -> None:
    """v0.6 (gap-analysis F9, ADR-0034/0035): when a hook declares
    PLAYBOOK-HOOK-CURSOR-WRAPPER: <wrapper>.sh and a sibling hook declares
    PLAYBOOK-HOOK-CURSOR-ONLY: true, the Cursor adapter copies both but
    registers ONLY the wrapper. Non-Cursor adapters skip the wrapper
    entirely (it's dead weight under ~/.claude/hooks/).
    """
    from hook_registration import (
        is_cursor_only,
        resolve_cursor_wrapper,
    )

    core = _make_hook_with_headers(
        tmp_path,
        "advisory",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
            "PLAYBOOK-HOOK-CURSOR-WRAPPER": "advisory-cursor.sh",
        },
    )
    wrapper = _make_hook_with_headers(
        tmp_path,
        "advisory-cursor",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write|StrReplace",
            "PLAYBOOK-HOOK-CURSOR-ONLY": "true",
        },
    )

    assert resolve_cursor_wrapper(core) == "advisory-cursor.sh"
    assert resolve_cursor_wrapper(wrapper) is None
    assert is_cursor_only(core) is False
    assert is_cursor_only(wrapper) is True


def test_windsurf_event_auto_derive(tmp_path: Path) -> None:
    """v0.6 (gap-analysis F16, ADR-0034): the auto-derive maps Claude event
    + matcher to one or more Cascade events. Mixed matchers (Bash|Edit)
    register for BOTH pre_run_command + pre_write_code.
    """
    from hook_registration import resolve_windsurf_events

    pre_bash = _make_hook_with_headers(
        tmp_path,
        "pre-bash",
        {"PLAYBOOK-HOOK-EVENT": "PreToolUse", "PLAYBOOK-HOOK-MATCHER": "Bash"},
    )
    pre_edit = _make_hook_with_headers(
        tmp_path,
        "pre-edit",
        {"PLAYBOOK-HOOK-EVENT": "PreToolUse", "PLAYBOOK-HOOK-MATCHER": "Edit|Write"},
    )
    post_mixed = _make_hook_with_headers(
        tmp_path,
        "post-mixed",
        {
            "PLAYBOOK-HOOK-EVENT": "PostToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write|Bash",
        },
    )
    session = _make_hook_with_headers(
        tmp_path,
        "session-brief",
        {"PLAYBOOK-HOOK-EVENT": "SessionStart", "PLAYBOOK-HOOK-MATCHER": "*"},
    )
    override = _make_hook_with_headers(
        tmp_path,
        "transcript-watcher",
        {
            "PLAYBOOK-HOOK-EVENT": "Stop",
            "PLAYBOOK-HOOK-MATCHER": "*",
            "PLAYBOOK-HOOK-WINDSURF-EVENT": "post_cascade_response_with_transcript",
        },
    )

    assert resolve_windsurf_events(pre_bash) == ["pre_run_command"]
    assert resolve_windsurf_events(pre_edit) == ["pre_write_code"]
    assert set(resolve_windsurf_events(post_mixed)) == {
        "post_run_command",
        "post_write_code",
    }
    assert resolve_windsurf_events(session) == ["post_setup_worktree"]
    assert resolve_windsurf_events(override) == [
        "post_cascade_response_with_transcript"
    ], "Explicit override must take precedence over auto-derive"


def test_target_materializer_generates_cursor_mdc_and_copilot_md(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """v0.6 (gap-analysis F5, Theme G): TargetMaterializer writes
    .cursor/rules/<name>.mdc with the Cursor frontmatter envelope and
    .github/copilot-instructions.md as a managed-block file.
    """
    rules = [_make_rule(tmp_path, "demo-rule", "# Demo Rule\n\nbody text")]
    content = _empty_content(rules=rules)
    materializer = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    result = materializer.materialize(content)

    mdc = tmp_target / ".cursor" / "rules" / "demo-rule.mdc"
    assert mdc.is_file()
    mdc_body = mdc.read_text(encoding="utf-8")
    assert mdc_body.startswith("---\n")
    assert "alwaysApply: true" in mdc_body
    assert "description: Demo Rule" in mdc_body
    assert "# Demo Rule" in mdc_body

    copilot = tmp_target / ".github" / "copilot-instructions.md"
    assert copilot.is_file()
    copilot_body = copilot.read_text(encoding="utf-8")
    assert "Copilot Instructions" in copilot_body
    assert "coding-agents-playbook BEGIN" in copilot_body
    assert "# Demo Rule" in copilot_body

    assert result.counts["cursor_mdc"] == 1
    assert result.counts["copilot_md"] == 1


def test_target_materializer_cursor_hooks_json_is_idempotent(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """Project Cursor hook registration strips the current managed command
    before appending it again, including the `bash .cursor/hooks/...` form
    emitted by the materializer.
    """
    hook = _make_hook_with_headers(
        tmp_path,
        "demo-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PostToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
        },
    )
    content = _empty_content(hooks=[hook])

    TargetMaterializer(tmp_target, repo_root, install_mode="symlink").materialize(
        content
    )
    TargetMaterializer(tmp_target, repo_root, install_mode="symlink").materialize(
        content
    )

    commands = _cursor_hook_commands(tmp_target / ".cursor" / "hooks.json")
    assert commands.count("bash .cursor/hooks/demo-hook.sh") == 1


def test_target_materializer_cursor_hooks_json_reconciles_zero_hook_profile(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """When a target narrows to a profile with no hooks, the managed
    .cursor/hooks.json is still rewritten so stale playbook commands do not
    point at pruned .cursor/hooks scripts.
    """
    hook = _make_hook_with_headers(
        tmp_path,
        "demo-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PostToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
        },
    )
    first = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    first_result = first.materialize(_empty_content(hooks=[hook]))
    write_lockfile(tmp_target, first_result)

    hooks_json = tmp_target / ".cursor" / "hooks.json"
    doc = json.loads(hooks_json.read_text(encoding="utf-8"))
    doc["hooks"].setdefault("postToolUse", []).append(
        {"command": "/Users/test/.custom/cursor-hook.sh", "timeout": 30}
    )
    hooks_json.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")

    second = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    second_result = second.materialize(_empty_content())
    removed = prune_orphans(tmp_target, second_result.entries)
    write_lockfile(tmp_target, second_result)

    commands = _cursor_hook_commands(hooks_json)
    assert "bash .cursor/hooks/demo-hook.sh" not in commands
    assert "/Users/test/.custom/cursor-hook.sh" in commands
    assert ".cursor/hooks.json" in second_result.entries
    assert removed >= 1


def test_cursor_skill_symlink_preserves_user_authored_dirs(
    tmp_home: Path, repo_root: Path
) -> None:
    """Adversarial-review regression (v0.6 post-review): a user with a
    personal skill at ~/.agents/skills/<name>/ OR ~/.cursor/skills/<name>/
    that COLLIDES with a playbook skill name must NOT lose content when
    the Cursor adapter runs. The adapter proves playbook ownership via
    .playbook-owned marker or legacy SKILL.md frontmatter; otherwise it
    warns + skips.

    Locks the high-severity finding from the v0.6 Codex adversarial
    review (cursor.py:208-242).
    """
    from adapters.cursor import CursorAdapter

    # v0.11 (ADR-0040): skills moved to base/skills/. Glob covers post-refactor
    # layout and falls back to legacy skills/ if base/ is absent in the fixture.
    sample = next(
        repo_root.glob("base/skills/**/SKILL.md"),
        None,
    ) or next(repo_root.glob("skills/**/SKILL.md"))
    install_name = sample.parent.name
    skill = Skill(
        path=sample,
        category=sample.parent.parent.name,
        name=sample.parent.name,
        frontmatter={},
        body="",
        install_name=install_name,
    )

    # Seed user-authored content at both target locations. NO .playbook-owned
    # marker, NO matching SKILL.md frontmatter (or the SKILL.md belongs to
    # someone else's skill).
    user_agents_dir = tmp_home / ".agents" / "skills" / install_name
    user_agents_dir.mkdir(parents=True)
    user_agents_payload = user_agents_dir / "MY_NOTES.md"
    user_agents_payload.write_text(
        "# my personal notes\nimportant content", encoding="utf-8"
    )
    user_cursor_dir = tmp_home / ".cursor" / "skills" / install_name
    user_cursor_dir.mkdir(parents=True)
    user_cursor_payload = user_cursor_dir / "MY_SKILL.md"
    user_cursor_payload.write_text(
        "---\nname: my-other-skill\n---\nuser body", encoding="utf-8"
    )

    adapter = CursorAdapter()
    content = _empty_content(skills=[skill])
    list(adapter.install(content, target=None))

    # User content survived at both locations.
    assert user_agents_payload.exists()
    assert user_agents_payload.read_text(encoding="utf-8") == (
        "# my personal notes\nimportant content"
    )
    assert user_cursor_payload.exists()
    assert user_cursor_payload.read_text(encoding="utf-8") == (
        "---\nname: my-other-skill\n---\nuser body"
    )
    # The cursor link was NOT created (because we couldn't prove ownership
    # of the canonical target, so the whole skill was skipped).
    cursor_link = tmp_home / ".cursor" / "skills" / install_name
    assert not cursor_link.is_symlink(), (
        "Cursor link must not be created when canonical target is user-owned"
    )


# === v0.7 layer-3 verification (ADR-0036): native config after install ===


def _hook_input_set(tmp_path: Path) -> list[Hook]:
    """Three hooks that exercise codex auto-promote + bash-vs-edit branches."""
    src = tmp_path / "src-hooks"
    src.mkdir(exist_ok=True)
    edit_hook = _make_hook_with_headers(
        src,
        "edit-hook",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
        },
    )
    bash_hook = _make_hook_with_headers(
        src,
        "bash-hook",
        {"PLAYBOOK-HOOK-EVENT": "PreToolUse", "PLAYBOOK-HOOK-MATCHER": "Bash"},
    )
    post_edit = _make_hook_with_headers(
        src,
        "post-edit",
        {
            "PLAYBOOK-HOOK-EVENT": "PostToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
        },
    )
    return [edit_hook, bash_hook, post_edit]


def _assert_all_commands_exist(by_event: dict[str, list[str]]) -> None:
    """Every command path the adapter registered must exist on disk. The
    install pipeline writes to runtime paths under the monkeypatched HOME;
    if a path is missing, layer-2 wrote the lockfile but layer-3 has nothing
    to load.
    """
    for cmds in by_event.values():
        for cmd in cmds:
            head = cmd.split()[0]
            assert Path(head).exists(), (
                f"layer-3 gap: registered command {cmd!r} does not exist on "
                "disk (lockfile would claim installed)"
            )


def _install_for(adapter_name: str, content, tmp_target: Path):
    """Construct + install for one adapter. Centralized to keep the
    parametrized hook + skill tests free of adapter-class import noise.
    """
    if adapter_name == "claude-code":
        from adapters.claude_code import ClaudeCodeAdapter

        return list(ClaudeCodeAdapter().install(content, tmp_target, None))
    if adapter_name == "codex":
        from adapters.codex import CodexAdapter

        return list(CodexAdapter().install(content, tmp_target, None))
    if adapter_name == "cursor":
        from adapters.cursor import CursorAdapter

        return list(CursorAdapter().install(content, target=None))
    if adapter_name == "cline":
        from adapters.cline import ClineAdapter

        return list(ClineAdapter().install(content, tmp_target, None))
    if adapter_name == "windsurf":
        from adapters.windsurf import WindsurfAdapter

        return list(WindsurfAdapter().install(content, tmp_target, None))
    if adapter_name == "copilot":
        from adapters.copilot import CopilotAdapter

        return list(CopilotAdapter().install(content, tmp_target, None))
    raise ValueError(f"unknown adapter: {adapter_name!r}")


# Layer-3 expectations per adapter: native config path (relative to tmp_home
# or tmp_target), the event keys we expect to see, and any per-shape extras.
# Centralizing the expectations table keeps the parametrized check small and
# makes drift visible as a single dict edit.
_HOOK_LAYER3_CASES = [
    {
        "id": "claude-code",
        "adapter": "claude-code",
        "config_under_home": ".claude/settings.json",
        "pre_event": "PreToolUse",
        "post_event": "PostToolUse",
        "edit_in_pre": True,
        "bash_in_pre": True,
        "translator_token": None,
    },
    {
        "id": "codex",
        "adapter": "codex",
        "config_under_home": ".codex/hooks.json",
        "pre_event": "PreToolUse",
        "post_event": "PostToolUse",
        "edit_in_pre": False,  # auto-promote to PostToolUse
        "bash_in_pre": True,
        "translator_token": None,
    },
    {
        "id": "cursor",
        "adapter": "cursor",
        "config_under_home": ".cursor/hooks.json",
        "pre_event": "preToolUse",
        "post_event": "postToolUse",
        "edit_in_pre": True,
        "bash_in_pre": True,
        "translator_token": None,
    },
    {
        "id": "cline",
        "adapter": "cline",
        "config_under_home": ".cline/hooks.json",
        "pre_event": "PreToolUse",
        "post_event": "PostToolUse",
        "edit_in_pre": True,
        "bash_in_pre": True,
        "translator_token": None,
    },
    {
        "id": "windsurf",
        "adapter": "windsurf",
        "config_under_home": ".codeium/windsurf/hooks.json",
        "pre_event": None,  # Windsurf uses pre_run_command + pre_write_code
        "post_event": "post_write_code",
        "edit_in_pre": True,
        "bash_in_pre": True,
        "translator_token": "_cascade-translate.sh",
    },
    # v0.8 (B5): Copilot's config sits under the TARGET project's
    # .github/hooks.json (per .github convention), not under HOME.
    # config_relative_to="target" selects the right root in the test
    # body; "home" stays the default for back-compat.
    {
        "id": "copilot",
        "adapter": "copilot",
        "config_under_home": ".github/hooks.json",
        "config_relative_to": "target",
        "pre_event": "PreToolUse",
        "post_event": "PostToolUse",
        "edit_in_pre": True,
        "bash_in_pre": True,
        "translator_token": None,
    },
]


@pytest.mark.parametrize(
    "case", _HOOK_LAYER3_CASES, ids=[c["id"] for c in _HOOK_LAYER3_CASES]
)
def test_native_hook_config_after_install(
    case: dict, tmp_home: Path, tmp_target: Path, tmp_path: Path
) -> None:
    """Layer-3 (ADR-0036): every adapter writes a native config whose
    registered commands resolve to scripts that exist on disk.

    Parametrized across claude-code / codex / cursor / cline / windsurf;
    expectations live in _HOOK_LAYER3_CASES. The shared
    parse_native_hook_commands parser from hook_native_config is reused
    so production verify and the lifecycle assertion walk identical JSON.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from hook_native_config import parse_native_hook_commands

    if case["adapter"] == "windsurf":
        # User-level Cascade install only runs when ~/.codeium exists.
        (tmp_home / ".codeium").mkdir(exist_ok=True)

    content = _empty_content(hooks=_hook_input_set(tmp_path))
    _install_for(case["adapter"], content, tmp_target)

    # v0.8 (B5): copilot writes its native config under target/.github,
    # not under home. config_relative_to="target" selects the right root.
    if case.get("config_relative_to") == "target":
        hooks_config = tmp_target / case["config_under_home"]
    else:
        hooks_config = tmp_home / case["config_under_home"]
    assert hooks_config.is_file(), (
        f"{case['adapter']} must write native config at {hooks_config}"
    )

    by_event = parse_native_hook_commands(hooks_config, case["adapter"])

    def _flat(event: str) -> str:
        return " ".join(by_event.get(event, []))

    if case["adapter"] == "windsurf":
        pre_run = _flat("pre_run_command")
        pre_write = _flat("pre_write_code")
        post_write = _flat(case["post_event"])
        assert "bash-hook.sh" in pre_run, "Bash matcher derives pre_run_command"
        assert "edit-hook.sh" in pre_write, "Edit-family derives pre_write_code"
        assert "post-edit.sh" in post_write
    else:
        pre_str = _flat(case["pre_event"])
        post_str = _flat(case["post_event"])
        if case["edit_in_pre"]:
            assert "edit-hook.sh" in pre_str, (
                f"{case['adapter']} keeps edit-hook under {case['pre_event']}"
            )
        else:
            assert "edit-hook.sh" not in pre_str, (
                f"{case['adapter']} must auto-promote edit-hook out of "
                f"{case['pre_event']}"
            )
            assert "edit-hook.sh" in post_str, (
                f"{case['adapter']} promotes edit-hook to {case['post_event']}"
            )
        if case["bash_in_pre"]:
            assert "bash-hook.sh" in pre_str, (
                f"{case['adapter']} keeps bash-hook under {case['pre_event']}"
            )
        assert "post-edit.sh" in post_str, (
            f"{case['adapter']} writes post-edit under {case['post_event']}"
        )

    if case["translator_token"]:
        for cmds in by_event.values():
            for cmd in cmds:
                assert case["translator_token"] in cmd, (
                    f"{case['adapter']} entry must wrap through "
                    f"{case['translator_token']}: {cmd!r}"
                )

    _assert_all_commands_exist(by_event)


def test_native_hook_config_cursor_wrapper_replaces_core(
    tmp_home: Path, tmp_path: Path
) -> None:
    """Layer-3 (ADR-0036): when PLAYBOOK-HOOK-CURSOR-WRAPPER is set, the
    wrapper appears under preToolUse and the wrapped core is NOT registered
    directly. Kept as a focused test because the wrapper convention is
    Cursor-specific and orthogonal to the per-adapter shape parametrization.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from adapters.cursor import CursorAdapter
    from hook_native_config import parse_native_hook_commands

    src = tmp_path / "src-hooks"
    src.mkdir(exist_ok=True)
    core = _make_hook_with_headers(
        src,
        "advisory",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write",
            "PLAYBOOK-HOOK-CURSOR-WRAPPER": "advisory-cursor.sh",
        },
    )
    wrapper = _make_hook_with_headers(
        src,
        "advisory-cursor",
        {
            "PLAYBOOK-HOOK-EVENT": "PreToolUse",
            "PLAYBOOK-HOOK-MATCHER": "Edit|Write|StrReplace",
            "PLAYBOOK-HOOK-CURSOR-ONLY": "true",
        },
    )
    content = _empty_content(hooks=[core, wrapper] + _hook_input_set(tmp_path))
    list(CursorAdapter().install(content, target=None))

    by_event = parse_native_hook_commands(tmp_home / ".cursor" / "hooks.json", "cursor")
    pre_camel = " ".join(by_event.get("preToolUse", []))

    assert "advisory-cursor.sh" in pre_camel, (
        "Cursor must register the wrapper for PLAYBOOK-HOOK-CURSOR-WRAPPER cores"
    )
    assert "advisory.sh" not in pre_camel.replace("advisory-cursor.sh", ""), (
        "Cursor must NOT register the wrapped core directly"
    )


# === v0.7 layer-3 verification (ADR-0036): skill install paths ===


def _assert_playbook_owned(skill_dir: Path, install_name: str) -> None:
    """The .playbook-owned marker proves which copy a re-install can safely
    overwrite. Missing marker = layer-2 wrote a skill dir the next install
    will refuse to touch.
    """
    marker = skill_dir / ".playbook-owned"
    assert marker.is_file(), (
        f"layer-3 gap: {skill_dir} has no .playbook-owned marker; next "
        "install will skip it as user-owned"
    )
    assert marker.read_text(encoding="utf-8").strip() == install_name


# Layer-3 expectations for skill install paths per adapter. install_under is
# "home" or "target"; the resolver below dereferences to tmp_home or
# tmp_target so the parametrization stays declarative.
#
# v0.8 Cursor review note: the v0.7 handoff mentioned "Copilot hook +
# Cline/Copilot skill lifecycle tests" but Copilot + Cline adapters do
# not install skills today (they handle rules + hooks only -- grep the
# adapter modules for "skill" returns no matches). The parametrization
# stays at claude-code / codex / cursor / windsurf because adding cline
# or copilot would test code paths that do not exist. If either
# adapter grows a skill surface, add the case row here.
_SKILL_LAYER3_CASES = [
    {
        "id": "claude-code",
        "adapter": "claude-code",
        "install_under": "home",
        "skill_dir": ".claude/skills/layer3-demo",
        "extra_check": None,
    },
    {
        "id": "codex",
        "adapter": "codex",
        "install_under": "home",
        "skill_dir": ".agents/skills/layer3-demo",
        # Codex must NOT write to ~/.codex/skills/ (Codex doesn't scan it).
        "extra_check": "no_codex_skills_dir",
    },
    {
        "id": "cursor",
        "adapter": "cursor",
        "install_under": "home",
        "skill_dir": ".agents/skills/layer3-demo",
        "extra_check": "cursor_symlink_points_to_canonical",
    },
    {
        "id": "windsurf",
        "adapter": "windsurf",
        "install_under": "target",
        "skill_dir": ".windsurf/skills/layer3-demo",
        "extra_check": None,
    },
]


@pytest.mark.parametrize(
    "case", _SKILL_LAYER3_CASES, ids=[c["id"] for c in _SKILL_LAYER3_CASES]
)
def test_native_skill_install_paths(
    case: dict, tmp_home: Path, tmp_target: Path, repo_root: Path
) -> None:
    """Layer-3 (ADR-0036): every skill-installing adapter materializes
    SKILL.md at the agent-loader path with the .playbook-owned marker.

    Note: the marker is the playbook's LAYER-2 ownership signal (proves
    which copy is safe to overwrite on re-install). True layer-3 runtime
    discovery additionally requires a new agent chat session; that part
    is out of scope for an offline test and is documented in
    skills/AGENTS.md.
    """
    skill = _make_skill(repo_root, install_name="layer3-demo")
    content = _empty_content(skills=[skill])
    _install_for(case["adapter"], content, tmp_target)

    install_root = tmp_home if case["install_under"] == "home" else tmp_target
    skill_dir = install_root / case["skill_dir"]
    assert (skill_dir / "SKILL.md").is_file(), (
        f"{case['adapter']} must materialize SKILL.md at {skill_dir}"
    )
    _assert_playbook_owned(skill_dir, "layer3-demo")

    if case["extra_check"] == "no_codex_skills_dir":
        assert not (tmp_home / ".codex" / "skills").exists(), (
            "codex must NOT write ~/.codex/skills/; Codex does not scan that path"
        )
    elif case["extra_check"] == "cursor_symlink_points_to_canonical":
        cursor_link = tmp_home / ".cursor" / "skills" / "layer3-demo"
        assert cursor_link.is_symlink() or cursor_link.is_dir(), (
            "cursor must expose the skill under ~/.cursor/skills/"
        )
        if cursor_link.is_symlink():
            assert cursor_link.resolve() == skill_dir.resolve(), (
                "cursor symlink must point at the ~/.agents/skills canonical"
            )


def test_safe_symlink_or_copy_relative_target_resolves_against_link_parent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """v0.7 Windows compat regression: the Windows symlink fallback
    must resolve a relative target against link_path.parent, not the process
    CWD. Cursor passes `../../.agents/skills/<name>`; without this fix the
    fallback copies whatever happens to live at CWD-relative `../../.agents/`
    or fails outright on Windows.
    """
    import adapters._writer as writer

    monkeypatch.setattr(writer, "os", type(writer.os)("os"))
    writer.os.name = "nt"
    writer.os.environ = {}

    canonical = tmp_path / ".agents" / "skills" / "demo"
    canonical.mkdir(parents=True)
    (canonical / "SKILL.md").write_text("# demo\n", encoding="utf-8")

    link_parent = tmp_path / ".cursor" / "skills"
    link_parent.mkdir(parents=True)
    link_path = link_parent / "demo"
    relative_target = Path("../..") / ".agents" / "skills" / "demo"

    def raising_symlink(self, target, target_is_directory=False):
        err = OSError(1, "privilege")
        # winerror is a Windows-only attribute; Pyright on POSIX rejects
        # direct assignment, so set it dynamically.
        setattr(err, "winerror", 1314)
        raise err

    monkeypatch.setattr(Path, "symlink_to", raising_symlink)
    monkeypatch.chdir(tmp_path.parent)

    result = writer.safe_symlink_or_copy(
        link_path, relative_target, target_is_directory=True
    )

    assert result == "copy"
    assert link_path.is_dir(), "fallback must materialize the directory at link_path"
    assert (link_path / "SKILL.md").is_file(), (
        "fallback must resolve relative target against link_path.parent so "
        "the canonical SKILL.md travels with the copy"
    )


def test_safe_symlink_or_copy_falls_back_to_copy_on_windows_privilege_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """v0.7 Windows compat: safe_symlink_or_copy must catch the
    'A required privilege is not held by the client' OSError (WinError 1314)
    that Path.symlink_to raises on Windows without Developer Mode, and fall
    back to copying the source content. Without this, install fails on
    every non-developer-mode Windows machine.
    """
    import adapters._writer as writer

    monkeypatch.setattr(writer, "os", type(writer.os)("os"))
    writer.os.name = "nt"
    writer.os.environ = {}

    def raising_symlink(self, target, target_is_directory=False):
        err = OSError(1, "privilege")
        # winerror is a Windows-only attribute; Pyright on POSIX rejects
        # direct assignment, so set it dynamically.
        setattr(err, "winerror", 1314)
        raise err

    monkeypatch.setattr(Path, "symlink_to", raising_symlink)

    source = tmp_path / "src.txt"
    source.write_text("hello", encoding="utf-8")
    dest = tmp_path / "dst.txt"

    result = writer.safe_symlink_or_copy(dest, source)

    assert result == "copy"
    assert dest.is_file() and not dest.is_symlink()
    assert dest.read_text(encoding="utf-8") == "hello"


def test_entry_for_records_copied_directory(tmp_path: Path) -> None:
    """v0.7 Codex review: when the Windows symlink fallback copies a
    directory tree, the lockfile must record it (with a tree_sha256) so
    `make status`, `make doctor-verify`, and `make remove` can see it.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    # v0.8 Cursor review fix: import from the focused module instead of
    # the install.py re-export facade so test coupling tracks the actual
    # implementation site.
    from install_lockfile import entry_for

    payload = tmp_path / "demo-skill"
    payload.mkdir()
    (payload / "SKILL.md").write_text("# demo\n", encoding="utf-8")
    (payload / ".playbook-owned").write_text("demo-skill\n", encoding="utf-8")

    entry = entry_for(payload, "owned")

    assert entry is not None
    assert entry["kind"] == "copied_dir"
    assert entry["ownership"] == "owned"
    assert isinstance(entry["tree_sha256"], str)
    assert len(entry["tree_sha256"]) == 64

    same_hash = entry_for(payload, "owned")
    assert same_hash and same_hash["tree_sha256"] == entry["tree_sha256"]

    (payload / "SKILL.md").write_text("# demo edited\n", encoding="utf-8")
    edited = entry_for(payload, "owned")
    assert edited and edited["tree_sha256"] != entry["tree_sha256"]


def test_safe_symlink_or_copy_reraises_non_privilege_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Genuine errors (read-only parent, missing source, etc.) must NOT be
    swallowed by the Windows fallback. The helper only handles WinError 1314;
    everything else surfaces so the caller sees the real failure.
    """
    import adapters._writer as writer

    def raising_symlink(self, target, target_is_directory=False):
        err = OSError(13, "permission denied")
        raise err

    monkeypatch.setattr(Path, "symlink_to", raising_symlink)

    source = tmp_path / "src.txt"
    source.write_text("hello", encoding="utf-8")
    dest = tmp_path / "dst.txt"

    with pytest.raises(OSError, match="permission denied"):
        writer.safe_symlink_or_copy(dest, source)


def _resolve_under_home(home: Path):
    """Helper: dependency-injected path resolver for verify_adapter tests."""

    def resolve(rel_or_abs: str) -> Path:
        p = Path(rel_or_abs)
        return p if p.is_absolute() else home / rel_or_abs

    return resolve


def test_verify_adapter_cursor_normalizes_pascal_to_camel_event(
    tmp_home: Path,
) -> None:
    """ADR-0036 layer-3: verify_adapter translates Cursor's PascalCase
    lockfile event keys to the camelCase keys Cursor's native hooks.json
    uses. Without this, a healthy Cursor install reports every hook as
    missing because PreToolUse != preToolUse in a dict lookup.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from install_verify import verify_adapter

    cursor_dir = tmp_home / ".cursor"
    cursor_dir.mkdir(parents=True)
    hook_script = cursor_dir / "hooks" / "demo.sh"
    hook_script.parent.mkdir()
    hook_script.write_text("#!/bin/sh\necho demo\n", encoding="utf-8")

    hooks_json = cursor_dir / "hooks.json"
    hooks_json.write_text(
        json.dumps(
            {
                "hooks": {
                    "preToolUse": [
                        {"command": str(hook_script), "matcher": "Edit|Write"}
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    entries = {str(hook_script.relative_to(tmp_home)): {"ownership": "owned"}}
    managed_keys = {"hooks": {"PreToolUse": [str(hook_script)]}}

    passed, issues, _counts = verify_adapter(
        "cursor",
        entries,
        managed_keys,
        target=None,
        resolve_locked_path=_resolve_under_home(tmp_home),
    )

    assert passed, (
        f"Cursor verify must pass after camelCase normalization; got {issues}"
    )


def test_verify_adapter_flags_missing_project_cursor_hooks_json(
    tmp_home: Path, tmp_target: Path
) -> None:
    """ADR-0036 layer-3: when target is set, the Cursor adapter writes BOTH
    ~/.cursor/hooks.json and <target>/.cursor/hooks.json. doctor-verify
    must check both; a missing project-level config used to slip through
    because only the user-level path was inspected.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from install_verify import verify_adapter

    user_dir = tmp_home / ".cursor"
    user_dir.mkdir(parents=True)
    hook_script = user_dir / "hooks" / "demo.sh"
    hook_script.parent.mkdir()
    hook_script.write_text("#!/bin/sh\n", encoding="utf-8")
    user_hooks_json = user_dir / "hooks.json"
    user_hooks_json.write_text(
        json.dumps({"hooks": {"preToolUse": [{"command": str(hook_script)}]}}),
        encoding="utf-8",
    )

    entries = {str(hook_script.relative_to(tmp_home)): {"ownership": "owned"}}
    managed_keys = {"hooks": {"PreToolUse": [str(hook_script)]}}

    passed, issues, _counts = verify_adapter(
        "cursor",
        entries,
        managed_keys,
        target=tmp_target,
        resolve_locked_path=_resolve_under_home(tmp_home),
    )

    assert not passed, (
        "verify must FAIL when project-level .cursor/hooks.json is missing"
    )
    joined = " ".join(issues)
    assert "/.cursor/hooks.json" in joined, (
        f"failure must name the project-level config path: {issues!r}"
    )


def test_verify_adapter_flags_missing_mcp_server(tmp_home: Path) -> None:
    """ADR-0036 layer-3: managed_keys.mcp_servers must be checked against the
    adapter's native MCP config. If a managed MCP entry vanishes from
    ~/.claude.json / ~/.codex/config.toml / ~/.cursor/mcp.json / ~/.codeium/
    windsurf/mcp.json, verify_adapter must FAIL. Without this, a removed
    runtime dependency hides while file + hook checks still pass.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from install_verify import verify_adapter

    cursor_dir = tmp_home / ".cursor"
    cursor_dir.mkdir(parents=True)
    # native config registers ONLY 'present-mcp'; managed_keys claims
    # 'present-mcp' AND 'missing-mcp', so the latter should surface as drift.
    (cursor_dir / "mcp.json").write_text(
        json.dumps({"mcpServers": {"present-mcp": {"url": "https://example.com"}}}),
        encoding="utf-8",
    )

    entries: dict = {}
    # v0.9 (ADR-0039): managed_keys.mcp_servers is list[ManagedMcpEntry];
    # each entry records the config_path the playbook wrote it to.
    cursor_cfg = str(cursor_dir / "mcp.json")
    managed_keys = {
        "mcp_servers": [
            {
                "id": "uuid-present",
                "name": "present-mcp",
                "config_path": cursor_cfg,
                "scope": "global",
                "installed_at": "2026-05-26T00:00:00+00:00",
            },
            {
                "id": "uuid-missing",
                "name": "missing-mcp",
                "config_path": cursor_cfg,
                "scope": "global",
                "installed_at": "2026-05-26T00:00:00+00:00",
            },
        ]
    }

    passed, issues, counts = verify_adapter(
        "cursor",
        entries,
        managed_keys,
        target=None,
        resolve_locked_path=_resolve_under_home(tmp_home),
    )

    assert not passed, "verify must FAIL when a managed MCP server is missing"
    assert counts["lockfile_mcps"] == 2
    joined = " ".join(issues)
    assert "missing-mcp" in joined, f"failure must name the missing server: {issues!r}"
    assert "present-mcp" not in joined or "missing-mcp" in joined.replace(
        "present-mcp", ""
    ), "verify must not flag the server that IS registered"


def test_verify_adapter_flags_wrong_event_registration(tmp_home: Path) -> None:
    """ADR-0036 layer-3 is event-specific: a hook registered under the
    WRONG event (e.g. PostToolUse instead of PreToolUse) fires at the
    wrong time. verify_adapter must FAIL and name the offending event
    rather than silently accept any event-key collision on the basename.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from install_verify import verify_adapter

    cursor_dir = tmp_home / ".cursor"
    cursor_dir.mkdir(parents=True)
    hook_script = cursor_dir / "hooks" / "guard.sh"
    hook_script.parent.mkdir()
    hook_script.write_text("#!/bin/sh\n", encoding="utf-8")
    # Native config has the script, but under postToolUse (wrong event).
    # The lockfile says PreToolUse; verify must flag the drift.
    (cursor_dir / "hooks.json").write_text(
        json.dumps({"hooks": {"postToolUse": [{"command": str(hook_script)}]}}),
        encoding="utf-8",
    )

    entries = {str(hook_script.relative_to(tmp_home)): {"ownership": "owned"}}
    managed_keys = {"hooks": {"PreToolUse": [str(hook_script)]}}

    passed, issues, _ = verify_adapter(
        "cursor",
        entries,
        managed_keys,
        target=None,
        resolve_locked_path=_resolve_under_home(tmp_home),
    )

    assert not passed, "verify must FAIL when a hook fires under the wrong event"
    joined = " ".join(issues)
    assert "postToolUse" in joined and "preToolUse" in joined, (
        f"failure must name BOTH the wrong and expected events: {issues!r}"
    )
    assert "event drift" in joined or "wrong" in joined.lower(), (
        f"failure must signal event mismatch: {issues!r}"
    )


def test_materialize_mcp_sources_replaces_prior_owned_copy(
    tmp_path: Path,
) -> None:
    """ADR-0036 layer-2 fix: on Windows, safe_symlink_or_copy falls back to
    copy and the playbook records the copy in `_bundles`. The NEXT install
    must recognise that path as a prior playbook-owned copy (replace) not
    as foreign content (skipped-real-file). Without this, repeat Windows
    installs orphan their own bundle files.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from adapters._loader import materialize_mcp_sources
    from adapters._protocol import McpConfig

    # Simulate a vendored bundle source directory.
    source_dir = tmp_path / "src-bundle"
    source_dir.mkdir()
    (source_dir / "server.py").write_text("# server\n", encoding="utf-8")
    (source_dir / "README.md").write_text("# readme\n", encoding="utf-8")  # skipped

    target_root = tmp_path / "agent-shared"
    target_root.mkdir()

    cfg = McpConfig(
        path=source_dir / "server.json",
        name="demo-bundle",
        config={},
        source_dir=source_dir,
    )

    # Simulate the post-Windows-fallback state: the linkpath already exists
    # as a real file (the prior install's copy fallback).
    expected_link = target_root / "demo-bundle" / "server.py"
    expected_link.parent.mkdir()
    expected_link.write_text("# stale copy\n", encoding="utf-8")

    # First check: WITHOUT prior_owned_paths, the helper treats the existing
    # real file as foreign (skipped-real-file).
    actions_no_hint = materialize_mcp_sources([cfg], target_dir=target_root)
    server_actions = [a for n, _p, a in actions_no_hint if n == "demo-bundle"]
    assert "skipped-real-file" in server_actions, (
        "without prior_owned_paths, the helper must protect user content"
    )

    # Now hand it the prior-owned set (this is what install.py does on rerun
    # from `_bundles` lockfile entries). The same existing file must be
    # treated as playbook-owned and refreshed.
    actions_with_hint = materialize_mcp_sources(
        [cfg], target_dir=target_root, prior_owned_paths={expected_link}
    )
    server_actions = [a for n, _p, a in actions_with_hint if n == "demo-bundle"]
    assert "updated" in server_actions, (
        f"prior_owned_paths hint must promote the existing real file to "
        f"updated, not leave it as skipped-real-file (actions: {server_actions})"
    )


def test_verify_adapter_substring_no_false_match(tmp_home: Path) -> None:
    """ADR-0036 layer-3: command_registers uses exact basename comparison so
    `lint-guard.sh` does NOT match `lint-guard-backup.sh`. Locks the
    substring-heuristic regression Codex thermo-nuclear review flagged.
    """
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    from install_verify import verify_adapter

    cursor_dir = tmp_home / ".cursor"
    cursor_dir.mkdir(parents=True)
    real_hook = cursor_dir / "hooks" / "lint-guard.sh"
    real_hook.parent.mkdir()
    real_hook.write_text("#!/bin/sh\n", encoding="utf-8")
    decoy_hook = cursor_dir / "hooks" / "lint-guard-backup.sh"
    decoy_hook.write_text("#!/bin/sh\n", encoding="utf-8")

    # Native config only registers the decoy; the expected hook is missing.
    hooks_json = cursor_dir / "hooks.json"
    hooks_json.write_text(
        json.dumps({"hooks": {"preToolUse": [{"command": str(decoy_hook)}]}}),
        encoding="utf-8",
    )

    entries = {
        str(real_hook.relative_to(tmp_home)): {"ownership": "owned"},
        str(decoy_hook.relative_to(tmp_home)): {"ownership": "owned"},
    }
    managed_keys = {"hooks": {"PreToolUse": [str(real_hook)]}}

    passed, issues, _ = verify_adapter(
        "cursor",
        entries,
        managed_keys,
        target=None,
        resolve_locked_path=_resolve_under_home(tmp_home),
    )

    assert not passed, (
        "exact-basename equality must flag lint-guard.sh as missing even "
        f"when lint-guard-backup.sh is present: {issues!r}"
    )
    joined = " ".join(issues)
    assert "lint-guard.sh" in joined


def test_pointer_mode_switch_strips_managed_cursor_hooks_json(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """v0.7 pointer-mode regression: switching to pointer mode must strip
    playbook-owned entries from the project-level managed hooks.json files
    (.cursor/hooks.json, .windsurf/hooks.json). prune_orphans alone misses
    them because they're tracked as ownership=managed.
    """
    hook = _make_hook_with_headers(
        tmp_path,
        "demo-hook",
        {"PLAYBOOK-HOOK-EVENT": "PostToolUse", "PLAYBOOK-HOOK-MATCHER": "Edit|Write"},
    )
    content = _empty_content(hooks=[hook])

    sym_mat = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    sym_result = sym_mat.materialize(content)
    write_lockfile(tmp_target, sym_result)

    cursor_hooks_json = tmp_target / ".cursor" / "hooks.json"
    assert cursor_hooks_json.is_file()
    before = json.loads(cursor_hooks_json.read_text(encoding="utf-8"))
    before_commands = [
        e.get("command", "")
        for entries in before.get("hooks", {}).values()
        if isinstance(entries, list)
        for e in entries
    ]
    assert any(".cursor/hooks/demo-hook.sh" in c for c in before_commands)

    ptr_mat = TargetMaterializer(tmp_target, repo_root, install_mode="pointer")
    ptr_mat.materialize(content)

    after = json.loads(cursor_hooks_json.read_text(encoding="utf-8"))
    after_commands = [
        e.get("command", "")
        for entries in after.get("hooks", {}).values()
        if isinstance(entries, list)
        for e in entries
    ]
    assert not any(".cursor/hooks/" in c for c in after_commands), (
        "pointer-mode switch must strip playbook-owned entries from "
        f"managed .cursor/hooks.json; still present: {after_commands!r}"
    )


def test_pointer_mode_switch_cleans_prior_symlink_install(
    tmp_target: Path, tmp_path: Path, repo_root: Path
) -> None:
    """v0.7 (ADR-0036 layer-2 fix): TargetMaterializer in symlink mode then
    pointer mode on the same target must clean up the prior .agents/ tree,
    not orphan it.

    Bug being locked: scripts/playbook_update.materialize_content used to
    short-circuit out of materialize+prune when install_mode=pointer, leaving
    .agents/skills/, .agents/rules/, etc. from the prior symlink install
    on disk as silent orphans.
    """
    rules = [_make_rule(tmp_path, "demo-rule", "# Demo\n\nbody")]
    hooks = [_make_hook(tmp_path, "demo-hook", "PostToolUse")]
    content = _empty_content(rules=rules, hooks=hooks)

    sym_mat = TargetMaterializer(tmp_target, repo_root, install_mode="symlink")
    sym_result = sym_mat.materialize(content)
    write_lockfile(tmp_target, sym_result)

    assert (tmp_target / ".agents" / "rules" / "demo-rule.md").exists()
    assert (tmp_target / ".agents" / "hooks" / "demo-hook.sh").exists()

    ptr_mat = TargetMaterializer(tmp_target, repo_root, install_mode="pointer")
    ptr_result = ptr_mat.materialize(content)
    removed = prune_orphans(tmp_target, ptr_result.entries)
    write_lockfile(tmp_target, ptr_result)

    assert removed > 0, "pointer-mode switch must prune prior .agents/ entries"
    assert not (tmp_target / ".agents" / "rules" / "demo-rule.md").exists(), (
        "prior rules dir must be cleaned when switching to pointer mode"
    )
    assert not (tmp_target / ".agents" / "hooks" / "demo-hook.sh").exists(), (
        "prior hooks dir must be cleaned when switching to pointer mode"
    )


