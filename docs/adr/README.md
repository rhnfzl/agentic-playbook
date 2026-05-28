# ADRs

**ADR stands for Architecture Decision Record.** Short documents that capture a single architectural decision plus the context that made it necessary and the consequences (good, bad, and open risks). ADRs are numbered sequentially (`ADR-0001`, `ADR-0002`, ...) and kept in the repo so future contributors can see why the architecture looks the way it does, not just what it is.

Each file in this directory follows the format `NNNN-kebab-case-slug.md` and ships four sections:

- **Status** -- Accepted / Superseded / Deprecated, plus the date.
- **Context** -- the problem the decision is solving.
- **Decision** -- what we decided.
- **Consequences** -- what is now better, what is worse, what risks are open.

## When to write one

- A choice is **hard to reverse** (rewriting the lockfile format, choosing an installer pattern, picking a hook canonical-source rule).
- A choice would be **surprising without context** (a future reader asks "why this?" and the reason is non-obvious from the code).
- A choice is **the result of a real trade-off** (there were genuine alternatives and we picked one for specific reasons).

If any of the three is missing, skip the ADR. Use a code comment or a PR description instead.

## When to NOT write one

- The decision is fully captured by the code's shape and well-named identifiers.
- The decision is reversible at any time without coordination (e.g. a one-off helper function name).
- The decision is short-term scaffolding that will go away in a few weeks.

## Numbering

ADRs are append-only. To add a new one: look at the highest-numbered file in this directory, add 1, and use that as your number. Never reuse a number, never renumber.

## Superseding

When a later ADR replaces an earlier one, set the earlier ADR's status to `Superseded by ADR-NNNN` and add a one-paragraph note pointing forward. The earlier ADR stays in the repo for the historical record.

## Full index

The list below mirrors the files in this directory in numerical order. See each file for its full status, context, decision, and consequences.

### Foundations (content shape and contract)

- ADR-0001 SKILL.md canonical (skill content type lives in `base/skills/<cat>/<name>/SKILL.md`).
- ADR-0002 Per-subproject AGENTS.md instead of monolithic.
- ADR-0003 Custom installer over `ruler`.
- ADR-0004 Drop the version-tag prefix from skill slugs.
- ADR-0005 Tier 1 / 2 / 3 agent support scheme.
- ADR-0006 Open-PR contribution model.
- ADR-0007 Three buckets: rules / skills / hooks.
- ADR-0008 Three-layer capture system (mid-session quick capture, end-of-session retrospective, periodic audit).
- ADR-0009 Unified `agents/` directory + Codex TOML conversion.
- ADR-0010 Commands and prompts as 5th and 6th content types.

### Quality and lifecycle

- ADR-0011 Tier promotion criteria (when a Tier 3 adapter graduates to Tier 2 or 1).
- ADR-0012 MCP bundle layout.
- ADR-0013 AGENTS.md governance harness.
- ADR-0014 External-source policy.
- ADR-0015 Skill size policy (warn at 500 lines, block at 1000).
- ADR-0016 Installer lifecycle (install / update / status / doctor / remove).
- ADR-0017 Eval harness pattern.
- ADR-0018 anchored-fs vendoring.
- ADR-0019 mattpocock frontend imports and sync.
- ADR-0020 Refer-only justifications (when to link rather than inline).

### Installer architecture (the Adapter Protocol)

- ADR-0021 AGENTS.md upstream contribution.
- ADR-0022 Per-project init customization.
- ADR-0023 Lifecycle ownership and anchored-fs scope.
- ADR-0024 Adapter Protocol + Install Manifest.
- ADR-0025 Profile end-to-end (per-role bundles wired through the installer).
- ADR-0026 MCP bundle lifecycle convention (`bootstrap.sh`, `health.sh`, `teardown.sh`).
- ADR-0027 AGENTS.md document type + hook event metadata.
- ADR-0028 Target materializer and unified target layout.
- ADR-0029 Hook reconciliation + matcher header.
- ADR-0030 Tier-3 declarative TOML registry.

### Three-layer contract (canonical / materialization / runtime)

