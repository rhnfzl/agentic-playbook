# research-curated (vendored)

Owner: rehan
last_reviewed: 2026-05-26

## Source

Curated subset of research-flavored skills from the same two upstream PM
collections that feed `skills/imported/pm-curated/`. Research is a
separate playbook profile (per the v0.10 profile-separation principle),
so its imports stay distinct: a dev who installs `--profile research`
gets only the research bundle, not the PM execution bundle.

- Upstream A: `https://github.com/phuryn/pm-skills` (MIT)
  - Pin: `f9eaa51000a65e04494aeaf90355d30f2080ebf2`
- Upstream B: `https://github.com/product-on-purpose/pm-skills` (Apache 2.0)
  - Pin: `498cad9418a7ca50d0132b93ec77e8f0d66f7166`

Vendored on: 2026-05-26

## Curated picks

The selection criteria per `SOURCES.toml`:

- Upstream research-flavored skills only (customer interviews, market
  research, segmentation, sentiment analysis). Not strategic PM, not
  delivery execution; those belong in `pm-curated`.
- Balanced across both upstreams so neither is load-bearing alone.

7 skills imported. See `SOURCES.toml` for the full list with upstream
paths.

## Local modifications

Same shape as `pm-curated`: original `name` + `description` + body
preserved; `version: 1.0.0`, `owner: rehan (vendored)`,
`last_reviewed: 2026-05-26` injected into the YAML frontmatter by the
sync script.

## Sync

Run `python3 scripts/sync_curated_skills.py` (same script that handles
`pm-curated`). The script reads each set's `SOURCES.toml` independently;
adding or removing research entries does not require touching
`pm-curated`.

## License compliance

Same as `pm-curated`: MIT + Apache 2.0 attribution is satisfied by the
upstream URL + pin citation in this file plus `SOURCES.toml`. If the
playbook ever ships these to a third party out-of-band, bundle the
upstream LICENSE + NOTICE files alongside.
