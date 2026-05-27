---
name: notebook-to-production
description: Use when the user wants to convert an exploratory Jupyter notebook into a structured, reproducible project (data/, src/, notebooks/, reports/) with functions, tests, and a clean dependency manifest.
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, productionize, refactor, reproducibility, jupyter]
scope: [research]
---

# Notebook to Production

What this gets you: an exploratory notebook lifted into a project structure a teammate can actually rerun. Constants extracted, cell logic moved into functions in `src/`, tests added for the load and transform paths, dependencies pinned, and a thin orchestration notebook left behind that imports from the package instead of redefining everything inline.

The goal is not to delete the notebook. The goal is to make the notebook a thin script that consumes a tested library, so the work survives the next time someone reruns it on a different dataset or different machine.

## When NOT to use this skill

- The notebook is genuinely throwaway exploration that nobody will revisit. Skip the productionization tax.
- The notebook is already structured (imports from a package, no inline constants, no copy-pasted cells). Just add tests if missing.
- The user wants a research-grade web app or a deployed model service. Productionizing to "scripted package" is step one, but the user will need additional infra (Docker, CI, model serving). This skill stops at the package boundary.
- The notebook is less than 50 lines. Refactoring a tiny notebook adds more friction than the structure removes.

## Inputs you need from the user

Confirm in one exchange:

1. **Path to the notebook**.
2. **Target project directory** (new or existing). If new, propose a cookiecutter-data-science style layout (see Step 1).
3. **Python version** (default 3.11).
4. **Dependency manager** (uv, poetry, pip + requirements.txt). Default to uv if the project has none.
5. **Will the notebook stay as a notebook**, or get converted to a script (`.py` via `jupytext` or `nbconvert`)? Default: keep as a notebook, just thin it out.

## Workflow

### Step 1: Establish the target layout

If the project does not exist, scaffold using the cookiecutter-data-science V2 layout (the de facto standard for research projects). Minimal version:

```
my-project/
  data/
    raw/           # immutable original data
    interim/       # data in transition
    processed/     # final, canonical data for modeling
    external/      # third-party reference data
  notebooks/
    1.0-initial-exploration.ipynb
  reports/
    figures/
  src/
    my_project/
      __init__.py
      data.py
      features.py
      models.py
      utils.py
  tests/
    test_data.py
    test_features.py
  pyproject.toml
  README.md
  .gitignore
```

If the project already exists, slot into whatever layout it has. Do not impose a layout the team has already rejected.

### Step 2: Read the notebook end to end

Open the notebook, read every cell, and tag each cell with one of:

- **load**: reads data from disk or an API.
- **clean**: transforms a dataframe (renames, type fixes, filters).
- **feature**: derives new columns.
- **model**: fits or predicts.
- **eval**: computes metrics on model output.
- **viz**: produces a plot.
- **scratch**: print / display / debug cells that should not survive.

Cells often combine concerns (a load cell that also renames columns). Note the split; the refactor will untangle them.

### Step 3: Extract constants

Find every literal in the notebook that has meaning:

- File paths (`"/data/raw/customers.csv"`).
- Numeric thresholds (`if score > 0.5`).
- Date ranges (`"2024-01-01"`).
- Model hyperparameters (`learning_rate=0.001`).
- Column lists (`["age", "income", "score"]`).

Lift them to the top of the notebook (and later, to a `config.py` or `pyproject.toml` section). The rule: if changing a literal would change a model output, it is a constant worth naming.

Anti-pattern: leaving `0.5` buried in the middle of a cell so the next person has to grep to find it.

### Step 4: Move logic into functions

For each non-trivial cell, refactor to a function with a clear input and output. Move the function to the appropriate file in `src/<package>/`:

```python
# src/my_project/data.py
import pandas as pd
from pathlib import Path

def load_customers(path: Path) -> pd.DataFrame:
    """Load the raw customer extract.

    Drops the columns marked as deprecated in the upstream schema (v3).
    """
    df = pd.read_csv(path, low_memory=False)
    return df.drop(columns=["legacy_segment_v2"], errors="ignore")
```

Rules:

- One function per cell, unless cells are tightly coupled (then group them).
- Type hints on the inputs and the return. They are documentation that the IDE enforces.
- Docstring on every public function (the one-liner is enough for utilities; longer for non-obvious transforms).
- No global state. If the function needs configuration, take it as a parameter.

Then the notebook cell becomes:

```python
from my_project.data import load_customers
df = load_customers(RAW_DATA_PATH / "customers.csv")
```

### Step 5: Add tests for the load and transform paths

For each function in `data.py` and `features.py`, write at least one test in `tests/`:

