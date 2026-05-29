"""Shared lifecycle-test helpers (v0.8 split per Cursor review).

The original test_lifecycle.py grew to ~2,900 lines as v0.8 added the
runtime probe, registry, allowlist, underscore, and Codex fold-in
tests. Cursor's thermo-nuclear review flagged the file size as the
blocker. This module exports every shared helper so the test modules
can stay small and topic-focused.

Convention:

  * Underscore-prefixed names are helpers; pytest does not collect them.
  * Public helpers are alphabetized below for findability.
  * Fixtures live in conftest.py (repo_root, tmp_home, tmp_target).
"""

from __future__ import annotations

import json
from pathlib import Path

from adapters._loader import Hook, PlaybookContent, Rule, Skill


def _assert_all_commands_exist(by_event: dict[str, list[str]]) -> None:
    """Every command path the adapter registered must exist on disk.
    Layer-2 wrote the lockfile but layer-3 has nothing to load otherwise.
    """
    for cmds in by_event.values():
        for cmd in cmds:
            head = cmd.split()[0]
            assert Path(head).exists(), (
                f"layer-3 gap: registered command {cmd!r} does not exist on "
                "disk (lockfile would claim installed)"
            )


def _assert_playbook_owned(skill_dir: Path, install_name: str) -> None:
    """The playbook stamps `.playbook-owned` inside every materialized
    skill dir so re-install knows which copy is safe to overwrite. The
    marker contents are the canonical install_name; the test asserts
    both presence and value.
    """
    marker = skill_dir / ".playbook-owned"
    assert marker.is_file(), (
        f"skill dir {skill_dir} missing .playbook-owned marker; next "
        "install will skip it as user-owned"
    )
    assert marker.read_text(encoding="utf-8").strip() == install_name


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


