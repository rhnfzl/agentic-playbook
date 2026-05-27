# Upcoming adapters, deferred from v0.2

**Status**: Tracking list (not adapters; just future-proofing notes)
**Last updated**: 2026-05-24

Per Q5 v0.2 lock, adapters for agents that are NOT currently used by a named teammate are deferred. The architecture (unified `agents/`, per-adapter pattern, frontmatter contract) makes adding them mechanical when adoption signal appears.

## Google Antigravity

**Deferred to v0.3 (or whenever a teammate first adopts it).**

- **What**: Google DeepMind's agent-first IDE. Launched Nov 18 2025. Uses Gemini 3 Pro / 3 Flash. Built-in Browser + Terminal subagents (no custom subagent surface as of March 2026).
- **Detection signal**: `~/.gemini/antigravity/` dir OR `/Applications/Antigravity.app`.
- **Tier**: Tier 2 candidate (skills + AGENTS.md). Antigravity has skills (SKILL.md format, same as Cursor/Claude/Codex). No MCP support (per April 2026 research; roadmap item). No custom subagents.
- **Skill path**: `~/.gemini/antigravity/skills/<name>/SKILL.md` (user-level) OR `.agents/skills/<name>/SKILL.md` (workspace). Antigravity docs: `.agents/skills` is the new default, `.agent/skills` still supported.
- **AGENTS.md**: project-root, standard read.
- **Estimated adapter size**: ~60 lines, modeled on the Pi adapter shape (skills only, rely on cross-tool ~/AGENTS.md / project AGENTS.md).
- **Promotion trigger**: 3+ teammates adopt per ADR-0011 criteria. OR Google ships custom subagent / MCP surfaces (which would warrant Tier 1).

## OpenAI Codex Cloud / Codex VS Code Extension

**Already partially covered.** The Codex CLI adapter ships to ~/.codex/ which the Codex VS Code extension and Codex Cloud share. No separate adapter needed unless those surfaces diverge.

## JetBrains AI Assistant (Claude Agent in JetBrains)

**Not deferred; out of v0.2 scope entirely.** JetBrains AI uses its own config surface inside `.idea/`. If team JetBrains adoption grows (currently Rehan + the maintainer both primarily terminal / Cursor CLI), evaluate a Tier 2 adapter then.

## Devin (Cognition)

**Not deferred; out of v0.2 scope.** Devin is a cloud-only agent, no local config to materialize. Cognition's local Cascade (Windsurf) is the Windsurf adapter case.

## Other AI coding assistants noted in research

These appeared in 2026 surveys but have no named team adopter:
- Replit Agent 3 (cloud-only)
- AWS Q Developer (Tier 3 entry added per Q12 v0.2)
- Continue (Tier 3 entry added per Q12)
- Tabnine (Tier 3 entry added per Q12)
- Aider (Tier 2 already)
- OpenHands (open source; standalone runtime)
- SWE-agent (Tier 3 entry added per Q12)
- Codeium proper (separate from Windsurf; Codeium-the-extension lives in VS Code)

## When to convert a Tier 3 detection into a Tier 2 adapter

When the agent has a distinct skill / rule / MCP surface beyond AGENTS.md. Per ADR-0011 promotion criteria:
1. At least one teammate uses the agent regularly.
2. The agent's distinct surface adds value beyond AGENTS.md alone.
3. Someone commits to maintenance (OWNERS.md entry).

Open a PR that:
- Demotes the Tier 3 entry (removes detection from install.py AGENTS dict at Tier 3 level).
- Creates `scripts/adapters/<agent>.py` modeled on the most similar existing adapter (Pi for skills-only, Cursor for full-surface).
- Registers as Tier 2 in install.py.
- Adds smoke tests in test_adapters.py.
- Updates docs/tools/<agent>.md (or creates it).

## How this list stays accurate

This doc is reviewed during the quarterly /audit-docs sweep (per existing playbook practice). When an entry becomes a real adapter (or is rejected as "we will not support"), the entry moves to ADR form or gets deleted with a note in the PR description.
