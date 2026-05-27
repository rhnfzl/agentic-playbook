# Subagents

This directory holds subagent definitions. Each `.md` file declares ONE specialized AI assistant that runs with its OWN context window, invoked by name (`@<name>` in Claude Code, `/<name>` in Cursor, or `--agent <name>` in Codex).

## What a subagent is (and is not)

A subagent is a bounded specialist role you can delegate work to. Think: "code reviewer with no permission to write", "data explorer that profiles new CSVs", "literature synthesizer that fetches and summarizes papers."

Different from skills: a skill is a workflow YOU follow (with the agent helping). A subagent is a worker the agent DELEGATES to in a fresh context window.

Different from rules: a rule is an always-on constraint (no em dashes, never push develop). A subagent is invoked only when relevant.

## Schema (locked per ADR-0009)

Every subagent file follows this shape:

```yaml
---
name: data-explorer
description: Use when the user wants to profile a new dataset before any modeling.
model: claude-opus-4-7         # optional; adapter may override
tools: [bash, read, edit, grep] # optional; honored by Cursor + Claude, dropped for Codex
---

# Body
Markdown body. Becomes the system prompt for Cursor + Claude Code subagents.
Becomes `developer_instructions` (triple-quoted) for Codex per ADR-0009.

## When to invoke
Concrete trigger phrases or contexts.

## Workflow
Step-by-step procedure the subagent should follow.

## What to return
The output shape and stopping condition.
```

Required: `name`, `description`. Everything else is optional.

## How the installer materializes subagents

| Adapter | Output path | Conversion |
|---|---|---|
| `cursor` | `~/.cursor/agents/<name>.md` (and project dup if `--target`) | Verbatim copy |
| `claude_code` | `~/.claude/agents/<name>.md` | Verbatim copy |
| `codex` | `~/.codex/agents/<name>.toml` | `_loader.agent_to_toml`: frontmatter -> TOML keys, body -> `developer_instructions = '''...'''` (literal triple-quote so backslash sequences like regex patterns survive) |
| `windsurf`, `pi`, `agents_md` (Tier 3) | Skipped | No native subagent surface |

The TOML conversion uses LITERAL strings so backslash sequences in regex / escape codes survive. If a body contains `'''`, the converter falls back to basic strings with backslashes escaped.

## What ships in this directory

| File | Role |
|---|---|
| `agentic-scenario-auditor.md` | Audits AI Backend / MCP scenario failures |
| `VCS-pr-investigator.md` | Investigates VCS PRs (read-only) |
| `docs-harness-validator.md` | Validates documentation harnesses (research, drafts, ADRs) |
| `homelab-drift-auditor.md` | Audits homelab config drift |
| `literature-synthesizer.md` | Fetches + summarizes papers on a topic |
| `r8-cross-checker.md` | Looks up related R8/MATCH Jira tickets before authoring new ones |
| `rag-evaluator.md` | Runs RAG retrieval evaluation autonomously |
| `second-eye-reviewer.md` | Independent code review pass (Sonnet, read-only) |
| `second-eye-reviewer-codex.md` | Independent code review pass via Codex `gpt-5.5` at `xhigh` reasoning (read-only, deeper + slower than the Sonnet variant) |

## How to add a new subagent

1. Decide: does this fit the subagent shape (specialized role + own context window + invoked by name)? If it's a workflow you drive yourself, write a skill instead.
2. Create `base/agents/<slug>.md` (or `overlays/team/agents/<slug>.md` for team-specific agents per ADR-0040) with the frontmatter + body per the schema above.
3. Be specific in the description: "Use when the user pastes a paper URL and asks for a comparison vs prior work" beats "Use for papers."
4. Run `make check` and `make test` (smoke tests will load the new agent and round-trip it through TOML to confirm Codex compatibility).
5. PR per `CONTRIBUTING.md`.

## Quality bar (per CONTRIBUTING.md + ADR-0011)

- The role must be bounded. "General coding helper" is the wrong shape; "PR review with no write permission" is right.
- The body must explain WHEN the subagent should fire and WHAT it should return. Without those, the parent agent has no contract.
- Backslash sequences (regex, escape codes) are safe in the body thanks to the TOML literal-string conversion in `_loader.agent_to_toml`.

## References

- ADR-0009: unified `agents/` directory + Codex TOML conversion
- ADR-0007: skills vs rules vs subagents (the 3-bucket distinction)
- `scripts/adapters/_loader.py` for `Agent` schema + `agent_to_toml` implementation
