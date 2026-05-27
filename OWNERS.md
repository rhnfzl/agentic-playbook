# Owners

This file lists owners of content areas. Each content artifact (skill, rule, hook, etc.) has its own `owner:` field in frontmatter; the entry here is the fallback when an artifact's owner is unset and the maintainer needs to route a question.

| Area | Owner | GitHub |
|---|---|---|
| Repo maintainer | Rehan Fazal | [@rhnfzl](https://github.com/rhnfzl) |
| Skills (base/skills/) | Rehan Fazal | @rhnfzl |
| Rules (base/rules/) | Rehan Fazal | @rhnfzl |
| Hooks (base/hooks/) | Rehan Fazal | @rhnfzl |
| MCP configs (base/mcp/) | Rehan Fazal | @rhnfzl |
| Agents (base/agents/) | Rehan Fazal | @rhnfzl |
| Commands (base/commands/) | Rehan Fazal | @rhnfzl |
| Prompts (base/prompts/) | Rehan Fazal | @rhnfzl |
| Profiles (profiles/) | Rehan Fazal | @rhnfzl |

As the project grows, area-specific owners can be added (frontend lead for frontend skills, ops lead for hooks, etc.).

## What `owner:` means in practice

- The owner is the maintainer of last resort for that artifact.
- `last_reviewed:` decay warnings ping the owner first.
- Per `CONTRIBUTING.md`, PRs that change a skill / rule should be approved by the owner OR by a generalist reviewer (with the owner getting tagged).

## Auto-validation

The frontmatter linter (`scripts/frontmatter_lint.py`) verifies that any `owner:` value listed in skill frontmatter exists in either the Aliases table above or as a known GitHub handle. Drift here would fail `make check`.
