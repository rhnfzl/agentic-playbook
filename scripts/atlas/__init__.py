"""Why Atlas: static site generator for ADRs, skills, and trajectories.

Walks the corpus, builds a JSON adjacency, renders one HTML page per
content unit plus an index. Output lives at `docs/atlas/` and is
committed (per ADR-0049) so the site is browseable on GitHub Pages
without a build step. The JSON adjacency is emitted so a future
graph-view (D3 or otherwise) can layer on top; the first cut ships
index + per-page text views only.

Cross-subsystem signals (read at render time, no hard dependency):

  * docs/security/ai-bom.json   (per-skill vetted-as-of badge for
                                  base/skills/imported/ skills only)
  * ~/.coding-agents-playbook/telemetry/skills.jsonl (trigger count;
                                  requires explicit TELEMETRY=on)
  * base/trajectories/*.yaml     (count + links to trajectories that
                                  target each skill)

Each signal degrades gracefully: missing file or missing opt-in
omits the corresponding badge.
"""
