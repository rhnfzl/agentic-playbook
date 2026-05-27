# Profiles

Owner: Rehan
last_reviewed: 2026-05-26

## Purpose

Role-based bundles that select which skills, rules, hooks, and MCPs an agent uses for a given role. Profiles are the filtering surface for the installer; categories under `skills/` are organizational.

Per the profile-separation principle (see project memory entry of the same name), each profile is single-role. Multi-role teammates compose via `make install PROFILE=a,b,c`; the installer unions includes and dedupes. Pre-authored composite profiles are intentionally not supported.

## What Lives Here

- `<role>.toml` profile files: backend-developer, frontend-developer, qa, tech-lead, product-manager, research, devops.
- `templates/` for new-profile scaffolds.
- `README.md` documents how the installer reads profiles.
- `devops.README.md` documents external-tool pointers (HashiCorp Terraform + Packer, AWS skill collections) that the DevOps profile references but does not vendor.

## Local Commands

- The installer respects `--profile <role>` to materialize only the role's items.
- `make init TARGET=/path` wires a target project to a profile.

## Edit Rules

- Profile names are kebab-case, match the typical role title.
- Each profile lists explicit skill / rule / hook / MCP keys (no globs).
- When a new skill is added to the playbook, decide whether to add it to relevant profiles or leave it user-discovered.

## Required Checks

- TOML validity: `python3 -c 'import tomllib; tomllib.load(open(sys.argv[1], "rb"))'`.
- Referenced skills, rules, hooks, MCPs must exist in their respective dirs.

## Required Skills

- None mandatory.

## Do Not

- Use profiles for ad-hoc grouping. Profiles are for portable, single-role bundles; multi-role composition happens via `make install PROFILE=a,b,c`.
- Add tool secrets or credentials to a profile.
- Require an overlay implicitly. A profile that includes overlay-only skills (under `overlays/team/skills/`) MUST declare `requires_overlays = ["team"]` (or the relevant overlay name) at the TOML root per ADR-0040. The installer validates this before materializing and rejects with a clear message if the active scope does not satisfy the requirement.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` when adding a profile or when a referenced item is renamed.
