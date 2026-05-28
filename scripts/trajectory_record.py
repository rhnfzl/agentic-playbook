#!/usr/bin/env python3
"""Trajectory recorder + draft YAML writer (Phase 2C-γ).

Closes the authoring loop. Before this script existed, authoring a
trajectory meant: spawn Claude Code manually, copy spans by hand,
write the YAML from scratch. Now:

    make record-trajectory SKILL=<name> SCENARIO=<name> PROMPT="..."

spawns Claude Code via the Phase 2B provider (with the security-
hardened tool allowlist from PR #4), saves the resulting trace as
the per-trajectory JSONL fixture (so `make trajectory-calibrate`
and `make verify-trajectory` can find it), and drafts a trajectory
YAML at `base/trajectories/<skill>/<scenario>.yaml.draft` with:

  * frontmatter pre-filled from the trace (model_pinned, adapter,
    skill, scenario, today's last_reviewed, etc.)
  * phrasing 1 = the user's actual prompt
  * phrasings 2-5 = TODO paraphrase placeholders (the lint gate
    catches TODO bodies so the author must replace them)
  * assertions seeded from the trace:
      - `first_skill_loaded: <name>` when a skill_load event appears
      - `must_invoke_tool: <name>` for every tool that fired
  * llm_judge block scaffolded with TODO rubric (caught by lint)

The author edits the draft, removes the `.draft` suffix, and runs
`make verify-trajectory SKILL=<name> SCENARIO=<name>` to confirm
the trajectory passes against the same fixture before committing.

Companion content: `base/skills/meta/trajectory-summarizer/SKILL.md`
documents the recorder workflow as a skill the agent can invoke to
help authors think through new scenarios.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable

REPO_ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT_DEFAULT / "scripts"))

from adapters.trace_record import TraceRecord  # noqa: E402


def draft_trajectory_yaml(
    skill: str,
    scenario: str,
    user_prompt: str,
    trace: TraceRecord,
) -> str:
    """Pure: produce the draft YAML body. No I/O."""
    today = date.today().isoformat()
    tool_calls = trace.tool_calls()
    seen_tools: list[str] = []
    for event in tool_calls:
        if event.name not in seen_tools:
            seen_tools.append(event.name)
    skill_loads = trace.skill_loads()
    first_skill = skill_loads[0].name if skill_loads else skill

    lines: list[str] = []
    lines.append("---")
    lines.append(f"name: {skill}/{scenario}")
    lines.append(f"description: TODO one-line description of what this trajectory verifies.")
    lines.append(f"skill: {skill}")
    lines.append(f"scenario: {scenario}")
    lines.append("version: 0.1.0")
    lines.append(f"owner: {os.environ.get('USER', 'unknown')}")
    lines.append(f"last_reviewed: {today}")
    lines.append("tags: []")
    lines.append(f"adapter_scope: [{trace.adapter}]")
    lines.append(f"model_pinned: {trace.model}")
    lines.append("authoring_mode: recorded")
    lines.append("---")
    lines.append("")
    lines.append("input:")
    lines.append("  phrasings:")
    # Quote-safe: escape backslashes and double-quotes inside the prompt.
    safe_prompt = user_prompt.replace("\\", "\\\\").replace('"', '\\"')
    lines.append(f'    - "{safe_prompt}"')
    for i in range(2, 6):
        lines.append(f'    - "TODO paraphrase {i} of the original prompt"')
    lines.append("  variant_strategy: parallel")
    lines.append("")
    lines.append("assertions:")
    lines.append(f"  - first_skill_loaded: {first_skill}")
    for tool in seen_tools:
        lines.append(f"  - must_invoke_tool: {tool}")
    lines.append("")
    lines.append("llm_judge:")
    lines.append("  threshold: 0.7")
    lines.append("  rubric: |")
    lines.append("    TODO Score the trajectory on:")
    lines.append("    1. Did the agent do the right first thing?")
    lines.append("    2. Did the agent produce the expected artifact?")
    lines.append("    3. Did the agent avoid forbidden tools?")
    lines.append("  model: claude-sonnet-4-6")
    lines.append("")
    return "\n".join(lines)


def _next_draft_path(canonical_yaml: Path) -> Path:
    """Return the next non-existing draft path for a canonical YAML.

    First call: `<scenario>.yaml.draft`.
    Subsequent calls (when `.draft` already exists): `<scenario>.yaml.draft.2`,
    `.draft.3`, etc. Avoids the silent-clobber failure mode where a
    second recording destroys the author's in-progress edits to the
    first draft. Walks linearly; the practical limit is the number of
    times an author re-records before reviewing the existing drafts.
    """
    base = canonical_yaml.with_suffix(".yaml.draft")
    if not base.exists():
        return base
    n = 2
    while True:
        candidate = canonical_yaml.with_suffix(f".yaml.draft.{n}")
        if not candidate.exists():
            return candidate
        n += 1


def save_fixture(
    repo_root: Path,
    skill: str,
    scenario: str,
    trace: TraceRecord,
) -> Path:
    """Write `<scenario>-pass.jsonl` so calibrate / verify pick it up.

    Output format mirrors what the Phase 1 `parse_otel_jsonl` shim
    expects: one OTLP-shaped span per line with `gen_ai.operation.name`
    + tool/skill attributes.
    """
    fixtures_dir = (
        repo_root / "base" / "trajectories" / skill / "fixtures"
    )
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    path = fixtures_dir / f"{scenario}-pass.jsonl"
    lines: list[str] = []
    for event in trace.events:
        span = _event_to_span(event)
        lines.append(json.dumps(span))
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _event_to_span(event) -> dict:  # type: ignore[no-untyped-def]
    """Inverse of `_span_to_event`: reconstruct a flat OTLP span dict
    from a TraceEvent so the round-trip through `parse_otel_jsonl`
    preserves the same kind + name + arguments."""
    attrs: list[dict] = []
    if event.kind == "skill_load":
        attrs.append({"key": "gen_ai.operation.name",
                      "value": {"stringValue": "skill_load"}})
        attrs.append({"key": "skill.name",
                      "value": {"stringValue": event.name}})
    elif event.kind == "tool_call":
        attrs.append({"key": "gen_ai.operation.name",
                      "value": {"stringValue": "tool_call"}})
        attrs.append({"key": "tool.name",
                      "value": {"stringValue": event.name}})
        if event.arguments:
            attrs.append({"key": "tool.arguments",
                          "value": {"stringValue": json.dumps(event.arguments)}})
    elif event.kind == "model_response":
        attrs.append({"key": "gen_ai.operation.name",
                      "value": {"stringValue": "chat"}})
        attrs.append({"key": "gen_ai.request.model",
                      "value": {"stringValue": event.name}})
    base_nano = 1_700_000_000_000_000_000 + event.seq * 1_000_000
    duration_nano = (event.duration_ms or 0) * 1_000_000
    return {
        "name": event.name,
        "startTimeUnixNano": str(base_nano),
        "endTimeUnixNano": str(base_nano + duration_nano),
        "attributes": attrs,
    }


def _trajectory_stub(skill: str, scenario: str, user_prompt: str):
    """The provider expects a Trajectory-like object with these fields.
    For recorder use, we only need a few attributes; the provider does
    not look up assertions/llm_judge during the spawn."""
    from adapters._protocol import Trajectory

    return Trajectory(
        path=Path("/tmp/recording.yaml"),
        skill=skill,
        scenario=scenario,
        frontmatter={},
        body="",
        input_phrasings=[user_prompt],
        assertions=[],
        llm_judge={},
        adapter_scope=["claude-code"],
        model_pinned="claude-opus-4-7",
    )


def main(
    skill: str | None = None,
    scenario: str | None = None,
    user_prompt: str | None = None,
    repo_root: Path | None = None,
    provider: Callable | None = None,  # type: ignore[type-arg]
) -> int:
    if skill is None or scenario is None or user_prompt is None:
        parser = argparse.ArgumentParser(
            description="Record a Claude Code session as a trajectory "
            "fixture and draft a starter YAML."
        )
        parser.add_argument("--skill", required=True)
        parser.add_argument("--scenario", required=True)
        parser.add_argument(
            "--prompt", required=True,
            help="The user prompt to send to Claude Code. Becomes "
            "phrasing #1 of the trajectory.",
        )
        args = parser.parse_args()
        skill = args.skill
        scenario = args.scenario
        user_prompt = args.prompt

    assert skill is not None and scenario is not None and user_prompt is not None

    if repo_root is None:
        repo_root = REPO_ROOT_DEFAULT

    if provider is None:
        # Default real provider; keep_workdirs=True keeps the agent's
        # output around for the author to inspect after the recording.
        from adapters.claude_code_provider import ClaudeCodeProvider

        provider = ClaudeCodeProvider(keep_workdirs=True)
    assert provider is not None  # type: ignore[unreachable]  # justification: narrows for pyright

    trajectory_stub = _trajectory_stub(skill, scenario, user_prompt)
    try:
        trace = provider(trajectory_stub, user_prompt, "claude-code")
    except (RuntimeError, TimeoutError) as exc:
        print(
            f"  error  trace_provider failed: "
            f"{type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    fixture_path = save_fixture(repo_root, skill, scenario, trace)
    yaml_text = draft_trajectory_yaml(skill, scenario, user_prompt, trace)

    # Refuse to clobber an existing trajectory; write .draft sibling.
    # Review-fold P2 #6: the .draft path was also unconditionally
    # overwritten, so a second `make record-trajectory` run silently
    # destroyed whatever the author had typed into the first .draft.
    # Now we walk a numeric suffix (.draft, .draft.2, .draft.3, ...) so
    # the author's in-progress work is preserved and the new draft
    # lands beside it for diffing.
    canonical = (
        repo_root / "base" / "trajectories" / skill / f"{scenario}.yaml"
    )
    canonical.parent.mkdir(parents=True, exist_ok=True)
    draft_path = _next_draft_path(canonical)
    draft_path.write_text(yaml_text, encoding="utf-8")

    rel_fixture = fixture_path.relative_to(repo_root)
    rel_draft = draft_path.relative_to(repo_root)
    print(f"  ok  fixture written: {rel_fixture}")
    print(f"  ok  draft trajectory: {rel_draft}")
    print()
    print("Next steps:")
    print(f"  1. Open {rel_draft} and replace every TODO marker")
    print(f"     (description, phrasings 2-5, rubric).")
    print(f"  2. Rename to .yaml when satisfied:")
    print(f"       mv {rel_draft} {canonical.relative_to(repo_root)}")
    print(
        f"  3. Verify against the fixture you just recorded:"
    )
    print(
        f"       make verify-trajectory SKILL={skill} SCENARIO={scenario} "
        f"FIXTURE={rel_fixture}"
    )
    print(
        f"  4. Run `make check` to confirm the lint gate accepts the "
        f"trajectory."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
