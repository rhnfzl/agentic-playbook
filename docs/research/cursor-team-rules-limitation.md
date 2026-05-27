# Cursor Team Rules dashboard, won't-fix limitation

**Status**: Won't-fix (per Q13 v0.2 lock)
**Last verified**: 2026-05-24 via Cursor forum search

## What is the Cursor Team Rules dashboard?

Cursor's Business plan ($40/user/mo) and Enterprise plan ship an admin dashboard at cursor.com/settings that lets organization admins set team-wide rules, commands, and chats. These are distinct from project-level `.cursor/rules/*.mdc` files (which any developer can author) and from user-level `~/.cursor/rules/` (which our v0.2 adapter writes).

Team Rules apply globally to all members of a Cursor team and override / merge with project-level and user-level rules.

## The limitation

**There is no API or CLI path for setting Team Rules programmatically.**

Confirmed:
- August 2025 forum thread (forum.cursor.com/t/api-access-to-set-team-rules/149383): user requests API access. Cursor team response: not available.
- May 11 2026 forum thread (forum.cursor.com/t/apis-for-provisioning-mcp-rules-and-commands): user re-requests API access for Team Rules, MCP, and Commands. Still not available as of that date.

The only way to set Team Rules is via the cursor.com admin UI.

## What the playbook does instead

For Cursor users, our v0.2 adapter ships:

- **User-level rules**: `~/.cursor/rules/<name>.mdc` (always-on for that user). Replaces what Team Rules would have given a single user.
- **Project-level rules**: `<target>/.cursor/rules/<name>.mdc` if `--target` was passed (always-on for anyone working in that project).
- **AGENTS.md** at project root (when target != $HOME) which Cursor reads natively.

This covers every Cursor user surface EXCEPT the admin dashboard's organization-wide enforcement.

## Why won't-fix

- The Cursor team has been asked twice (Aug 2025, May 2026) and has not shipped the API. Building speculative workarounds (e.g., screen-scraping the admin UI, automating cursor.com via Playwright) violates the playbook's "no speculative infrastructure" discipline.
- For team specifically, the current Cursor team size doesn't justify Enterprise plan adoption (which is the prerequisite for Team Rules dashboard access).
- User-level rules from our adapter already give every individual developer the right rules; the playbook quality gate (one team-shared repo, PR-reviewed rules) is enforced upstream of distribution.

## Revisit if

- Cursor ships a Team Rules API or CLI. Likely signal: forum.cursor.com thread with Cursor team confirmation, OR a release announcement on cursor.com/changelog.
- team grows to a size where central Team Rules enforcement (versus per-developer install) becomes a real concern.
- A 3rd-party tool (e.g., the "AgentMD" forum thread from April 2026) provides a stable Team Rules sync API the playbook can leverage.

## How a future adapter would work

When the API exists, the Cursor adapter would gain:

```python
def install(repo_root: Path) -> None:
    # existing user-level + project-level writes
    ...
    # NEW: Team Rules sync (if CURSOR_TEAM_API_TOKEN env var set)
    if os.environ.get("CURSOR_TEAM_API_TOKEN"):
        _sync_team_rules(repo_root)
```

This stays opt-in (env var) so the existing install paths don't break.
