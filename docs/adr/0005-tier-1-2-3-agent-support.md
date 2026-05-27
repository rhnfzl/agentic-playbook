# 0005. Tier 1 / Tier 2 / Tier 3 agent support

## Status
Accepted (2026-05-24)

## Context

The coding-agent ecosystem in mid-2026 has 28+ tools that consume agent rules and skills. Supporting all of them with full per-agent adapters would require ~3000-5000 lines of code. Supporting only the 4 most-used by the team is simpler but contradicts the "support as many as possible" intent.

A key structural fact: as of mid-2026, AGENTS.md is read natively by ~20 tools (Claude Code, Codex, Cursor, Windsurf, Copilot, Gemini CLI, Aider, Cline, Kiro, Goose, Junie, Roo Code, Kilo Code, OpenCode, Zed, Amp, Augment, Tabnine, Continue.dev, plus more emerging). For those, generating an AGENTS.md is enough.

## Decision

Tier the agent support by adapter depth:

- **Tier 1 (full adapter)**, skills + rules + hooks + MCP. ~150-200 lines per agent. Currently: Claude Code, Codex, Cursor, Windsurf.
- **Tier 2 (skills + rules)**, drop hooks and MCP. ~80-100 lines per agent. Currently: GitHub Copilot, Gemini CLI, Aider, Cline.
- **Tier 3 (AGENTS.md only)**, generated free by the AGENTS.md generator. ~20 agents. No per-agent code.

## Consequences

- Total custom code: ~1000 lines for 8+ agents. ~20 more agents work for free via AGENTS.md.
- Tier 1 agents get the richest experience (auto-triggered skills, hook automation, MCP server registration).
- Tier 2 agents get the same rules but no auto-triggered skills (they have to be referenced manually).
- Tier 3 agents get only the rules via AGENTS.md. No skill-discovery; teammates must mention skill names in chat.

## Why this is the right shape

- Maximum coverage at minimum cost (the user's stated intent).
- Tiers reflect actual capability: Cursor/Windsurf can't run skills the same way Claude Code does, so Tier 1 for them is "richest available," not "Claude-Code-parity."
- Promotion path: if a Tier 2 agent becomes more popular at team and we want richer integration, we promote to Tier 1 by adding the missing adapter logic.

## Promotion criteria

Promote an agent from Tier 3 to Tier 2 when:
- It is the primary editor for at least 1 teammate, OR
- The agent itself has added native skill support that we want to leverage.

Promote from Tier 2 to Tier 1 when:
- The team relies on agent-side hooks (lint guard, sonar advisory) being active in that agent, OR
- The agent's native MCP support is significantly different from AGENTS.md-only access.

## Source

- See `docs/research/2026-05-24-research-brief-v2.md` ("Comprehensive Agent Landscape") for the full 28-agent inventory with primary-source config format confirmations.
