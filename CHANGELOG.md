# Changelog

This repo is the downstream mirror of a maintainer's working playbook. Releases here track the upstream's major versions; the actual development happens upstream and flows through `scripts/sync_distribution.py` (ADR-0042).

The exact set of skills, rules, hooks, and ADRs that shipped at each upstream version is visible in the `.sync-manifest.json` at the repo root (it records the source commit SHA + scrub-rules hash for the most recent sync).

## v0.1.0 (2026-05-27)

Initial public release. Mirrors the maintainer's playbook at the v0.13 upstream version.

What this includes:

- **8 content types** end-to-end: skills, rules, hooks, MCP configs, subagents, slash commands, prompt templates, behavior trajectories (per ADR-0044).
- **Lifecycle installer** (`scripts/install.py`) supporting Claude Code, Codex CLI, Cursor IDE + CLI, Windsurf, Pi, and 20+ long-tail adapters via Tier 3.
- **Profile bundles** for 7 roles (tech-lead, backend-developer, frontend-developer, qa, research, product-manager, devops).
- **Three-layer governance**: ADR-0036 (canonical / materialization / runtime), ADR-0029 (hook reconciliation), ADR-0033 (AGENTS.md write API).
- **Capture system**: `/playbook-retrospective` + `/playbook-promote` for graduating session-time patterns into the playbook (ADR-0008).
- **Sync framework**: `scripts/sync_distribution.py` (ADR-0042) for distributing the playbook to a downstream destination via a manifest-driven scrub-and-copy.
- **CI gates**: `make check` runs 17 gates (frontmatter, AGENTS.md governance, external-skill audit, skill-security, size policy, decay, em-dashes, no-versions, skill-description length, hook metadata, hook-source unification, pyright zero, human-html allowlist, ADR uniqueness, ignored-containment, playbook-version, trajectory).
- **Test suite**: 220+ lifecycle pytest tests covering install / update / status / doctor / multi-target registry / scope resolution / content paths / governance.

This is a first public release. Expect iteration on the scrub rules (some upstream conventions are workspace-specific and the conservative scrub list will grow over the first few syncs).
