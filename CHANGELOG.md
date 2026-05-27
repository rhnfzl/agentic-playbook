# Changelog

All notable changes to the coding-agents-playbook. Format: lightweight markdown, one heading per release, newest at top. Steipete-inspired (per ADR-0020).

## v0.3.0 (2026-05-25)

Goal: turn the playbook from "useful skill library" into "team-shared agent operating system". Closes every recommendation from the 2026-05-25 research artifact in one PR.

### Governance harnesses

- `scripts/check_agents_md.py`: AGENTS.md coverage + 8-section template + root/sub line budgets + locality (line-overlap) + freshness (90d active / 180d docs) + conflict-control (anti-contradiction). Block-by-default.
- `scripts/audit_external_skill.py`: security audit for vendored skill content (hidden Unicode, secret reads, network exfiltration, persistence writes, unpinned downloads). Block-by-default; per-skill `.audit-allow` allowlist with reviewer signoff.
- `scripts/size_check.py`: warn at 500 lines, BLOCK at 1000. Vendored content warn-only (per ADR-0019).
- `scripts/frontmatter_lint.py`: extended with Agent Skills spec compliance (name regex + parent-dir match for non-vendored, semver, description cap 1024, license SPDX, allowed-tools known names, referenced-file existence).

### AGENTS.md coverage (now 12 files)

10 new top-level AGENTS.md files: `agents/`, `commands/`, `docs/`, `hooks/`, `mcp/`, `profiles/`, `prompts/`, `rules/`, `scripts/`, `skills/`. Root + `skills/engineering/supacode-cli/AGENTS.md` updated to the strict template.

### Skill split

- `skills/meta/graphify/SKILL.md` split from 1291 lines to 369 lines via progressive disclosure. Deep procedure moved to `references/extraction.md`, `references/exports.md`, `references/incremental.md`, `references/query-modes.md`, `references/integrations.md`. Behaviour preserved.

### Installer lifecycle

`scripts/install.py` gains:
- `--list` show installed playbook content per adapter
- `--status` compare against `.playbook-lock.json`, diff per adapter
- `--update` re-materialize + refresh lockfile
- `--remove` walk lockfile + unlink every recorded file
- `--drift` alias of `--status`
- Lockfile generated automatically on every install/update

### MCP bundles

- `mcp/anchored-fs/` vendored from `~/.config/agent-shared/mcp_servers/anchored-fs/`. Playbook is now the canonical upstream (per ADR-0018). LICENSE added (MIT).
- `hooks/agent-memory-session-brief.sh` new SessionStart companion hook (renders context from accumulated memory via the `mcp/agent-memory-bridge/` bundle).

### Vendored skills (skills/imported/)

- `skills/imported/mattpocock/` (MIT, 18 skills across engineering/productivity/misc). Pinned to `b8be62f`. `scripts/sync_mattpocock.sh` for monthly sync.
- `skills/imported/layers/` (MIT, 9 skills). Pinned to `0e5d49b`.
- `skills/imported/impeccable/` (Apache 2.0, single skill). Pinned to `84135db`.
- `skills/imported/taste-skill/` (MIT, 12 skills). Pinned to `c8075169`.

Anthropic frontend-design vendored briefly then DROPPED: prose-only design guidance, better served by MCP-connected approaches (chrome-devtools-mcp, design-system MCPs). Catalog-only.

### External-source catalog

`docs/research/external-skill-sources.md`: 17 entries across vendored + refer-only with full metadata (source / pin / license / skills / status / risk_class / reviewer / last_reviewed / notes).

### Eval harness

- `scripts/eval_runner.py` v0.3 static-mode harness (no LLM call required)
- 4 reference suites: `evals/VCS-pr-review/`, `evals/chat-transcript-debug/`, `evals/mcp-first-boundary-check/`, `evals/ci-failure-triage/`. Each with `cases.yaml` + `judge.md`. 18 cases total, all passing.

### Per-project init / customization

- `scripts/playbook_init.py`: hybrid pointer + selective install (ADR-0022)
- `scripts/playbook_update.py`: refresh pointer + bump last_reviewed
- `profiles/init/{generic,backend,frontend,data-science,custom}.yaml`: seed profile skill sets
- `make init TARGET=/path` Makefile target

### Documentation

- `TOOLS.md`: top-level CLI tool reference (steipete-style)
- `RELEASING.md`: tag / lint / push / announce flow
- `CHANGELOG.md`: this file
- 10 new ADRs (0013-0022) capturing every architectural decision

### Post-PR fixes from review rounds

After the v0.3 plan was locked, three review passes (one Codex, one Cursor, one adversarial Codex) surfaced findings that were folded into this release:

- Adapter skill copy: SKILL.md only -> SKILL.md + references/ + scripts/ (graphify usable in installed form).
- Imported skill namespacing: `imported-<source>-<name>` install slug avoids first-party collisions.
- Audit script: scan .mjs + .cjs.
- anchored-fs server: enforce `--allowed-dir` boundary in overridden edit/preview tools.
- anchored-fs default scope: `{{PLAYBOOK_TARGET}}` (resolved at install) instead of home-wide `~`. Home-wide is now an explicit opt-in.
- Lifecycle ownership model (ADR-0023): lockfile records `{sha256, ownership}` per file. `make remove` skips managed-block files and refuses to unlink user-edited owned files.
- Lockfile coverage gap closed (Cursor project paths, MCP configs, skill support dirs, Windsurf target paths, Pi prompts, codex AGENTS.md + config.toml).
- Per-project init `--force` flag works; `make status TARGET=...` passes through; `make check` runs `eval_runner`.
- Catalog pins replaced with actual SHAs; rtk-ai/rtk added.

### Counts

- Skills: 58 -> 98 (+40 vendored)
- AGENTS.md files: 2 -> 12 (+10 coverage)
- ADRs: 12 -> 23 (+11)
- Eval suites: 0 -> 4

## v0.2.1 (2026-05-24)

Foundational shape. See git history for the v0.2.1 commits (`6a4bf23` and `b70b91d`).

## v0.1.0 (initial)

Skills + rules + harness scaffolding. See `5f22f64`.