- ADR-0031 Loader four-file split (`_protocol`, `_reader`, `_writer`, `_detect`).
- ADR-0032 anchored-fs bundle conformance to ADR-0026.
- ADR-0033 AGENTS.md canonical write API.
- ADR-0034 Cross-agent hook contract.
- ADR-0035 Canonical hook source unification (skill-owned vs root).
- ADR-0036 Three-layer content contract (canonical / materialization / runtime).
- ADR-0037 Generalized hook adapter scoping (`PLAYBOOK-HOOK-ADAPTERS` header).
- ADR-0038 Multi-target registry.
- ADR-0039 Per-config managed keys + lockfile_version 3 + HTTP MCP probe.

### Content tiering (`base/` vs `overlays/`)

- ADR-0040 Base / overlay subtree split for content tiering.
- ADR-0041 Content tiering guardrails (automated `scope_boundary` check).
- ADR-0042 Playbook content distribution (manifest-driven sync to a downstream mirror).
- ADR-0043 Marketplace distribution (designed in the upstream; ADR text and emitter intentionally not shipped in this public mirror per the portfolio's distribution choice).

### Trajectories (the eighth content type)

- ADR-0044 Trajectories as the eighth content type.
- ADR-0045 Trajectory trace contract (cross-adapter behavior assertions).
- ADR-0046 Trajectory DSL and hybrid match (DSL assertions + LLM-judge rubric).

### Operations (security, telemetry, atlas)

- ADR-0047 Supply-chain security gate (AI BOM, block-by-default for imported skills).
- ADR-0048 Skill telemetry privacy (opt-in OTel, metadata only, no prompt or response bodies).
- ADR-0049 Why atlas is auto-generated (knowledge-graph for ADRs + skills + trajectories).

## Cross-reference: ADR → consumer

| ADR | What it changes | Consumed by |
|---|---|---|
| 0001 | Skill format | `base/skills/`, `scripts/frontmatter_lint.py`, `scripts/checks/frontmatter.py` |
| 0008 | Capture system | `base/skills/meta/playbook-retrospective/`, `base/skills/meta/playbook-promote/`, `scripts/retrospective.py`, `scripts/promote_skill.py` |
| 0010 | Commands + prompts | `base/commands/`, `base/prompts/` |
| 0024 | Adapter Protocol | `scripts/adapters/_protocol.py`, every `scripts/adapters/<tool>.py` |
| 0025 | Profile | `profiles/`, `scripts/playbook_profile.py` |
| 0027 | Hook metadata | `scripts/hook_registration/` (package), `scripts/checks/hook_metadata.py` |
| 0034 | Cross-agent hook contract | Every adapter that exposes hook registration |
| 0036 | Three-layer contract | `scripts/install_verify.py`, `make doctor-verify` |
| 0042 | Content distribution | `scripts/sync_distribution.py`, `.sync-manifest.json` |
| 0044 | Trajectories | `base/trajectories/`, `scripts/trajectory_harness.py`, `make trajectory-check` |
| 0047 | Supply-chain gate | `scripts/security/`, `scripts/audit_security.py`, `make audit` |
| 0048 | Telemetry | `scripts/telemetry/`, `make telemetry-report` |
| 0049 | Atlas | `scripts/atlas/`, `scripts/build_atlas.py`, `make atlas`, `docs/atlas/index.html` |

## How to start reading the ADRs

For a first read, the three highest-leverage ADRs are:

1. **ADR-0036** (three-layer content contract) explains the canonical / materialization / runtime split that the installer + `make doctor-verify` are built around.
2. **ADR-0024** (Adapter Protocol) explains how every per-tool adapter implements the same `Protocol` so adding a new agent is a bounded task.
3. **ADR-0044** (trajectories) explains the eighth content type and why cross-adapter behavior assertions are checked by a harness rather than materialized into adapters.

For the security and operations story, read ADR-0047 → 0048 → 0049 in order.

The marketplace plugin story (ADR-0043) is designed in the upstream and intentionally not shipped in this public mirror; the ADR text, the emitter source, and the per-role packs all live upstream-only. For the sync model that decides which artifacts flow downstream, read ADR-0042.