```python
# tests/test_data.py
import pandas as pd
from my_project.data import load_customers

def test_load_customers_drops_legacy_column(tmp_path):
    csv = tmp_path / "in.csv"
    csv.write_text("id,name,legacy_segment_v2\n1,Alice,old\n")
    df = load_customers(csv)
    assert "legacy_segment_v2" not in df.columns
    assert df.shape == (1, 2)
```

You do not need 100% coverage. You need enough tests that a future change accidentally breaks a test rather than silently changes a number in a report. Prioritize:

- Load functions (catches schema drift).
- Cleaning functions (catches subtle dtype regressions).
- Feature functions (catches accidental dropped rows or wrong joins).

Skip testing visualization functions and model fits; both are too expensive to test cleanly. Test their inputs and their outputs instead.

### Step 6: Pin dependencies

Capture the working environment so the next person can reproduce it. With uv:

```bash
uv init                 # if pyproject.toml does not exist
uv add pandas scikit-learn matplotlib pyarrow
uv add --dev pytest ruff
uv lock                 # produces uv.lock
```

The lock file is the contract. Commit it. Without a lock file, "it worked on my machine" is the most common research-project failure mode.

If the existing notebook uses `!pip install pandas==2.1.0` cells, lift those versions into the pyproject.toml and delete the install cells.

### Step 7: Reorganize the notebook

After extraction, the notebook should be thin:

```python
# notebooks/1.0-initial-exploration.ipynb

# Cell 1: setup
import pandas as pd
from my_project.data import load_customers
from my_project.features import build_features
from my_project.models import fit_baseline
from my_project.config import RAW_DATA_PATH, FEATURES, TARGET

# Cell 2: load
df = load_customers(RAW_DATA_PATH / "customers.csv")
df.head()

# Cell 3: features
df_feat = build_features(df)
df_feat[FEATURES].describe()

# Cell 4: model
model, metrics = fit_baseline(df_feat, FEATURES, TARGET)
print(metrics)
```

If a notebook cell is more than 30 lines, it probably wants to be a function. Apply the rule iteratively until the notebook reads like a story (load, transform, fit, evaluate, look) and the logic lives in `src/`.

### Step 8: Add a README and a make target

A new contributor needs three commands to be productive:

```markdown
# my-project

## Setup
```bash
uv sync
```

## Run the exploratory notebook
```bash
uv run jupyter notebook notebooks/1.0-initial-exploration.ipynb
```

## Run the tests
```bash
uv run pytest
```

## Project layout
- data/: data files (raw is immutable, never edit by hand)
- notebooks/: exploration and analysis notebooks
- src/my_project/: importable library code
- reports/: figures and writeups
```

If the project will run on a schedule or as a pipeline, add a `Makefile` or a `dvc.yaml` so the chain `raw -> processed -> features -> model -> report` is reproducible end to end.

### Step 9: Lint and format

Run the linter and formatter on the new code:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

Add the pre-commit config so future commits stay clean:

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.6.0
    hooks:
      - id: ruff
      - id: ruff-format
