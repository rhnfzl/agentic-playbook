# Rules

This directory holds the playbook's always-on behavioral constraints. Each `<name>.md` is a single rule the installer distributes to every adapter's rules surface (AGENTS.md, `.cursor/rules/`, `.windsurfrules`, `.clinerules`, etc.).

## What a rule is

A rule is a directive the agent should ALWAYS or NEVER do. Different from a skill (which is a workflow the agent runs on demand). Different from a hook (which fires automatically without agent involvement). Rules describe boundaries; skills describe procedures.

Format: one rule per file, `.md`, single H1 title, plain-language body. No frontmatter requirement (rules ride as-is into adapter rule files).

## What ships in this directory

| Rule | What it constrains | Why |
|---|---|---|
| `never-push-to-develop.md` | Feature branch then PR then review then merge; never push directly to develop. | The PR is the audit trail. Direct pushes bypass review. |
| `no-em-dashes.md` | Never use the em-dash character in authored prose. | Em-dashes read as LLM tell; use commas, parentheses, separate sentences instead. |
| `no-ticket-ids-in-code.md` | Never put ticket IDs in code, comments, docstrings, or env example files. | Ticket IDs rot; PR descriptions are the right home. |
| `writing-style.md` | Lead with plain-language product context before technical detail. | Engineers, PMs, and stakeholders all read the same artifacts; plain-language framing reaches everyone. |

Workplace-specific rules (priority schemes, label policies, internal-host preferences, request-chain debugging policies, VCS-host bindings, MCP boundary discipline) are designed in the upstream and intentionally not shipped in this public mirror per ADR-0040 (base / overlay split).

## How the installer wires rules

| Adapter | Where rules land |
|---|---|
| `claude_code` | `~/AGENTS.md` (managed block) + reminder to `@~/AGENTS.md` from `~/.claude/CLAUDE.md` |
| `codex` | `~/.codex/AGENTS.md` (managed block) |
| `cursor` | `~/.cursor/rules/<name>.mdc` (one MDC file per rule, with `alwaysApply: true`) + project AGENTS.md when `--target` differs from `$HOME` |
| `windsurf` | `~/.codeium/windsurf/memories/global_rules.md` (managed block) + project `.windsurfrules` |
| `cline` | `<target>/.clinerules` (managed block) + `~/.cline/rules/playbook.md` (project doc) |
| Other Tier 2 / 3 | Concatenated into `<target>/AGENTS.md` |

All adapters use the same `<!-- coding-agents-playbook BEGIN/END -->` marker pair so hand-authored content outside the block is preserved across re-installs.

## How to add a new rule

1. Write `rules/<name>.md` with an H1 title and a plain-language body that names the WHY before the WHAT.
2. Use commas, parentheses, or separate sentences (never em-dashes; the lint will block).
3. Run `python3 scripts/check_em_dashes.py`.
4. Run `python3 scripts/test_adapters.py` (verifies the new rule renders cleanly into every adapter's rules surface).
5. PR per `CONTRIBUTING.md`.

## Quality bar

- A rule must be SINGULAR (one constraint per file). If you have two constraints, write two rule files.
- A rule must apply ALWAYS (or NEVER apply). Conditional rules ("do X when Y") are skills, not rules.
- A rule must NAME THE WHY. The body explains the reasoning so future authors can judge edge cases.
- A rule must AVOID DECAY. If a rule depends on a tool version, link to the source and note the date.

## Three layers (per ADR-0036)

A rule lives on the same three layers the hooks and skills contracts spell out. For rules the layer mechanics are simpler because each adapter ingests rules through a managed block rather than a separate registration step.

| Layer | What it is for rules | Verified by |
|---|---|---|
| 1. Canonical source | `rules/<name>.md`. Single H1, plain prose. | `make check` (the no-em-dashes + no-versions-in-readmes gates apply). |
| 2. Materialization | What the installer writes per adapter: the `coding-agents-playbook BEGIN/END` managed block inside `~/AGENTS.md` (Claude), `~/.codex/AGENTS.md` (Codex), project `AGENTS.md` (every adapter that supports it), `.cursor/rules/<name>.mdc` (Cursor), `.github/copilot-instructions.md` (Copilot), `.clinerules` (Cline), `~/.codeium/windsurf/memories/global_rules.md` (Windsurf). The lockfile records the file(s) touched. | `make status` confirms the managed block is current; surrounding hand-authored content is preserved. |
| 3. Runtime discovery | What the agent loads at session start. Most agents re-read their rules file every session, so the typical "I edited a rule" workflow is: re-run `make install` (or `make update`), open a NEW chat, and the agent picks up the change. Cursor MDC rules with `alwaysApply: true` are auto-attached; Cline reads `.clinerules` once per session; Copilot picks up `.github/copilot-instructions.md` on next conversation. | Open a new chat session after `make install`; the rule should fire on the next relevant prompt. |

### Rule not landing? Debug checklist

1. **Layer 1**: is the rule file on disk under `rules/`? Is the H1 sentence-case and free of em dashes (so `make check` passes)?
2. **Layer 2**: does the agent's rule file contain the new block? `grep "coding-agents-playbook BEGIN" ~/AGENTS.md` (or the adapter's equivalent) and confirm your rule's H1 appears between the markers.
3. **Layer 3**: did you start a new chat session? Cursor/Codex/Claude rules are read at session start, not per-prompt.
4. **Cursor MDC**: confirm `~/.cursor/rules/<name>.mdc` exists with the `alwaysApply: true` line in the frontmatter envelope.
5. **Copilot**: confirm `.github/copilot-instructions.md` contains the rule. Copilot only reads project-level config; user-level rules don't apply.

## References

- ADR-0007: three buckets (rules, skills, hooks); expanded to seven per ADR-0010.
- ADR-0010: commands + prompts as 5th and 6th content types.
- ADR-0036: three-layer content contract that this section instantiates.
- `scripts/test_adapters.py`: rule materialization roundtrip checks.
