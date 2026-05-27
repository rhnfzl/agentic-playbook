# 0022. Per-project init + customization (hybrid pointer + selective install)

## Status

Accepted (2026-05-25)

## Context

Until v0.3 the playbook had two modes: clone-and-use (run agents inside the playbook directory) or `make install` (materialize into adapter home dirs globally). Neither answered the common ask: "I have an unrelated project; how do I bring the playbook into it without polluting either side?"

Research (Tavily) surfaced three precedents:

1. **steipete pointer pattern.** Target project's AGENTS.md says `READ ~/Projects/agent-scripts/AGENTS.md BEFORE ANYTHING`. Lightest setup; no install into target.
2. **MSicc Skills Central + project-skill-installer.** Symlink or copy selected skills from central repo into the target's `skills/` tree.
3. **Aspire `aspire agent init`.** Detect target language/framework/adapter, prompt for skill subset, install into target's adapter dirs.

Each alone leaves gaps. The pointer pattern preserves a single source of truth but offers no per-project customization. The selective install captures customization but loses the link back to upstream. The Aspire init is rich but assumes one framework.

## Decision

Hybrid: pointer + selective install + project config.

### `scripts/playbook_init.py --target <dir>`

Detects:
- Language (pyproject.toml / package.json / go.mod / Cargo.toml / Gemfile / build.gradle / pom.xml)
- Adapter in use (.claude / .codex / .cursor / .windsurfrules / .github/copilot-instructions.md)
- Existing AGENTS.md (refuses to overwrite without `--force`)

Prompts for (or accepts flags):
- `--profile {frontend,backend,data-science,generic,custom}`
- `--install-mode {pointer,symlink,copy}` (default: pointer)

Generates:
- `target/AGENTS.md` = steipete-style pointer (`READ /path/to/playbook/AGENTS.md BEFORE ANYTHING`) plus the strict 8-section template (Owner: TBD, Last reviewed: today, profile annotation) so the project owner fills in the rest.
- `target/.playbook-config.yaml` records version, profile, install_mode, detected language, detected adapters.

### `scripts/playbook_update.py --target <dir>`

Reads `.playbook-config.yaml` and re-applies:

- v0.3: pointer-refresh only (keeps `READ <playbook>/AGENTS.md` pointing at current playbook root; bumps last_reviewed)
- v0.4+: materialize the profile's skill set per install_mode

### `profiles/init/<profile>.yaml`

Seed profile skill sets:
- `generic.yaml`: diagnose, triage, audit-docs, handoff + no-em-dashes, writing-style rules
- `backend.yaml`: diagnose, tdd, triage, sonar-pr-gate, improve-codebase-architecture + no-em-dashes, writing-style, mcp-first-boundary rules
- `frontend.yaml`: imported/layers/layers-intro, layers-product-strategy, impeccable, taste-skill, redesign-skill + no-em-dashes, writing-style
- `data-science.yaml`: data-profiling, hypothesis-design, notebook-to-production, statistical-analysis + no-em-dashes, writing-style
- `custom.yaml`: empty defaults; user fills in

### Makefile

`make init TARGET=/path` invokes `playbook_init.py`. `make update` works on the global install (per ADR-0016); per-project update is `python3 scripts/playbook_update.py --target /path` directly (no Makefile shortcut to avoid TARGET ambiguity with global update).

## Consequences

- New project setup is one command: `python3 scripts/playbook_init.py --target ~/my-project --profile backend`.
- Project AGENTS.md stays project-specific (owner, local commands, local rules) while inheriting global rules via the pointer.
- `.playbook-config.yaml` keeps the customization in the target's git, so future teammates clone and see the choice.
- Future v0.4+ work: implement the symlink/copy materialization paths in `playbook_update.py`.

## Related

- v0.3 plan: scope row 14
- Aspire `aspire agent init`: https://aspire.dev/get-started/ai-coding-agents
- MSicc Skills Central pattern (referenced in v0.3 plan)
- steipete pointer pattern (referenced in v0.3 plan)
