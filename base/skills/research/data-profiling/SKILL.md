---
name: data-profiling
description: Use when the user wants to profile a new dataset before modeling (load, inspect schema, dtypes, missing values, distributions, outliers) and produce a short markdown profile they can paste into a notebook or report.
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, data, exploration, eda]
scope: [research]
---

# Data Profiling

What this gets you: a one-page markdown profile of a fresh dataset (CSV, parquet, jsonl) that a teammate or coding agent can read in under two minutes. Schema, dtypes, row counts, missingness, distribution snapshots, outlier flags, and the first three questions you should answer before modeling. Run it the moment a dataset lands on disk and before any feature engineering or modeling decision.

The point is to make the dataset legible. Skipping this step is how research projects end up with silent dtype coercions, leaked targets, and surprise nulls discovered three iterations into a model.

## When NOT to use this skill

- The dataset is already profiled and the profile is fresh (less than a sprint old, schema unchanged). Re-read the existing profile instead.
- The user wants a deep statistical analysis or a hypothesis test. Use `skills/research/statistical-analysis/` for that.
- The dataset is greater than 50M rows. Sample first (see Step 1) or use a Spark / DuckDB profile pattern instead of pandas.
- The dataset is unstructured (images, raw text, audio). This skill assumes tabular data.

## Inputs you need from the user

Before starting, confirm these in one short exchange (do not ask one at a time):

1. **Path or URL** to the dataset.
2. **Format** (CSV, parquet, jsonl, xlsx, sqlite). Infer from extension if obvious.
3. **Target column** if there is one, so the profile flags target leakage candidates.
4. **Known sensitive columns** to redact in the output (emails, IDs, free-text PII).

If the user is uncertain about target or sensitive columns, run the profile anyway and flag candidates for them to confirm.

## Workflow

### Step 1: Load with the right tool

Pick the loader by format and size. Defaults that scale well:

```python
import pandas as pd
from pathlib import Path

path = Path("data/raw/customers.parquet")

if path.suffix == ".csv":
    df = pd.read_csv(path, low_memory=False)
elif path.suffix in (".parquet", ".pq"):
    df = pd.read_parquet(path)
elif path.suffix in (".jsonl", ".ndjson"):
    df = pd.read_json(path, lines=True)
elif path.suffix == ".xlsx":
    df = pd.read_excel(path)
else:
    raise ValueError(f"Unsupported extension: {path.suffix}")
```

If the file is greater than 1GB or the user reports memory pressure, sample first:

```python
df = pd.read_csv(path, nrows=100_000)  # head sample for quick profile
# For random sample: read full, then df.sample(n=100_000, random_state=42)
```

Note the sampling choice in the profile output (head vs random) because it affects how you interpret the distributions.

### Step 2: Headline stats

The three numbers that matter most for a first look:

```python
n_rows, n_cols = df.shape
mem_mb = df.memory_usage(deep=True).sum() / 1024**2
dup_rows = df.duplicated().sum()
```

Capture them at the top of the profile. If `dup_rows` is non-zero, that is a finding (call it out, do not silently drop).

### Step 3: Schema and dtypes

```python
schema = pd.DataFrame({
    "dtype": df.dtypes.astype(str),
    "n_unique": df.nunique(dropna=True),
    "n_missing": df.isna().sum(),
    "pct_missing": (df.isna().mean() * 100).round(2),
})
```

Look for:

- Columns inferred as `object` that should be numeric (string-encoded numbers from a bad CSV export). Try `pd.to_numeric(..., errors="coerce")` and see if it survives.
- Datetime columns inferred as `object`. Try `pd.to_datetime(..., errors="coerce")` and report parse success rate.
- Columns where `n_unique == n_rows` (likely identifiers, not features).
- Columns where `n_unique == 1` (constants, drop candidates).
- Columns where `pct_missing` is greater than 50% (consider whether the column is meaningful at all).

### Step 4: Distributions (numeric)

For numeric columns:

```python
numeric = df.select_dtypes(include=["number"])
desc = numeric.describe(percentiles=[0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]).T
desc["skew"] = numeric.skew()
desc["kurtosis"] = numeric.kurtosis()
```

Flag:

