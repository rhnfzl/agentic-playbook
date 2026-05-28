# 0049. Why Atlas: auto-generated rationale graph

## Status
Accepted (2026-05-28). Ships the static-site generator, three page
kinds (ADR, skill, trajectory), an index with section anchors, and
the JSON adjacency the (future) D3 view will consume. Output lives
at `docs/atlas/` and is committed so the site is browseable on
GitHub Pages without a build step.

## Context

The playbook ships 47 ADRs (and growing) plus 109 skills plus a
trajectory corpus. The "rationale IS the value" pitch only lands if
someone can find the rationale. Reading the ADR list in
`docs/adr/README.md` is a flat hyperlink list; cross-references
between ADRs and skills are not surfaced anywhere. Competing
projects (mattpocock/skills, obra/superpowers) do not have this
problem because they do not have an ADR corpus.

Two failure modes the atlas closes:

1. **Skill discoverability**. A user landing on `base/skills/` sees
   a directory tree by category. There is no per-skill "what does
   this do, what's its usage signal, is it vetted?" view.
2. **ADR-to-skill traceability**. ADR-0044 named trajectories as the
   8th content type. Which skills exist *because* of that decision?
   The atlas surfaces this via the "ADRs mentioning this skill"
   section on each skill page.

## Decision

### Static-site generator under `scripts/atlas/`

Three modules:

- `scripts/atlas/graph_builder.py` builds the adjacency. Node kinds:
  `adr`, `skill`, `trajectory`. Edge kinds:
  - `mentions` (ADR body mentions a skill name, whole-word match)
  - `belongs_to` (trajectory in `base/trajectories/<skill>/`)
  - `supersedes` (ADR body matches `Supersedes 0NNN`)
- `scripts/atlas/template_engine.py` is the f-string template
  helper. No Jinja, no PyYAML; explicit `escape()` call site.
- `scripts/build_atlas.py` is the CLI. Renders the index plus one
  page per node plus `graph.json`.

The output structure:

```
docs/atlas/
  index.html
  adr/<NNNN>.html
  skill/<scope>-<category>-<name>.html
  trajectory/<skill>-<scenario>.html
  static/atlas.css
  graph.json
```

### Auto-generated, committed

The rendered HTML is checked in. Two reasons:

1. GitHub Pages serves it directly. A user does not need to run a
   build to browse the atlas. The README links straight to the
   GitHub Pages URL.
2. Code review can see exactly what changes when the corpus
   changes. A PR that adds an ADR shows up as a diff in
   `docs/atlas/index.html` and the new ADR page; a reviewer
   immediately sees what landed.

The trade-off: every PR that touches an ADR or skill *should* be
followed by a `make atlas` to regenerate the site. A future CI
gate can enforce that the committed `docs/atlas/` is in sync with
the latest source corpus.

### Cross-subsystem signals (the data spine)

Each skill page renders badges by reading three sibling artifacts
when present:

- `docs/security/ai-bom.json` (ADR-0047): per-source vetted-as-of
  marker. Rendered as `vetted: YYYY-MM-DD` or `vetted: unvetted`.
  Only applied to skills under `base/skills/imported/` since BOM
  entries are keyed by `imported/<source>/...` paths; first-party
  skills under `base/skills/<category>/` have no vetted-as-of
  concept and render without the security badge.
- Telemetry aggregates via `scripts/telemetry.ingest` (ADR-0048):
  trigger count and last-fired timestamp. **Atlas inverts the
  standard telemetry contract: badges render ONLY when the user
  explicitly sets `TELEMETRY=on` (or `1/true/yes/enabled`)**, not
  when `is_enabled()` would normally return True. This is a
  privacy-by-construction guard: a contributor with local telemetry
  running would otherwise silently bake personal usage signals into
  committed HTML headed to a public PR. The collector + report CLI +
  decay consumers retain the standard off-switch shape; only atlas
  flips to opt-in.
- Trajectory adjacency via the graph itself: count of trajectories
  targeting this skill, with links.

Missing signals degrade silently. The atlas does not require
security or telemetry to render; both consumers are best-effort.

### No PyYAML, no Jinja, no fetched JS

- Template engine is f-string + html.escape. Zero PyYAML calls;
  YAML frontmatter is parsed via a tiny line-based regex helper.
- D3 force-graph view is deliberately deferred. We ship
  `graph.json` so a follow-up commit (or a hand-edited atlas
  augmentation) can layer D3 on top, but the first cut ships
  index + per-page views without external JS. The atlas is
  useful as a static text tree on day one; the graph is the
  polish.

### Why not Sphinx / MkDocs / Antora / etc.

Three reasons:

1. Toolchain weight. MkDocs/Sphinx require Python+plugin trees.
   The playbook's discipline is "stdlib first."
2. ADR + skill + trajectory cross-references are unique to this
   playbook; no off-the-shelf generator knows the graph shape.
3. The output must be auditable in PR diffs. A custom generator
   produces stable, deterministic HTML we can review.

## Consequences

### Positive

- 47 ADRs become discoverable rather than a wall of filenames.
- Every skill page surfaces its rationale (which ADR justifies
  it) automatically.
- Telemetry-aware: the "which skills are actually used" question
  has a visible answer when telemetry is on.
- GitHub Pages compatible out of the box; no runtime build.

### Negative

- Every ADR/skill PR adds churn to `docs/atlas/`. We accept this
  because reviewers can see what landed in the rendered output.
- The graph builder's edge heuristics are imperfect. Whole-word
  matching can miss a skill if the ADR uses the directory name
  rather than the frontmatter `name`. A future refinement can
  add explicit cross-references in ADR frontmatter.
- D3 graph view is deferred; the first cut is text + tables.

### Reject if

- `make atlas` takes longer than 5 seconds on a typical tree
- Generated pages contain prompt content or other sensitive
  material that should not be public (the renderer reads source
  files verbatim; reviewers must audit any new content type
  before adding it to the graph)
- The committed `docs/atlas/` drifts from the source corpus more
  than once per release (would justify a CI gate that fails when
  `make atlas` produces a diff)

## References

- `docs/research/2026-05-28-tavily-enhancement-backlog.md` Idea 6
- ADR-0047 (security gate) and ADR-0048 (telemetry) define the
  badges the atlas renders.
