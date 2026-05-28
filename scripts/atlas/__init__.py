"""Why Atlas: static site generator for ADRs, skills, and trajectories.

Walks the corpus, builds a JSON adjacency, renders one HTML page per
content unit plus an index with a D3 force graph. Output lives at
`docs/atlas/` and is committed (per ADR-0049) so the site is
browseable on GitHub Pages without a build step.

Cross-subsystem signals (read at render time, no hard dependency):

  * docs/security/ai-bom.json   (per-skill vetted-as-of badge)
  * ~/.coding-agents-playbook/telemetry/skills.jsonl (trigger count)
  * base/trajectories/*.yaml     (per-skill trajectory pass/fail)

Each signal degrades gracefully: if the file is missing or
telemetry is off, the corresponding badge renders as "n/a" or is
omitted.
"""