- Columns where `min < 0` for quantities that should be non-negative (counts, durations, prices).
- Columns where `max` is suspiciously round (capped values like 999 or 9999).
- Heavy skew (`|skew| > 2`) which often means log-transform candidates for downstream modeling.
- The ratio `(p99 - p95) / (p95 - p50)`: greater than 5 suggests a heavy tail worth a separate look.

### Step 5: Categorical breakdowns

For string and categorical columns:

```python
for col in df.select_dtypes(include=["object", "category"]).columns:
    vc = df[col].value_counts(dropna=False).head(10)
    pct = (vc / len(df) * 100).round(2)
```

Flag:

- High-cardinality columns (greater than 1000 unique values in a small dataset) where you may need to bucket or hash.
- Columns with one dominant level (greater than 95% of rows in one category): low information.
- Columns that look like free text (long strings, high uniqueness): probably need NLP, not categorical encoding.

### Step 6: Missingness pattern

A scalar missing rate hides whether missingness is structured. Quick check:

```python
miss = df.isna()
co_missing = miss.T.dot(miss)  # n_cols x n_cols matrix of joint nulls
```

If two columns are missing together (e.g., `address_line_2` and `address_apt`), they probably share a root cause (the address parser failed, the user skipped a section). That changes the imputation strategy.

For larger datasets, the `missingno` package gives a quick heatmap. For smaller ones, a printed correlation of the null indicator matrix is enough.

### Step 7: Outliers (numeric only, first pass)

A first-pass outlier flag using IQR. Not a final decision, just a signal:

```python
def iqr_outlier_count(s: pd.Series, k: float = 1.5) -> int:
    q1, q3 = s.quantile([0.25, 0.75])
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    return int(((s < lo) | (s > hi)).sum())

outliers = {c: iqr_outlier_count(df[c]) for c in numeric.columns}
```

Report the count and percentage. Do not auto-remove. Outliers in a research dataset can be the most interesting rows.

### Step 8: Target leakage scan (if target column known)

For each non-target column, check correlation (numeric) or mutual information (mixed) with the target. Anything with `|r| > 0.95` or near-perfect MI is a leak candidate. Common offenders: post-event columns (a `closed_at` timestamp present for the target class), engineered columns that already use the target.

```python
if target and target in df.columns:
    y = df[target]
    if y.dtype.kind in "biufc":
        corr = df.select_dtypes(include=["number"]).corrwith(y).abs().sort_values(ascending=False)
```

Flag the top 5 by correlation. The user makes the leak decision; the profile just surfaces the candidates.

### Step 9: Write the markdown profile

Write to a file named `<dataset-stem>.profile.md` next to the dataset (or under `reports/profiles/` if the project follows the cookiecutter-data-science layout). Structure:

```markdown
# Profile: customers.parquet

Loaded: 2026-05-24 by data-profiling skill
Sampled: no (full 487,213 rows)

## Headline
- Shape: 487,213 rows x 24 cols
- Memory: 312.4 MB
- Duplicates: 0
- Target column: churned_flag (binary)

## Schema flags
- email: object (likely PII, redacted in output)
- signup_date: object, parses cleanly as datetime (97.8%); recommend cast
- customer_id: object, n_unique == n_rows (identifier, exclude from features)
- legacy_segment: constant ("standard"), drop candidate

## Missingness
- referral_source: 64.2% missing, co-missing with referral_campaign (0.91 cor)
  -> probably "user did not come via referral", consider imputing as "organic"
- last_login_ts: 8.1% missing, isolated, likely never-logged-in users

## Distribution flags
- monthly_spend: heavy skew (skew=4.2), p99=$2,847 vs p50=$48, log-transform candidate
- account_age_days: bimodal at 30 and 365, suggests two cohorts (trial vs annual)
- session_count: min=-1 (data quality issue, 14 rows)

## Outlier first pass (IQR, k=1.5)
- monthly_spend: 18,402 rows (3.8%)
- support_tickets: 1,221 rows (0.25%)

## Target leakage candidates
- cancellation_reason: 0.99 corr with churned_flag (post-event, exclude)
- last_refund_amount: 0.81 corr (review, may be post-event)

## First three questions to answer
1. Confirm cancellation_reason is post-event and exclude from training set.
2. Decide imputation strategy for referral_source (treat NA as a category or impute).
3. Investigate the 14 rows with session_count == -1: data error or sentinel?
```