```

### Step 10: Commit in slices

Do not commit the whole refactor as one giant change. Slice it:

1. Add the project skeleton (pyproject, src/, tests/, README).
2. Lift constants. (Notebook unchanged in behavior.)
3. Extract one function group at a time (data, then features, then models).
4. Add tests for each function group as it lands.

Each commit should leave the notebook runnable. If a commit breaks the notebook, you cannot bisect later when the model drifts.

## Common pitfalls

- **Notebook globals**: cells that depend on a variable defined three cells up. Refactor the producer and consumer together.
- **Mutable defaults**: a function with `def f(df, cols=[])` will leak state across calls. Use `None` and create inside.
- **Implicit IO order**: a cell that writes to disk and a cell that reads from disk are coupled even if they look independent. Capture the IO contract in a docstring.
- **Random seeds**: notebooks often rerun with different seeds and silently change numbers. Pin seeds in a `set_seed()` call at the top.
- **Magic numbers in plots**: figure size, color, title. These are fine to leave in the viz cell as long as they do not affect model output.

## Output shape

A new or restructured project directory plus a chat reply listing:

- The files added (and why).
- The functions extracted (and which cell each came from).
- The tests added (and what behavior each covers).
- The next refactor candidate the user should tackle in the next pass.

If the notebook is large (greater than 30 cells), do this in multiple sessions. Stage one: skeleton plus constants. Stage two: extract load and clean. Stage three: extract features and model. Each stage leaves the notebook runnable.

## Sources

- DrivenData, "Cookiecutter Data Science V2" (2024), https://drivendata.co/blog/ccds-v2
- Cookiecutter Data Science docs, https://cookiecutter-data-science.drivendata.org
- General prior art: the Joel Test for notebooks (Joel Grus, "I Don't Like Notebooks" talk and follow-up writing on reproducibility)

## Pre-flight checklist

Before lifting a notebook into a project structure, confirm:

1. **The notebook will be revisited.** A one-off analysis that nobody will rerun does not need productionizing. The refactor costs an hour or two; spend it only if the notebook will earn it back.
2. **The notebook runs end-to-end today.** Refactoring a broken notebook is harder than fixing it first. Run all cells in order on a fresh kernel; if anything errors, fix it before the refactor starts.
3. **The user has agreed on the target layout.** The cookiecutter-data-science layout is the default, but team conventions vary. Confirm before scaffolding.
4. **The dataset is accessible to the user, not just the notebook author.** Refactoring is pointless if the new code cannot find the data. Check that paths are configurable (env vars or config), not hard-coded to one machine.
5. **The user wants tests.** Some teams want the refactor without the test layer because they have their own. Confirm and skip Step 5 if so.

If any answer is "no" or "not sure", surface and resolve before starting. Mid-refactor course corrections are painful.

## Second worked example: an ML training notebook with pipeline stages

The first walkthrough assumed a simple notebook (load -> features -> model). Here is the harder case: an ML training notebook that already has multiple stages (download, preprocess, feature engineering, model training, evaluation, plotting), each spanning many cells. The challenge is not extracting one function; it is decomposing into the right modules.

Scenario: a colleague has been iterating on `notebooks/2026-05-train-classifier.ipynb`. It is 80 cells, runs for 4 hours end-to-end, and produces a saved model artifact plus three figures. They want it productionized so the team can rerun it on the next data refresh.

Phase A: read the notebook and tag every cell with its stage. The tagging matters because the refactor groups by stage.

```
cells 1-5:    setup (imports, constants, env vars)
cells 6-12:   download (S3 boto3 calls)
cells 13-22:  preprocess (parse, clean, filter)
cells 23-35:  features (categorical encoding, scaling, interaction terms)
cells 36-45:  model (CatBoost train + hyperparameter sweep)
cells 47-55:  evaluation (metrics on held-out set)
cells 56-65:  plotting (3 figures)
cells 66-80:  scratch (debugging, experiments not used)
```

Phase B: decide which stages become which modules. For this notebook:

- `src/myproj/data.py`: download + preprocess (the two stages are coupled, the download produces raw files that preprocess consumes)
- `src/myproj/features.py`: features
- `src/myproj/models.py`: model training + hyperparameter sweep
- `src/myproj/evaluation.py`: metrics
- `src/myproj/plotting.py`: figures

Five modules is the right granularity for an 80-cell notebook. Fewer modules and the files get too long; more and the imports get noisy.

Phase C: lift the constants. The notebook has paths (`"/data/raw/transactions.parquet"`), thresholds (`MIN_TRANSACTIONS = 5`), date ranges (`"2024-01-01"`), hyperparameters (`LEARNING_RATE = 0.05`). Hoist all of them into a `config.py` or a `pyproject.toml` section. Group them by stage (data paths together, model params together) for readability.

Phase D: extract one stage at a time, in dependency order. Start with `data.py` because everything else depends on it. For each function:

```python
# src/myproj/data.py
import boto3
import pandas as pd
from pathlib import Path

def download_transactions(bucket: str, key: str, dest: Path) -> Path:
    """Download the transactions parquet from S3 to a local path."""
    s3 = boto3.client("s3")
    s3.download_file(bucket, key, str(dest))
    return dest

def preprocess_transactions(raw_path: Path, min_transactions: int = 5) -> pd.DataFrame:
    """Load raw transactions, drop accounts with too few records."""
    df = pd.read_parquet(raw_path)
    counts = df.groupby("account_id").size()
    keep = counts[counts >= min_transactions].index
    return df[df["account_id"].isin(keep)].copy()
```

Test each function as it lands. Then move to `features.py`, then `models.py`, etc. The notebook stays runnable throughout because each cell either still has the old logic or now imports the new function.

Phase E: the model training stage is the trickiest. CatBoost training has heavy state (the trained model, the training history, the feature importances). Wrap the entire training run in a function that returns a `TrainResult` dataclass:

```python
# src/myproj/models.py
from dataclasses import dataclass
from typing import Any
import pandas as pd
from catboost import CatBoostClassifier

@dataclass
class TrainResult:
    model: CatBoostClassifier
    feature_importances: dict[str, float]
    training_history: dict[str, list[float]]

