---
name: skill-cleaner
description: Use when your installed coding-agent skill set has grown noisy (too many skills loaded per session, duplicates across sources, stale skills past their last_reviewed date) and you want to audit before pruning. Walks every skill root the playbook installs into (Claude Code, Codex, Cursor, Windsurf, Cline, Copilot, Pi) and reports unused / duplicate / stale skills with token-budget impact. Suggests first; never deletes without explicit confirmation.
version: 0.1.0
owner: rehan
last_reviewed: 2026-05-26
tags: [maintenance, skills, audit, cleanup, meta]
scope: [any]
---

# Skill cleaner

Use when your installed skill set has grown to the point that the agent's per-session prompt budget feels bloated, duplicate skills cause routing ambiguity (both mattpocock and the playbook's native engineering dir have a `diagnose` skill, etc.), or stale skills past their `last_reviewed` date are still loaded.

The audit is read-only by default. Cleanup proposals come back as a list; you decide which to delete.

## When to use

- Your `make install` skill count has grown past ~100 and session start feels slow.
- An adapter is loading both an imported and a native skill with the same name; you want to pick one.
- You are doing a quarterly skill-set review and want a baseline of what is installed where.
- You suspect a previous experiment left skills on disk that the lockfile no longer tracks.

## When NOT to use

- For one-off "remove this single skill" surgery: use the adapter's native uninstall path (`make remove` for playbook-tracked items, or manual rm for user-authored).
- For deciding whether to ADD a skill: that is a different skill (`/playbook-promote` covers the promotion path).
- During a critical session where you cannot afford a 5-minute review pause; the audit walks every skill root and produces a long-ish report.

## Procedure

### 1. Identify the skill roots to scan

The playbook installs skills into multiple roots depending on which adapters are present:

- `~/.claude/skills/` (Claude Code; SKILL.md files under category dirs)
- `~/.codex/skills/` (Codex CLI; same shape, symlinked from `~/.agents/skills/`)
- `~/.cursor/skills/` (Cursor; .mdc format)
- `~/.codeium/windsurf/skills/` (Windsurf Cascade)
- `~/.cline/skills/` (Cline)
- `~/.pi/agent/skills/` (Pi)
- `~/.agents/skills/` (cross-tool USER skill root)

Skip any root that does not exist on this machine. Surface which roots were scanned in the audit output.

### 2. Inventory each root

For each skill root that exists, walk its directory tree and collect:

- Skill name (from the SKILL.md frontmatter `name:` field).
- Source (playbook-managed via the playbook lockfile, mattpocock-vendored, pm-curated-vendored, research-curated-vendored, user-authored).
- `last_reviewed` date from frontmatter.
- Approximate token cost (rough rule: 4 chars per token; size of SKILL.md body / 4).
- Description length (SKILL.md description field is capped at 1024 chars per Codex; flag any over).

### 3. Detect duplicates

Group skills by name across all scanned roots. A name appearing in 2+ roots is a candidate duplicate.

For each duplicate, surface:

- Which roots have it.
- Whether the sources differ (playbook-native vs vendored-import vs user-authored).
- Which would win in routing if the agent loaded both (typically: longer description wins, or first-loaded wins).

Recommend: keep the one with the best-shaped description + most recent `last_reviewed`. The recommendation is a suggestion; the user decides.

### 4. Detect stale skills

A skill whose `last_reviewed` is older than 60 days is in the warn zone (per the playbook's `decay.py` check). Past 180 days it should be archived or refreshed.

Surface a stale list with: name, last_reviewed, age in days, source. Recommend: refresh the playbook-managed ones via `make update` (which bumps the lockfile entry but does not auto-bump `last_reviewed` in SKILL.md, that is a manual edit by the owner). Archive or delete user-authored skills past 180 days unless the owner reaffirms.

### 5. Detect orphan skills

A skill on disk that is NOT in the playbook lockfile AND has no clear user-authored origin is an orphan. Common cause: a prior `make install --profile X` left files, the profile was changed, and orphans linger.

For each orphan, surface: path, parent root, size, last-modified-date. Recommend: confirm with the user, then `rm -rf` the directory.

### 6. Detect over-budget skills

The playbook's `skill_description.py` check forbids descriptions over 1024 chars (Codex's schema cap). Flag any installed skill whose description exceeds that; the agent's tool-palette load may silently drop or truncate them.

### 7. Produce the report

Sections in this order:

1. Roots scanned (with skill counts).
2. Total skill count + estimated token cost.
3. Duplicates (with recommendation per duplicate).
4. Stale skills (60-180 days warn, >180 days archive).
5. Orphan skills (not in lockfile, not user-authored).
6. Over-budget skills (description > 1024 chars).
7. Recommended actions (a numbered list the user can act on item-by-item).

### 8. Pause for user direction

Print the report. Stop. Do NOT delete or modify anything without an explicit user instruction. The skill's output policy is: suggest first; edit only when the user asks.

If the user asks to act on a specific item, proceed with that one item only. After each action, re-print the affected section so the user sees the current state. Do not chain multiple deletions without re-confirming.

## Required Checks

- Every skill root scanned was checked for existence before walking; missing roots are skipped silently, not reported as errors.
- Each duplicate flagged has a recommendation explaining WHICH to keep and WHY.
- Each stale skill has its age in days (not just the date), so the user can prioritize.
- Orphan deletions wait for explicit confirmation; the skill prints the orphan + asks before any `rm`.

## Do Not

- Do not delete skills the user did not explicitly authorize. "I see five orphans, removing them now" is the wrong shape; "I see five orphans, here they are, want me to remove any?" is the right one.
- Do not modify `last_reviewed` dates on the user's behalf as part of cleanup; that field is a deliberate owner action, not a janitorial sweep.
- Do not silently fix description-length violations by truncating; flag them so the owner edits the source.
- Do not chase a vanity number ("get below 80 skills"); cleanup is opportunistic, not quota-driven.

## Related

- `meta/playbook-promote` (the inverse direction: graduating a draft INTO the playbook).
- `meta/playbook-retrospective` (the upstream: capturing skill-worthy patterns at session end).
- `scripts/checks/decay.py` (the playbook's freshness gate; this skill surfaces the same data in a cross-root view).
- `scripts/checks/skill_description.py` (the playbook's description-length gate).

## References

- ADR-0011 (tier-promotion criteria) for the quality bar a skill must meet to graduate.
- ADR-0015 (skill size policy) for the size budget this skill helps enforce.