The "First three questions" section is the most important. A profile that ends in observations alone is half a profile. End in decisions the user has to make.

## Tooling shortcuts

For a quick start when the dataset is small (less than 100k rows, less than 30 columns), the `ydata-profiling` package produces an HTML report in one call:

```python
from ydata_profiling import ProfileReport
ProfileReport(df, title="Customers", minimal=True).to_file("customers_report.html")
```

For console-only summaries, `skimpy` is lightweight and fast:

```python
from skimpy import skim
skim(df)
```

Use these as starting points, then write the markdown profile by hand. Auto-generated HTML reports are good for exploration but bad for review. A human-curated markdown profile is what a teammate will actually read.

## When the profile changes the plan

Common findings that change downstream decisions:

- **Target leakage candidates found**: stop the modeling pipeline, exclude leaky columns, re-run.
- **Greater than 50% missingness on a candidate feature**: ask whether the column is meaningful or whether a different data source is needed.
- **Mixed dtypes in what should be a numeric column**: fix upstream extraction before profiling further.
- **Class imbalance discovered (target is 98 / 2 split)**: switch from accuracy to precision / recall / F1 and consider sampling or class weights.
- **Bimodal distributions in features**: investigate whether the dataset is actually two cohorts that should be modeled separately.

Surface these as part of the profile, do not bury them.

## Output shape

A `.profile.md` file at a stable path next to the dataset, plus a short conversation reply summarizing the top three findings and the three open questions. If the user asks for a notebook cell instead, paste the profile as a markdown cell with the same structure.

## Sources

- ydata-profiling docs, https://ydata-profiling.ydata.ai
- Real Python, "Automate Python Data Analysis With YData Profiling" (2025), https://realpython.com/ydata-profiling-eda
- DrivenData, "Cookiecutter Data Science V2" (project structure for the reports/ layout)

## Pre-flight checklist

Run through these before pulling up a profile. The skill is cheap to run but it is not free, and a stale or duplicate profile is worse than no profile.

1. Has this dataset been profiled in the last sprint? Check `reports/profiles/` (or wherever the team puts profiles) for an existing file. If one exists and the file modification timestamp is newer than the dataset modification timestamp, read the existing profile.
2. Is the dataset stable (not actively being rewritten by an upstream pipeline)? Profiling a file mid-write produces nonsense numbers. Coordinate with the pipeline owner if in doubt.
3. Does the user have an actual downstream question (modeling, reporting, sanity-check)? If they just want to look at the data, point them at a notebook with `df.sample(20)` instead of running the full profile.
4. Is the dataset small enough that pandas can load it in memory? For files greater than 5GB on a 16GB machine, use the sampling pattern in Step 1 or switch to DuckDB / Polars.
5. Are there target leakage concerns the user wants surfaced? If yes, confirm the target column up front.

If three or more answers are uncertain, ask the user a clarifying question before invoking. A profile generated for an unclear purpose tends to omit the one column the user actually cared about.

## Second worked example: JSON event log

The first worked example assumed a clean tabular CSV / parquet. Many research datasets are nested JSON event logs (clickstream, agent traces, instrumentation events). The flow needs adjustment because the schema is not flat.

Phase A: load with the right tool. JSON event logs are usually JSONL (one event per line). Use `pd.read_json(path, lines=True)` for files less than 5GB, or `duckdb.read_json_auto()` for larger files (DuckDB streams through JSON natively).

```python
import pandas as pd
df = pd.read_json("data/raw/agent_events.jsonl", lines=True)
print(df.shape, df.columns.tolist()[:10])
```

Phase B: detect nested columns. A pandas dataframe loaded from JSONL often has columns that contain dicts or lists:

```python
nested_cols = [c for c in df.columns if df[c].apply(lambda x: isinstance(x, (dict, list))).any()]
print("Nested columns:", nested_cols)
```

These columns do not respond to the normal `df.describe()` or `df.nunique()` calls. Either flatten them with `pd.json_normalize` or profile their structure separately.

Phase C: schema profile for flat columns only. Run the standard schema / dtype / missingness sweep on the flat columns. Skip the nested ones for now.