def train_classifier(X: pd.DataFrame, y: pd.Series, params: dict[str, Any]) -> TrainResult:
    """Train a CatBoost classifier and return model + history."""
    model = CatBoostClassifier(**params)
    model.fit(X, y, eval_set=(X, y), verbose=False)
    importances = dict(zip(X.columns, model.feature_importances_))
    history = model.get_evals_result()["learn"]
    return TrainResult(model=model, feature_importances=importances, training_history=history)
```

Phase F: the plotting stage. Plotting functions take a fitted model or a metrics dict and return a matplotlib Figure. They should NOT call `plt.show()` (let the notebook do that). They SHOULD have a `savefig` parameter for batch use.

```python
# src/myproj/plotting.py
import matplotlib.pyplot as plt

def plot_feature_importances(importances: dict[str, float], top_n: int = 20, savefig: Path | None = None):
    fig, ax = plt.subplots(figsize=(8, 6))
    top = sorted(importances.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    ax.barh([n for n, _ in top][::-1], [v for _, v in top][::-1])
    ax.set_xlabel("Importance")
    if savefig:
        fig.savefig(savefig, dpi=150, bbox_inches="tight")
    return fig
```

Phase G: the resulting notebook is a thin orchestration:

```python
# notebooks/2026-05-train-classifier.ipynb (now ~20 cells, all calls)
from myproj.config import (RAW_DATA_BUCKET, RAW_DATA_KEY, MIN_TRANSACTIONS, MODEL_PARAMS)
from myproj.data import download_transactions, preprocess_transactions
from myproj.features import build_features
from myproj.models import train_classifier
from myproj.evaluation import score_classifier
from myproj.plotting import plot_feature_importances, plot_roc_curve

raw = download_transactions(RAW_DATA_BUCKET, RAW_DATA_KEY, dest="data/raw/transactions.parquet")
df = preprocess_transactions(raw, min_transactions=MIN_TRANSACTIONS)
X, y = build_features(df)
result = train_classifier(X, y, MODEL_PARAMS)
metrics = score_classifier(result.model, X, y)
plot_feature_importances(result.feature_importances)
plot_roc_curve(metrics["roc_curve"])
print(metrics)
```

Phase H: add a CLI entry point so the pipeline can run unattended:

```python
# src/myproj/cli.py
import typer
from myproj.data import download_transactions, preprocess_transactions
# ... etc

app = typer.Typer()

@app.command()
def train(output_dir: Path = Path("artifacts/")):
    raw = download_transactions(RAW_DATA_BUCKET, RAW_DATA_KEY, dest="data/raw/transactions.parquet")
    df = preprocess_transactions(raw)
    X, y = build_features(df)
    result = train_classifier(X, y, MODEL_PARAMS)
    output_dir.mkdir(exist_ok=True)
    save_model(result.model, output_dir / "model.cbm")
    save_metrics(score_classifier(result.model, X, y), output_dir / "metrics.json")

if __name__ == "__main__":
    app()
```

The notebook is now the human-facing interface (exploration, plotting, sanity-checking); the CLI is the unattended interface (CI, scheduled retraining, hyperparam sweeps). Both share the same library.

Phase I: tests. Add tests for `data.py`, `features.py`, and the metrics in `evaluation.py`. Skip tests for `models.py` (training is expensive) and `plotting.py` (the test would just check the figure has axes; not high value).

The deltas from the small-notebook case: more modules, more discipline around dataclasses for training output, a CLI entry point alongside the notebook. The structural workflow is the same; the granularity scales with notebook size.

## Edge cases

1. **The notebook depends on a colleague's local file that is not in the repo** (`/Users/alice/Downloads/data.csv`): the productionized version must take the path as a parameter or pull from a versioned storage. Surface the dependency, do not paper over it. If the colleague is no longer around, the productionization is blocked until the data source is identified.

2. **The notebook runs for 4 hours end-to-end**: do not retry the full run during the refactor. Mock or sample the data, refactor against the small version, then run the full version once at the end to confirm parity.

3. **The notebook trains a model with random initialization but no seed**: the refactored version produces different numbers than the original notebook. Pin the seed before extracting. If the team is comparing pre / post refactor outputs, identical numbers prove the refactor is faithful.

4. **The notebook uses `from ... import *` everywhere**: every cell pulls everything from a utility module. The refactor needs to identify which names are actually used per cell and import them explicitly. Star imports hide the dependency graph.

5. **The notebook has a magic `%pip install` cell that installs from a git URL**: the productionized version uses `pyproject.toml` with an explicit git dependency. Pin the commit hash, not just the branch, so future installs are reproducible.

6. **The notebook outputs to a Google Drive link or a Slack channel**: side effects (writes, posts, sends) belong in functions with explicit IO arguments, not in the notebook body. The refactored function takes a `dest: Path | str` parameter and the user decides where to write.

## Anti-patterns

1. **Big-bang refactor in one commit**: irrecoverable if anything breaks. Slice into the four-stage commit plan (skeleton, constants, data + clean, features + model). Each commit leaves the notebook runnable.

2. **Deleting the notebook after refactoring**: the thin notebook is still useful (it is the exploration surface). Delete the SCRATCH cells, keep the orchestration cells.

3. **Adding tests that pin model output exactly**: model outputs can change between library versions, between random seeds, between machines. Test the SHAPE of the output, the dtype, the value range. Reserve exact-value tests for deterministic transforms (a feature encoder, not a model).

4. **Skipping the dependency manifest**: `requirements.txt` without versions is not reproducibility. Pin minor versions at minimum (`pandas>=2.1,<2.2`) and commit a lockfile.

5. **Refactoring around magic numbers without naming them**: extracting `0.5` as a function parameter is half the work. The other half is naming it `MIN_CONFIDENCE_THRESHOLD = 0.5` so the reader knows what it means.

## When to chain with

- **agent-repo-briefing**: the brief identifies a mature notebook that should be productionized. The skill picks up from there.
- **data-profiling**: the profile of the input dataset becomes the docstring of the load function. Future readers know what the data looks like without re-deriving it.
- **statistical-analysis**: the notebook's analysis cells get lifted into a tested function in `src/`. The test runs the same analysis on a fixture and pins the expected output.
- **rag-eval-method**: a one-off retrieval-eval notebook becomes a reusable `eval_retrieval.py` script that the team runs on every retriever change.

Productionization is rarely the start of a chain; it is the consolidation step after exploration has produced something worth keeping.

## Decision tree

```
Will the notebook be rerun by anyone other than the original author?
  No  -> productionization is overkill; leave as-is
  Yes -> continue
        |
        v
Is the notebook less than 50 lines AND less than 30 cells?
  Yes -> not worth a refactor; tidy in place if needed
  No  -> continue
        |
        v
Does it currently run end-to-end on a fresh kernel?
  No  -> fix first, then refactor
  Yes -> continue
        |
        v
Does the project already have a layout?
  Yes -> follow it; do not impose cookiecutter
  No  -> scaffold cookiecutter-data-science V2
        |
        v
Is the notebook simple (one stage) or multi-stage?
  Simple      -> standard 10-step workflow
  Multi-stage -> second worked example (per-stage modules + CLI entry point)
        |
        v
Commit in slices (skeleton, constants, then one stage per commit)
```

## Output schema

The skill produces a restructured project directory plus a chat reply.

**Artifacts created or modified:**

1. `pyproject.toml` (or updated equivalent) with pinned dependencies.
2. `uv.lock` (or `poetry.lock`, etc.) committed.
3. `src/<package>/` with one module per logical stage (data, features, models, evaluation, plotting).
4. `src/<package>/config.py` (or constants section in `pyproject.toml`) with all named constants.
5. `tests/` with at least one test per data / features / evaluation function.
6. The original notebook, thinned to import from the new package.
7. `README.md` with setup, run, and test commands.
8. `.pre-commit-config.yaml` with ruff (optional but recommended).
9. Optional: `src/<package>/cli.py` for unattended runs.

**Chat reply summarizes:**

- The files added (path + one-sentence purpose each).
- The functions extracted (path + which cell each came from).
- The tests added (path + what behavior each covers).
- The next refactor candidate (a function still embedded in the notebook that should move out next).
- Any blocking issues found during the refactor (missing data, broken cells, hard-coded paths).

The chat reply is roughly 200 to 400 words. The structural change is visible in the diff; the prose explains the WHY.

## Limits

The skill stops at the package boundary. It produces a structured, tested, reproducible project with a CLI entry point. It does NOT produce a deployed service, a Docker image, a Kubernetes manifest, or a CI pipeline. Those are separate concerns that build on top of the productionized package.

The skill assumes the notebook's logic is correct. If the notebook has a bug, the productionized version has the same bug (now in `src/`, possibly with a test that pins the bug in place). Review the logic during the refactor, not just the structure.

The skill does not auto-tune dependencies. If the notebook pins `pandas==2.0` because of a known compatibility issue, the refactor preserves the pin. Updating versions is a separate task.

The skill works best on Python notebooks. R notebooks (Quarto, RMarkdown) follow a similar pattern but the tooling is different. Adapt the workflow to `renv` / `targets` / `box` rather than `uv` / `pytest` / `src/`.
