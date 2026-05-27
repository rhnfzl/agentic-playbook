---
name: promote-ticket
description: >-
  Distills a closed-ticket transient doc into permanent or reference docs, then
  deletes the transient. v0.1 is interactive: locates the transient, prints
  destination hints, and asks the user to confirm before deletion. Does not
  auto-query Jira or produce diffs (both planned for v0.2); operates on user
  confirmation.
version: 1.0.0
owner: rehan-8v
last_reviewed: 2026-05-24
---

# promote-ticket

## When to use

When a Jira ticket has been closed and a `tickets/active/<TICKET-ID>-*.md`
transient doc exists that should be distilled into durable docs (permanent
architecture or reference) and then removed.

## Invocation

```bash
python3 ~/.agents/skills/promote-ticket/__main__.py <TICKET-ID> [--root PATH]
```

## v0.1 behavior

1. Locates every file matching `tickets/active/<TICKET-ID>-*.md` across the
   workspace (root and both subprojects' `docs/tickets/active/`).
2. Prints each file's path and summary.
3. Prints distillation candidate destinations: `docs/architecture/<suggested>.md`
   and `docs/references/<suggested>.md` in the relevant subproject.
4. Prompts the user to confirm ticket is closed (type literal `yes` to proceed; any other input aborts); if not, exits without changes. Pass `--yes` for non-interactive agent invocation.
5. After user applies distillation manually, re-invoke with `--delete` to remove
   the transient docs and log a CHANGELOG entry.

Future v0.2 will call the Jira MCP tool and propose concrete diffs.