Phase D: structural profile for nested columns. For each nested column, sample 100 to 1000 rows and inspect the shape:

```python
for col in nested_cols:
    sample = df[col].dropna().head(100)
    if sample.apply(lambda x: isinstance(x, dict)).all():
        all_keys = set().union(*[set(d.keys()) for d in sample])
        print(f"{col}: dict with {len(all_keys)} unique keys, sample keys: {list(all_keys)[:10]}")
    elif sample.apply(lambda x: isinstance(x, list)).all():
        lengths = sample.apply(len)
        print(f"{col}: list with length min={lengths.min()}, max={lengths.max()}, mean={lengths.mean():.1f}")
```

Phase E: event distribution. For event logs, the most useful summary is "events per type, per time bucket". Group by event type and hour / day:

```python
df["timestamp"] = pd.to_datetime(df["timestamp"])
events_by_type_and_hour = df.groupby([df["timestamp"].dt.floor("H"), "event_type"]).size().unstack(fill_value=0)
```

Look for gaps (no events for several hours; pipeline outage), spikes (a single event type dominates; instrumentation bug), and shifts (event mix changes over the window; a deploy happened mid-collection).

Phase F: per-user or per-session metrics. If the events have a user_id or session_id, the profile should include per-session distributions (events per session, session duration, drop-off points). These are usually the most actionable signal.

Phase G: write the profile. The structure is the same as the tabular case, but with two additional sections: "Nested column shapes" and "Event distributions over time". The "First three questions" section often becomes: which event types are noisy enough to drop? Are the session boundaries reliable? Is the timestamp field timezone-correct?

The takeaway: the workflow is the same, but Steps 3 to 7 split into flat-column work and nested-column work. Profiling a nested dataset with only the flat-column tools (most common mistake) leaves 60% of the signal on the table.

## Edge cases

1. **The dataset is sorted by a sensitive column (e.g., signup date)**: the head sample from Step 1 is a date-skewed sample, not a representative one. Use `df.sample(n, random_state=42)` instead, or shuffle before sampling. Note the sampling strategy in the profile.

2. **The dataset has a column whose name conflicts with a pandas attribute (e.g., `name`, `index`, `shape`)**: accessing `df.name` returns the attribute, not the column. Use `df["name"]` throughout the profile code, never the attribute access shortcut.

3. **The target column is heavily imbalanced (99 / 1 split)**: aggregate statistics over the full dataset are dominated by the majority class. Compute the profile per class as well, especially distributions of features. Flag the imbalance in the profile so downstream modeling uses the right loss / sampling strategy.

4. **The dataset is a time series with a time index, not a flat table**: missingness is now "missing timestamps in the time range" not just NaN counts. Resample to a regular frequency and report gaps. Outliers should be defined within rolling windows, not against the global mean.

5. **The dataset is a join of two tables with overlapping column names**: pandas suffixes the duplicates (`col_x`, `col_y`). Surface this as a finding because it usually means the join introduced silent duplicates. Recommend re-joining with explicit suffixes or dropping one side.

6. **The dataset has free-text columns that the profile reports as "object, high cardinality"**: that is technically correct but unhelpful. Sample 5 to 10 values and include them inline so the reader sees what the text looks like. A free-text column needs NLP treatment, not categorical encoding.

## Anti-patterns

1. **Auto-generating an HTML profile (ydata-profiling) and shipping it as the deliverable**: the HTML is useful for exploration but it is a giant file no teammate will read. The deliverable is the curated markdown profile with the "First three questions" section. Use the HTML as a draft, write the markdown by hand.

2. **Dropping rows with any missing value before profiling**: this is the most common silent data corruption. The profile is supposed to surface missingness as a finding, not hide it. Run the profile on the raw data; let the user decide what to drop.

3. **Letting pandas infer dtypes silently**: a 24-column CSV often has 3 columns where pandas inferred `object` because of one bad row. Surface these explicitly in the schema section so the user knows to fix the source.

4. **Profiling a sample without saying so**: a profile that says "487k rows" when you actually read 100k is a lie. The profile header must state whether sampling happened and how (head, random, stratified).

5. **Treating the IQR outlier count as a list of rows to delete**: outliers in a research dataset can be the most interesting rows. The profile reports the count; the user decides what to do.

## When to chain with

