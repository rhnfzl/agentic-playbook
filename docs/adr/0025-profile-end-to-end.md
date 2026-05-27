# 0025. Profile end-to-end (TOML role bundles wired through install + init)

## Status

Accepted (2026-05-25); landed in v0.4 after the grill-with-docs session.

## Context

Through v0.3 Profile was a confusing concept. Three shapes coexisted with no wiring between them:

1. **TOML role bundles** at `profiles/<role>.toml` (backend-developer, frontend-developer, qa, tech-lead). Mature schema with `[skills] include = [...]`, `[rules]`, `[hooks]`, `[mcp]`. CONTEXT.md defined Profile as this shape. The installer ignored them.
2. **YAML init bundles** at `profiles/init/*.yaml` (backend, frontend, data-science, generic, custom). Lighter schema. `playbook_init.py --profile` accepted these names but did not actually read the YAML content. CONTEXT.md did not document them.
3. **`playbook_init.py --profile` flag** that took one of the YAML names and recorded it in `.playbook-config.yaml`, but never used it for any materialization.

The README at `profiles/README.md` openly stated "Profile-aware install is planned" but the wiring was never built. ADR-0022 (per-project init) sketched a hybrid pointer + selective install design that left the install side as v0.4+ deferred work.

## Decision

Profile is the TOML role bundle. Wire it end-to-end through install + init + update.

### Canonical Profile shape

`profiles/<role>.toml` is canonical. The five `profiles/init/*.yaml` files are deleted as dead drift (the YAML names did not match the TOML names; the YAML schema was thinner; CONTEXT.md never documented them).

### Profile drives both global install AND per-project init / update

- `python3 scripts/install.py --profile backend-developer` narrows the global install. The dispatcher loads `PlaybookContent` (per ADR-0024), filters it through the profile's lists, and only the narrowed content reaches the Adapters.
- `python3 scripts/playbook_init.py --target /path --profile backend-developer` records the profile name in the target's `.playbook-config.yaml` and scaffolds the pointer AGENTS.md.
- Omitting `--profile` installs everything (today's default behavior preserved).

### `install_mode` stays per-project, NOT per-Profile

`install_mode` (pointer / symlink / copy) lives in `.playbook-config.yaml`, not in the Profile TOML. A backend-developer can use `pointer` in repo A and `copy` in repo B without combinatorial Profile explosion (we don't want `backend-developer-pointer`, `backend-developer-copy`, `backend-developer-symlink` variants).

### Filtering semantics

Skills are matched by `<category>/<name>` slug (e.g. `engineering/diagnose`). Rules / hooks / MCP are matched by their slug. Agents / commands / prompts pass through filtering unchanged: the Profile constrains only the four canonical types it lists today (skills / rules / hooks / mcp).

### Module placement

Profile loader + filter live at `scripts/playbook_profile.py` (named to avoid Python's stdlib `profile` module collision).

## Consequences

- `scripts/install.py` gains `--profile <slug>`. The narrowing happens at the dispatcher seam, so Adapters don't need to know about Profile at all.
- `scripts/playbook_init.py --profile` accepts TOML basenames only (`backend-developer`, `frontend-developer`, `qa`, `tech-lead`). Default is `tech-lead` (broad coverage).
- `scripts/playbook_update.py` reads the profile name from `.playbook-config.yaml`; future PR materializes the profile's content per `install_mode`. v0.4 still ships pointer-refresh only.
- `data-science.toml` can be added later if a research-team subset becomes a real need; the four current TOML profiles cover the demonstrated audiences.
- `.playbook-config.yaml` stays YAML (it's user-editable per-project; converting to TOML is cosmetic and can wait).
- `profiles/README.md` updated to reflect the new wiring; the "Profile-aware install is planned" paragraph is now obsolete.

Verified at land: `qa` profile narrows 98 skills -> 9, 11 rules -> 8, 8 hooks -> 2.

## Rejected alternatives

- **YAML init bundles win.** Less mature schema; required updating CONTEXT.md and rewriting README files. The YAML shape was the dead drift, not the TOML shape.
- **Keep both with explicit separate purposes.** "Profile" would mean two things (role-bundle filter vs project-class scaffold) even with documentation. Confusing.
- **Bundle install_mode into the Profile.** Couples per-role intent with per-project reality. Combinatorial.
- **Per-Adapter install_mode.** Maximum flexibility, no demonstrated use case, much more complex.

## Related

- ADR-0022 (per-project init + customization): superseded in part. The "v0.4+ materialize" path is now Profile filtering through the install dispatcher.
- ADR-0024 (Adapter Protocol + InstallManifest): Profile filtering plugs into `PlaybookContent` before any Adapter sees the content.
- CONTEXT.md (Profile entry): already aligned with the TOML role-bundle shape.
- Source: 2026-05-25 grilling session captured in `docs/human-html/2026-05-25-architecture-coding-agents-playbook-architecture-opportunities.html`.
