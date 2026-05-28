# research/

Discovery and analysis: data profiling, literature synthesis, RAG evaluation, hypothesis design, statistical analysis, notebook-to-production. Skills here help the coding agent do the rigor work that supports product, ML, and research decisions.

## What ships here

| Skill | What it does |
|---|---|
| `agent-repo-briefing/` | Brief a new repo to a coding agent so the next session can act on it without re-discovering structure. |
| `data-profiling/` | Profile a new dataset (shape, schema, distributions, NULL behavior, outliers) before any modeling. |
| `hypothesis-design/` | Convert a vague product question into a testable hypothesis with named confounds and a stopping rule. |
| `literature-synthesis/` | Walk a topic's literature and produce a structured synthesis with citations + open questions. |
| `notebook-to-production/` | Migrate a one-off Jupyter notebook into a production-shaped Python module with tests and a CI gate. |
| `rag-eval-method/` | Evaluate a RAG (retrieval-augmented generation) pipeline with deterministic retrieval metrics + LLM-judged generation quality. |
| `statistical-analysis/` | Run a structured statistical analysis (t-test, ANOVA, regression) with explicit assumptions and effect-size reporting. |

## Schema and authoring

Per `base/skills/README.md`. Research skills tend to ship with explicit assumption-and-confound sections because the discipline depends on naming what could go wrong before the analysis runs.

## When to add a research skill

- The workflow involves evidence (data, papers, interviews, observed behavior).
- The workflow produces a structured artifact (data profile, lit review, RAG eval, hypothesis doc).
- The workflow has a deterministic methodology that's easy to skip when in a hurry.

For PM-flavored research (user personas, competitor analysis, market sizing), check `base/skills/imported/research-curated/` first; that set covers most PM-adjacent research workflows.

## Related

- `base/skills/imported/research-curated/` for the upstream-vendored PM research skills.
- `base/skills/imported/pm-curated/` for the broader PM execution skill bundle (some overlap; profiles split the two).
- `base/skills/README.md` for the skill format and category contract.
- `profiles/research.toml` for the role profile that filters this category to the research bundle.