Data profiling is the second-most-common starting move (after `agent-repo-briefing`). It often runs:

- **After agent-repo-briefing**: the brief identifies a dataset, the profile inspects it. Pair the two when onboarding to a new repo with unfamiliar data.
- **Before hypothesis-design**: you cannot design an experiment on data you have not inspected. The profile surfaces class imbalance, missingness patterns, and effect-size context that the experiment design needs.
- **Before statistical-analysis**: a t-test on a heavily skewed column is not informative. The profile flags the skew so the analyst picks a non-parametric test (or transforms first).
- **Before notebook-to-production**: the profile becomes part of the docstring for the load function in `src/data.py`. Future readers know what the data looks like without re-deriving it.
- **Before rag-eval-method**: if the labeled query set is a dataset in its own right, profile it (query length distribution, judgment-grade distribution, per-topic coverage) before computing retrieval metrics.

The skill is rarely the last step. Almost always there is a modeling or analysis decision that the profile feeds into.

## Decision tree

```
Is the dataset structured (tabular) or unstructured (images, audio, raw text)?
  Unstructured -> skill does not apply, use modality-specific EDA tooling
  Structured   -> continue
        |
        v
Is the dataset less than 5GB?
  Yes -> use pandas (standard workflow)
  No  -> sample with df.sample(n=100k, random_state=42) and note the sample
         OR switch to DuckDB / Polars for the full profile
        |
        v
Is the dataset flat (rectangular) or nested (JSON, lists, dicts)?
  Flat   -> standard 9-step workflow
  Nested -> follow the second worked example (split flat / nested)
        |
        v
Does the user know the target column?
  Yes -> include target leakage scan (Step 8)
  No  -> skip Step 8, flag in the profile that no leakage check ran
        |
        v
Has this dataset been profiled before, less than a sprint ago, with no schema changes?
  Yes -> read the existing profile, do not regenerate
  No  -> run the full skill
        |
        v
Write the .profile.md, surface top 3 findings + 3 open questions
```

## Output schema

The skill produces one or two artifacts.

**Primary artifact: the markdown profile.** Path convention: `reports/profiles/<dataset-stem>.profile.md`, or sibling to the dataset if there is no `reports/` directory. Required sections in order:

1. Header (dataset name, load timestamp, sampling note if sampled).
2. `## Headline` (shape, memory, duplicates, target column if any).
3. `## Schema flags` (columns flagged for dtype, identifiers, constants, high missingness).
4. `## Missingness` (per-column rates, co-missingness patterns).
5. `## Distribution flags` (numeric columns with skew, capped values, suspect ranges).
6. `## Outlier first pass` (IQR counts per numeric column).
7. `## Target leakage candidates` (if target known; otherwise omit).
8. `## First three questions to answer` (decisions the user has to make next).

The "First three questions" section is non-negotiable. A profile without it is a description, not a recommendation. The whole point is to surface decisions, not just observations.

**Secondary artifact: the chat reply.** A short summary listing the top 3 findings and the 3 open questions. The chat reply lets the user start the conversation without reading the full markdown. The markdown is the durable artifact; the chat is the trailer.

**Optional artifact: an HTML report.** Generated by ydata-profiling for exploration only. Stored under `reports/profiles/<dataset-stem>.html` if the user asks for it. Not committed to git by default (it is too large); add to `.gitignore` if the team does not want it tracked.

Word count target for the markdown: 300 to 800 words. A profile longer than that has stopped being a profile and started being a notebook.

## Quality checks before delivery

Walk through these before handing the profile to the user or to a downstream skill:

1. **Is every flagged column actionable?** A column flagged as "high missingness" needs the downstream implication (drop, impute, model the missingness). A flag without an implication is noise.
2. **Are the schema flags real, not pandas artifacts?** A column inferred as object that is actually text is fine. A column inferred as object because of one stray non-numeric value is a real flag. Distinguish.
3. **Is the target leakage section honest?** If you did not check leakage (no target column), say so. Do not omit the section silently; the user might assume leakage was clean.
4. **Are the "First three questions" decisions, not observations?** "The data is skewed" is an observation. "Should we log-transform monthly_spend or model the tail separately?" is a decision. Rewrite if needed.
5. **Is the profile reproducible?** A profile that the user cannot regenerate next month is a snapshot, not a contract. Commit the profile and the script that produced it.

