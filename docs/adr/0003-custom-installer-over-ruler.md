# 0003. Custom installer over Ruler CLI

## Status
Accepted (2026-05-24)

## Context

Ruler CLI (github.com/intellectronica/ruler) already does cross-tool sync from `.ruler/*.md` source files to 20+ agent native config formats, including MCP config distribution. It is MIT-licensed, OSS.

Choosing it would save ~600 lines of installer code. The team gets cross-tool sync for free.

The alternative: write our own ~1000-line installer that owns all the translation logic.

## Decision

Write our own custom installer. Do not depend on Ruler at runtime.

## Why

The playbook is foundation infrastructure for the team. Every teammate's daily workflow will depend on the installer working correctly. Three risks with adopting a third-party dependency for this layer:

1. **Abandonment risk.** Ruler is maintained by one person. If they step away, we inherit a critical dependency with no maintainer.
2. **Behavior drift.** Ruler's adapter interpretations may differ from what we want. When that happens, we either fork (which defeats the purpose) or accept their interpretation.
3. **Versioning coupling.** Ruler upgrades may require us to update our source format. Owning the engine means we control the upgrade cadence.

The cost (extra ~600 lines of Python) is worth paying for a foundation that the whole team will depend on.

## Consequences

- We own ~1000 lines of installer code: detection, dispatch, adapters per agent.
- We can borrow Ruler's adapter patterns (study the OSS code) without runtime dependency.
- We need to maintain awareness of agent config format changes (Cursor's `.cursorrules` to `.cursor/rules/*.mdc` migration, Windsurf's pre-Cognition vs post-Cognition format).

## Mitigation

- Study Ruler's source as a reference. Apply patterns where they fit. Cite Ruler in `docs/research/inspirations.md` for credit.
- Keep adapters small and focused (~100-200 lines each). Easier to update individually when a single agent's format changes.
- Document each agent's config format in `docs/tools/<agent>.md` so future contributors can see what we know about that agent's interface.

## Alternative considered: Packmind

Packmind has a heavier-weight enterprise governance model (lint/drift detection, multi-repo distribution, RBAC, SSO/SCIM). Rejected for v0.1 as overkill for a 10-engineer team. Revisit if team scales past 40 engineers or needs compliance-grade enforcement.
