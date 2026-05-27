# mcp-first-boundary-check judge

## Scoring rubric (v0.3 static mode)

Five cases ensure the skill still encodes the canonical MCP-vs-AI-Backend split:

1. **Trigger discipline.** Skill names a when-to-use.

2. **Portable semantic check.** Skill body references how generic MCP clients (Claude Desktop, n8n, Cursor) would experience the behaviour. This is the "would a third party succeed with only MCP metadata" check.

3. **AI Backend boundary articulated.** Skill body explicitly names AI Backend so its scope is unambiguous.

4. **Avoid hidden rewrites.** Skill body uses deterministic / portable semantic / MCP-first vocabulary so reviewers know to push fixes to MCP rather than adding repair logic in AI Backend.

5. **Frontmatter completeness.**

## Future v0.4 dynamic mode

Fixture diffs to add:
- A diff that adds a keyword bag to AI Backend (should be flagged: fix MCP first)
- A diff that adds a tool schema enrichment to MCP (should pass)
- A diff that puts MCP tool names hard-coded into AI Backend (should be flagged)
- A diff that fixes approval/session state in AI Backend (should pass; that is AIB's owned space)
