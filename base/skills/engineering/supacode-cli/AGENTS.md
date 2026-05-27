# Supacode CLI

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Control Supacode from the terminal. Use when running Supacode CLI commands, managing worktrees, tabs, and surfaces programmatically, or when inside a Supacode terminal session.

## What Lives Here

- This skill's SKILL.md plus this local AGENTS.md.
- No subdirectories.

## Local Commands

```sh
TAB_ID=$(supacode tab new -i "npm start")
SPLIT_ID=$(supacode surface split -t "$TAB_ID" -s "$TAB_ID" -d v -i "npm test")
supacode surface close -t "$TAB_ID" -s "$SPLIT_ID"
supacode tab close -t "$TAB_ID"
```

Flags: `-w` (worktree), `-t` (tab), `-s` (surface), `-r` (repo), `-c` (script UUID), `-i` (input), `-d` (direction), `-n` (new ID).

## Edit Rules

- Always capture stdout when creating tabs or surfaces (UUID is on stdout).
- Always pass explicit `-t` / `-s` when targeting a created resource; env-var defaults point to your own shell only.
- For new tabs, surface ID equals tab ID.

## Required Checks

- Verify the parent skill SKILL.md still matches this local guidance after edits.

## Required Skills

- None.

## Do Not

- Call `supacode tab new` or `supacode surface split` without capturing the UUID.
- Omit `-t` / `-s` flags when targeting a created resource.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when Supacode CLI flags change.
