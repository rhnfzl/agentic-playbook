# Documentation

Owner: Rehan
last_reviewed: 2026-05-25

## Purpose

Durable documentation: ADRs, research artifacts, human-review HTML, and external-source catalog. This is freeze-tier content: things that should not change without a record.

## What Lives Here

- `adr/` Architecture Decision Records (one per design choice).
- `human-html/` HTML artifacts for human review (plans, reviews, syntheses).
- `research/` long-form research, inspirations, failure-mode catalog, external-source catalog.
- `tools/` operational tool documentation when not fitting elsewhere.
- `templates/` doc scaffolds.

## Local Commands

- ADR scaffold: `cp docs/adr/0001-skill-md-canonical.md docs/adr/<NNNN>-<slug>.md`.
- Human HTML scaffold: `python3 ~/.agents/skills/human-html/human_html_artifacts.py new <kind> "<title>"`.

## Edit Rules

- ADRs are append-only once merged. Supersede via a new ADR that references the old one.
- HTML artifacts under `human-html/` follow the `YYYY-MM-DD-kind-slug.html` naming.
- Use the writing-style rule (plain-language product context first).

## Required Checks

- Em-dash rule applies. Run `make check` before commit.
- HTML artifacts must include the `<meta name="artifact-kind">` and `artifact-created` tags.

## Required Skills

- `/human-html` for HTML artifacts.
- `/audit-docs` for periodic doc-decay sweeps.

## Do Not

- Edit ADRs in place after merge. Write a successor ADR.
- Treat this dir as a scratch zone. Use temp files outside the repo for scratch.

## Owner And Freshness

Owner: Rehan. Refresh `last_reviewed` quarterly or when a new ADR lands.