def _install_for(adapter_name: str, content, tmp_target: Path):
    """Construct + install for one adapter. Centralized so parametrized
    hook + skill tests stay free of adapter-class import noise.
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


def _make_hook_with_headers(
    tmp_path: Path, name: str, headers: dict, body_tail: str = "exit 0\n"
) -> Hook:
    """Variant that lets a test specify arbitrary PLAYBOOK-HOOK-* headers
    (CURSOR-MATCHER, CURSOR-WRAPPER, CURSOR-ONLY, WINDSURF-EVENT, ADAPTERS, etc.)
    """
    header_lines = "\n".join(f"# {k}: {v}" for k, v in headers.items())
    body = f"#!/usr/bin/env bash\n{header_lines}\n{body_tail}"
    hook_path = tmp_path / f"{name}.sh"
    hook_path.write_text(body, encoding="utf-8")
    return Hook(path=hook_path, name=name, body=body)


def _make_rule(tmp_path: Path, name: str, body: str = "rule body") -> Rule:
    rule_path = tmp_path / f"{name}.md"
    rule_path.write_text(body, encoding="utf-8")
    return Rule(path=rule_path, name=name, body=body)


def _make_skill(repo_root: Path, install_name: str) -> Skill:
    """Pick the first SKILL.md in the repo and wrap it as a Skill record."""
    sample = next(repo_root.glob("skills/**/SKILL.md"))
    return Skill(
        path=sample,
        category=sample.parent.parent.name,
        name=sample.parent.name,
        frontmatter={},
        body="",
        install_name=install_name,
    )


def _write_fake_mcp_server(tmp_path: Path, behavior: str) -> Path:
    """Write a fake stdio MCP server for runtime-probe tests.

    behavior in {"ok", "error", "non_json", "no_stdout", "hang"} controls
    the response shape. v0.8 fold-in adds the realistic 'long-running'
    case (see _write_long_running_fake_server) but the original five
    behaviors are still useful for the unit tests.
    """
    script = tmp_path / f"fake-{behavior}.py"
    if behavior == "ok":
        body = (
            "import json, sys\n"
            "line = sys.stdin.readline()\n"
            "req = json.loads(line)\n"
            "resp = {\n"
            "    'jsonrpc': '2.0', 'id': req['id'],\n"
            "    'result': {\n"
            "        'protocolVersion': '2024-11-05',\n"
            "        'serverInfo': {'name': 'fake-ok', 'version': '1.0'},\n"
            "        'capabilities': {},\n"
            "    },\n"
            "}\n"
            "sys.stdout.write(json.dumps(resp) + '\\n')\n"
            "sys.stdout.flush()\n"
        )
    elif behavior == "error":
        body = (
            "import json, sys\n"
            "line = sys.stdin.readline()\n"
            "req = json.loads(line)\n"
            "resp = {\n"
            "    'jsonrpc': '2.0', 'id': req['id'],\n"
            "    'error': {'code': -32603, 'message': 'simulated failure'},\n"
            "}\n"
            "sys.stdout.write(json.dumps(resp) + '\\n')\n"
            "sys.stdout.flush()\n"
        )
    elif behavior == "non_json":
        body = (
            "import sys\nsys.stdin.readline()\n"
            "sys.stdout.write('not json at all\\n')\nsys.stdout.flush()\n"
        )
    elif behavior == "no_stdout":
        body = (
            "import sys\nsys.stdin.readline()\n"
            "sys.stderr.write('only stderr\\n')\nsys.stderr.flush()\n"
        )
    elif behavior == "hang":
        body = "import sys, time\nsys.stdin.readline()\ntime.sleep(30)\n"
    else:
        raise ValueError(f"unknown behavior: {behavior}")
    script.write_text(body, encoding="utf-8")
    return script


def _write_fake_mcp_config(
    tmp_path: Path,
    *,
    server_name: str,
    command: str,
    args: list[str],
    fmt: str,
) -> Path:
    """Write a minimal MCP native config (JSON or TOML) for probe tests."""
    if fmt == "json":
        path = tmp_path / "mcp.json"
        path.write_text(
            json.dumps(
                {"mcpServers": {server_name: {"command": command, "args": args}}}
            ),
            encoding="utf-8",
        )
    else:
        path = tmp_path / "config.toml"
        args_toml = "[" + ", ".join(f'"{a}"' for a in args) + "]"
        path.write_text(
            f'[mcp_servers.{server_name}]\ncommand = "{command}"\nargs = {args_toml}\n',
            encoding="utf-8",
        )
    return path


def _write_long_running_fake_server(tmp_path: Path) -> Path:
    """Fake stdio MCP server that answers initialize and then stays alive
    (the realistic shape every real MCP server has). Pin for the Codex
    P1 fix: communicate() would wait for EOF and timeout against this.
    """
    script = tmp_path / "fake-long-running.py"
    script.write_text(
        "import json, sys\n"
        "line = sys.stdin.readline()\n"
        "req = json.loads(line)\n"
        "resp = {\n"
        "    'jsonrpc': '2.0', 'id': req['id'],\n"
        "    'result': {\n"
        "        'protocolVersion': '2024-11-05',\n"
        "        'serverInfo': {'name': 'fake-long-running', 'version': '1.0'},\n"
        "        'capabilities': {},\n"
        "    },\n"
        "}\n"
        "sys.stdout.write(json.dumps(resp) + '\\n')\n"
        "sys.stdout.flush()\n"
        "for line in sys.stdin:\n"
        "    pass\n",
        encoding="utf-8",
    )
    return script


__all__ = [
    "_assert_all_commands_exist",
    "_assert_playbook_owned",
    "_cursor_hook_commands",
    "_empty_content",
    "_hook_input_set",
    "_install_for",
    "_make_hook",
    "_make_hook_with_headers",
    "_make_rule",
    "_make_skill",
    "_write_fake_mcp_config",
    "_write_fake_mcp_server",
    "_write_long_running_fake_server",
]