If any check fails, fix before delivering. A profile that surfaces the wrong findings is worse than no profile because it leads the user astray.

## Limits

The skill is a sampling instrument, not a deep statistical analysis. It surfaces what is obvious in the first pass. Subtle bugs (silent distribution shifts between train and test, label-leakage hidden behind a join, time-of-day effects) often require a second pass that mixes profiling with hypothesis testing.

The skill assumes the dataset is correct at the source. If the upstream pipeline silently dropped 10% of rows, the profile will faithfully describe the corrupted version. The user should always cross-check the profile's row count against an independent reference (the source system's record count, a prior version of the same data) before trusting the rest of the profile.

The skill does not produce a feature-engineering plan. It surfaces what features look like; the user (or a downstream feature-engineering skill) decides what to derive. Confusing profiling with feature design is a common scope creep that leads to overlong profiles.

## Profile templates by dataset type

The default workflow assumes a generic tabular dataset. Three specialized templates calibrate the focus.

**Time-series profile.** Add sections for:

- Sampling rate (regular or irregular).
- Gaps in the time index (periods with no observations).
- Stationarity check (rolling mean, rolling std).
- Seasonality (autocorrelation at common lags: hour, day, week, year).
- Anomaly windows (periods with values far from the rolling mean).

The "First three questions" usually become: are the gaps real or instrumentation outages? Is the seasonality strong enough to require detrending? Are the anomaly windows model-relevant or noise?

**Categorical-heavy profile.** Add sections for:

- Cardinality per column (with the distribution of unique counts).
- Top values per column (top 10 with percentages).
- Co-occurrence of high-cardinality columns (do values cluster?).
- High-cardinality columns that may need bucketing or hashing.

The "First three questions" usually become: are any high-cardinality columns acting as identifiers in disguise? Are there free-text columns mislabeled as categorical? Are the dominant values stable across time?

**Text-heavy profile.** Add sections for:

- Length distribution (chars, words, sentences).
- Language distribution (if applicable).
- Top tokens or n-grams (after basic cleaning).
- Encoding issues (non-UTF-8 sequences, mojibake).
- Duplicate or near-duplicate text rows.

The "First three questions" usually become: do we need language-specific preprocessing? Is the duplicate rate high enough to deduplicate? Are there encoding issues that need to be fixed upstream?

Use the right template for the dataset type. A generic profile on a time series misses the gaps; a generic profile on text data misses the language mix.

## Tooling notes

The skill works with:

- **pandas** for most operations (read, describe, missingness, dtypes).
- **pyarrow** for parquet reading (the default backend for `pd.read_parquet`).
- **numpy** for distribution statistics.
- **seaborn / matplotlib** for distribution plots (optional; the markdown profile usually stands without inline charts).
- **missingno** for missingness heatmaps (optional; useful for datasets with greater than 20 columns where co-missingness matters).
- **ydata-profiling** for an HTML draft (optional; do not ship the HTML, use it as a draft for the curated markdown).
- **skimpy** for console-only summaries (optional; fast when the user just wants a one-screen overview).

For larger datasets that do not fit in pandas memory:

- **DuckDB** for SQL-style profiling on parquet / CSV files (`SELECT COUNT(*), AVG(x), STDDEV(x) FROM 'file.parquet'`).
- **Polars** for fast pandas-like profiling on large datasets.
- **PySpark** for very large distributed datasets (typically only in production data engineering contexts).

The skill does not require GPU or specialized hardware. Most profiles run in seconds to minutes on a laptop. Sampling is the right answer when the full data does not fit; faster hardware is not.

## Idempotency

A profile run twice on the same dataset should produce the same output (modulo timestamps). Test this by running the profile twice on a frozen dataset and diffing the markdown. Any non-deterministic output (a sampling step without a seed, a hash that varies between runs) is a bug.

Idempotency matters because the profile is committed and reviewed. A reviewer should be able to re-run the profile against the same data and see identical numbers. If the numbers shift, the data drifted or the profile script changed; either way, the change is worth investigating.

Pin random seeds at the top of the profile script: `RANDOM_SEED = 42`. Document the seed in the profile header so the next reader knows the sampling was deterministic.
