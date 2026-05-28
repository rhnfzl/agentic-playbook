# imported/taste-skill/

Vendored from [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) (MIT). A 12-skill set covering visual taste, redesign, image-to-code, brutalist, minimalist, and other design and UI sensibilities the agent can lean on when producing visual artifacts.

## What ships here

| Skill | What it does (per upstream) |
|---|---|
| `brandkit/` | Build a brand kit (colors, typography, voice) from a brief or an existing artifact. |
| `brutalist-skill/` | Apply brutalist design sensibilities: aggressive typography, strong contrast, no decorative chrome. |
| `gpt-tasteskill/` | The general "taste check" skill: review an artifact and call out where it looks off. |
| `image-to-code-skill/` | Convert a UI mockup image into working HTML/CSS code. |
| `imagegen-frontend-mobile/` | Generate mobile-frontend design references via an image gen model. |
| `imagegen-frontend-web/` | Generate web-frontend design references via an image gen model. |
| `minimalist-skill/` | Apply minimalist design sensibilities: whitespace, restraint, one-thing-per-screen. |
| `output-skill/` | Format an output artifact for a specific design context. |
| `redesign-skill/` | Take an existing UI and redesign it for a target sensibility or audience. |
| `soft-skill/` | Apply soft design sensibilities: pastels, rounded corners, friendly tone. |
| `stitch-skill/` | Stitch multiple design artifacts together into a coherent set. |
| `taste-skill/` | The root taste skill (umbrella under which other taste skills sit). |

## Provenance

See [`PROVENANCE.md`](PROVENANCE.md) for the upstream URL, license, pin SHA, and `last_reviewed` date.

These skills are **vendored** (per ADR-0014 + ADR-0018): the playbook copies them locally.

## When to consume

- Frontend, UI, or design work where visual sensibility matters.
- Generating HTML artifacts for `docs/human-html/` where the artifact has to be presentable, not just functional.
- Working with PMs or designers who need design references quickly.

The `frontend-developer` profile includes a subset of this set.

## When to NOT consume

- Backend-only engineering. Taste skills don't help when there's no visual output.
- Production design systems where the team has a real design lead. These skills are scaffolding, not a replacement for design judgement.

## Related

- [`PROVENANCE.md`](PROVENANCE.md) for upstream attribution.
- [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) for the upstream README.
- `base/skills/productivity/frontend-slides/` for the team-authored slides-generation skill (complements imagegen-frontend-web).
