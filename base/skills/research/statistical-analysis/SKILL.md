---
name: statistical-analysis
description: Use when the user wants to test whether a difference is real (compare groups, run a t-test, ANOVA, chi-squared, correlation, etc.). Walks the disciplined workflow of describe, check assumptions, pick the test, run, interpret p-value and effect size, write up.
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, statistics, hypothesis-test, p-value, effect-size]
scope: [research]
---

# Statistical Analysis

What this gets you: a defensible test on a dataset (the right test for the data shape, with assumption checks, with an effect size next to the p-value, with the interpretation written for a non-statistician reader). The output stops a teammate or stakeholder from misreading the result.

Most "is X significant?" failures in research are not bad math. They are skipped steps: not checking normality before a t-test, ignoring effect size, or running ten tests and reporting the one that hit p less than 0.05. This skill is the discipline that prevents those failures.

## When NOT to use this skill

- The user wants exploratory data analysis, not a confirmatory test. Use `skills/research/data-profiling/` first.
- The user wants to design an experiment before collecting data. Use `skills/research/hypothesis-design/` for power calculation and pre-registration.
- The user wants Bayesian estimation rather than frequentist NHST. The skeleton is similar (describe, check, fit, interpret) but the test choice is different (use PyMC, numpyro, or Bambi).
- The user has greater than 1M observations and wants causal inference, not significance testing. Different toolchain (econometrics packages, causal graphs).

## Inputs you need from the user

Confirm in one short exchange (do not ask one at a time):

1. **The question** stated as a hypothesis. "Is X different between A and B?" Or "Is X correlated with Y?"
2. **The data** (path to the file or the dataframe variable name).
3. **The groups or columns** involved.
4. **Whether this is pre-registered or post-hoc**. Post-hoc is fine, but the writeup will say so.
5. **The decision the test informs**. Affects how strict the alpha threshold should be.

If the user starts with "is X significant?" without a hypothesis, push back. Surface the implicit hypothesis before running anything.

## Workflow

### Step 1: Describe the data

Before any test, look at the data. Compute:

- Sample size per group.
- Mean, median, standard deviation per group (or per relevant slice).
- Min, max, range (catches obvious errors).
- Count of missing values per group.

```python
import pandas as pd
desc = df.groupby("group")["metric"].agg(["count", "mean", "median", "std", "min", "max"])
miss = df.groupby("group")["metric"].apply(lambda s: s.isna().sum())
```

If group sizes are imbalanced by more than 4 to 1, note it. Some tests assume balanced groups and degrade silently when they are not.

### Step 2: Visualize the distributions

Histograms, density plots, boxplots. Two minutes of plotting often makes the test choice obvious:

```python
import seaborn as sns
sns.histplot(data=df, x="metric", hue="group", element="step", stat="density", common_norm=False)
sns.boxplot(data=df, x="group", y="metric")
```

What you are looking for:

- Roughly symmetric or heavily skewed?
- Single peak or bimodal?
- Outliers that would dominate the mean?
- Obviously different shape across groups (not just shifted means)?

Skewed or bimodal distributions usually mean a non-parametric test or a transformation, not a t-test on the raw values.

### Step 3: Check assumptions

Most parametric tests share three assumptions: independence, normality (within each group, not overall), homoscedasticity (equal variances across groups).

**Independence**: usually a study-design question, not a data question. Are the observations truly independent? Repeated measures on the same subject are not independent. Time-series observations are not independent.

**Normality** (per group, not overall). Use a visual check (Q-Q plot) plus a formal test for small samples:

```python
from scipy import stats
for name, group in df.groupby("group"):
    stat, p = stats.shapiro(group["metric"])
    print(f"{name}: Shapiro-Wilk W={stat:.3f}, p={p:.4f}")
```

Shapiro-Wilk is good up to n=5000. Above that, the test gets so powerful it rejects on irrelevantly small deviations. For large n, trust the Q-Q plot and your eyes.

**Homoscedasticity** (equal variances). Use Levene's test (more robust to non-normality than Bartlett's):

```python
groups = [g["metric"].dropna() for _, g in df.groupby("group")]
stat, p = stats.levene(*groups)
print(f"Levene W={stat:.3f}, p={p:.4f}")
```

If `p > 0.05`, variances are not statistically different (do not reject equal-variance assumption). If `p < 0.05`, use a test variant that does not assume equal variance (Welch's t-test instead of Student's).

### Step 4: Pick the test

Based on Steps 1 to 3, choose the test. Decision tree:

```
Comparing means of two groups?
  Independent observations?
    Normal-ish?
      Equal variances?  -> Student's t-test (independent)
      Unequal variances? -> Welch's t-test (default for most cases)
    Heavily non-normal?
      -> Mann-Whitney U (rank-based)
  Paired observations (same subject, before / after)?
    Normal-ish (of the differences)?  -> Paired t-test
    Non-normal?                       -> Wilcoxon signed-rank

Comparing means of three or more groups?
  Independent?
    Normal-ish, equal variances? -> One-way ANOVA
    Unequal variances?           -> Welch's ANOVA
    Heavily non-normal?          -> Kruskal-Wallis
  Repeated measures?             -> Repeated-measures ANOVA (Mauchly's for sphericity)

Categorical association?
  Two categorical variables? -> Chi-squared (large samples) or Fisher's exact (small)
  Ordered categorical?       -> Cochran-Armitage trend test

Continuous association?
  Linear relationship, normal residuals? -> Pearson correlation
  Monotonic but not linear?              -> Spearman correlation
  Ordinal data?                          -> Kendall's tau
```

Recommend Welch's t-test over Student's by default for two-group comparison. The cost when variances are equal is negligible. The cost when they are not equal and you used Student's is a misleading p-value.

### Step 5: Run the test

```python
from scipy import stats

a = df.loc[df["group"] == "control", "metric"].dropna()
b = df.loc[df["group"] == "treatment", "metric"].dropna()

t_stat, p = stats.ttest_ind(a, b, equal_var=False)  # Welch's
print(f"Welch's t-test: t={t_stat:.3f}, p={p:.4f}")
```

Note the test family, the test statistic, and the p-value. Do not stop here.

### Step 6: Compute effect size

A p-value with no effect size is malpractice. The p-value tells you whether a difference is detectable; the effect size tells you whether the difference matters. Common effect sizes:

- **Cohen's d** for two-group mean comparison. Rough thresholds: 0.2 small, 0.5 medium, 0.8 large.
- **Eta-squared (or partial eta-squared)** for ANOVA. The fraction of variance explained by the grouping.
- **Cramer's V** for chi-squared. 0 to 1, where 0.1 is weak, 0.3 is moderate, 0.5 is strong.
- **Pearson r** for correlation. Already an effect size.

```python
def cohens_d(a, b):
    pooled_std = ((a.std()**2 + b.std()**2) / 2) ** 0.5
    return (a.mean() - b.mean()) / pooled_std

d = cohens_d(a, b)
print(f"Cohen's d: {d:.3f}")
```

If `p < 0.05` but `d < 0.1`, you found a tiny effect that was detectable because n was huge. Report that explicitly. Do not let the p-value alone do the talking.

### Step 7: Confidence intervals

Report a confidence interval for the effect. CIs convey precision in a way p-values do not.

```python
import numpy as np
# 95% CI for the mean difference
diff = a.mean() - b.mean()
se = ((a.var(ddof=1)/len(a)) + (b.var(ddof=1)/len(b))) ** 0.5
ci_lo, ci_hi = diff - 1.96 * se, diff + 1.96 * se
print(f"Mean diff: {diff:.3f}, 95% CI [{ci_lo:.3f}, {ci_hi:.3f}]")
```

For non-parametric tests, use bootstrap CIs (`scipy.stats.bootstrap` or write a small bootstrap loop).

### Step 8: Multiple testing correction (if applicable)

If you ran more than one test on the same dataset, the family-wise false-positive rate balloons. Common corrections:

- **Bonferroni**: divide alpha by the number of tests. Strict; over-conservative for many tests.
- **Benjamini-Hochberg (FDR)**: controls the expected fraction of false discoveries; less strict than Bonferroni.

`statsmodels.stats.multitest.multipletests(pvalues, method="fdr_bh")` does it for you.

Be honest about how many tests you ran, including the ones that did not get reported. Selective reporting is the most common form of unintentional p-hacking.

### Step 9: Interpret in plain language

Write the result for the decision-maker, not for a stats teacher:

```
We compared the average click-through rate between the control group (n=412, mean 0.043)
and the treatment group (n=398, mean 0.052) using Welch's t-test.

The difference (0.009, or about 21% relative) was statistically significant (t=2.41, p=0.016, Cohen's d=0.17).
The 95% confidence interval for the difference was [0.002, 0.016].

Cohen's d of 0.17 is a small effect. The result is consistent with a real but modest improvement.
Sample sizes are large enough that even small differences become detectable.

We did not pre-register a stopping rule, so the result should be confirmed with a separate validation run
before rolling out broadly.
```

The interpretation answers four questions:

1. What test did we run and on what data?
2. What did we find (effect size, CI, p-value)?
3. How meaningful is the effect in context?
4. What caveats apply (pre-registration, multiple testing, design limits)?

### Step 10: Write up

The writeup belongs in a markdown report, a notebook cell, or a stakeholder summary. Include:

- The hypothesis (as stated before looking at the data).
- The test chosen and why.
- The result (effect size, CI, p-value).
- The interpretation.
- The caveats.
- The data and the code that ran the test (link or inline).

A test result with no reproducible code is a rumor.

## Common pitfalls

- **HARKing** (hypothesizing after the result is known). Running a test, finding a pattern, then writing the hypothesis to match. This is the single largest source of false discoveries. Mark all post-hoc analyses as such.
- **P-hacking**: running variants until something hits p less than 0.05. If you tested multiple slicings, report all of them and apply correction.
- **Reading the null as truth**: "p = 0.12 means there is no effect" is wrong. It means the data did not provide strong evidence against the null. Absence of evidence is not evidence of absence.
- **Ignoring assumptions**: a t-test on a heavily skewed distribution with n=20 is not informative. Switch to Mann-Whitney U.
- **One huge test**: when you actually have 50 sub-questions. Multiple testing correction or a hierarchical model is needed.
- **Misreading effect direction**: `t < 0` does not mean "no effect"; it means group A's mean is lower than group B's. Check which is which.

## Output shape

A short markdown writeup with the test, the result, the effect size, the CI, and the plain-language interpretation. A copy of the code that ran it (notebook cell or `.py` script). If the user needs a chart, a single comparison plot (boxplot or violin plot with the group means annotated).

## Sources

- GeeksforGeeks, "Difference between t-test and ANOVA" (2024), assumption summary
- Clyte Tech, "When to use t-test vs ANOVA" (Dec 2025)
- General prior art: the American Statistician special issue on p-values (Wasserstein et al. 2019); the "New Statistics" movement (Cumming 2014) for emphasis on effect sizes and CIs over p-values.

## Pre-flight checklist

Before running any test, confirm:

1. **The hypothesis was stated before looking at the data.** If not, mark the analysis as exploratory in the writeup. Exploratory results are suggestive, not confirmatory.
2. **The unit of analysis is clear.** Are observations independent? Repeated measures on the same subject violate independence. Clustered data (multiple observations per user) violates it too.
3. **The metric is operationalized.** "Customer satisfaction" is not a metric; "the mean of post-call rating on 1-5 scale" is.
4. **The sample size is non-trivial.** A t-test on n = 4 per group is mostly noise. If n is under 10 per group, switch to non-parametric tests and interpret with caution.
5. **The data has been profiled.** A test on a column you have not eyeballed is a test on whatever silently broke during upstream processing.

If any of these are uncertain, run the relevant prerequisite skill (data-profiling, hypothesis-design) before continuing.

## Second worked example: chi-squared on a 2x3 contingency table

The first worked example used Welch's t-test on a continuous metric. The contrasting case is a categorical analysis: a chi-squared test on a 2x3 contingency table.

Scenario: the team has rolled out three onboarding flow variants (A, B, C) and wants to know whether the conversion rate ("converted within 7 days", binary outcome) differs across them. The data is per-user with `(variant, converted)` columns; 1200 users total split roughly evenly across the three variants.

Phase A: describe the data. Count and proportion per variant:

```python
import pandas as pd
ct = pd.crosstab(df["variant"], df["converted"])
prop = pd.crosstab(df["variant"], df["converted"], normalize="index")
print(ct)
print(prop.round(3))
```

Output:
```
converted    False  True
variant
A              280    120     (conversion rate: 30.0%)
B              260    140     (conversion rate: 35.0%)
C              250    150     (conversion rate: 37.5%)
```

Phase B: visualize. A bar chart with 95% CI bars per variant. Three bars, with the confidence intervals showing whether the differences are plausibly real:

```python
import seaborn as sns
import matplotlib.pyplot as plt
sns.barplot(data=df, x="variant", y="converted", ci=95)
```

Phase C: check assumptions. Chi-squared has fewer assumptions than t-test. The main one: expected count in each cell is at least 5. With 1200 users split evenly and conversion rates around 30 to 38%, every cell exceeds 80 expected counts. Good to go. If any cell expected count is under 5, switch to Fisher's exact test.

Phase D: pick the test. Two categorical variables (variant with 3 levels, converted with 2 levels), independent observations, expected counts above 5. Pearson chi-squared is the answer.

Phase E: run the test.

```python
from scipy import stats
chi2, p, dof, expected = stats.chi2_contingency(ct.values)
print(f"chi-squared: {chi2:.3f}, dof: {dof}, p: {p:.4f}")
```

Output: `chi-squared: 5.07, dof: 2, p: 0.0793`

Phase F: compute effect size. For chi-squared on a 2x3 table, the right effect size is Cramer's V:

```python
n = ct.values.sum()
cramers_v = (chi2 / (n * (min(ct.shape) - 1))) ** 0.5
print(f"Cramer's V: {cramers_v:.3f}")
```

Output: `Cramer's V: 0.065`

Cramer's V of 0.065 is in the "negligible-to-weak" range (0 to 0.1). The effect is small.

Phase G: confidence intervals for each conversion rate. For binary outcomes:

```python
from statsmodels.stats.proportion import proportion_confint
for variant in ["A", "B", "C"]:
    s = df.loc[df["variant"] == variant, "converted"]
    lo, hi = proportion_confint(s.sum(), len(s), method="wilson")
    print(f"{variant}: {s.mean():.3f} (95% Wilson CI [{lo:.3f}, {hi:.3f}])")
```

Output shows the CIs for A and C overlap slightly (A: [25.6, 34.7]; C: [32.9, 42.3]). The overall test is borderline (p = 0.079), the effect size is small, and the CIs overlap. The data does not yet support a confident "C is best".

Phase H: post-hoc pairwise tests (if the omnibus is significant or close, and the team wants to know which pairs differ). Run three pairwise two-proportions tests and apply Bonferroni correction (alpha / 3 = 0.0167):

```python
from statsmodels.stats.proportion import proportions_ztest
pairs = [("A", "B"), ("A", "C"), ("B", "C")]
for v1, v2 in pairs:
    s1 = df.loc[df["variant"] == v1, "converted"]
    s2 = df.loc[df["variant"] == v2, "converted"]
    z, p = proportions_ztest([s1.sum(), s2.sum()], [len(s1), len(s2)])
    print(f"{v1} vs {v2}: z={z:.2f}, p={p:.4f} (Bonferroni-adjusted alpha: 0.0167)")
```

Phase I: interpret. "Across 1200 users split across three onboarding variants, conversion rates were A=30.0%, B=35.0%, C=37.5%. A chi-squared test was borderline significant (chi^2 = 5.07, p = 0.079, Cramer's V = 0.065, a small effect). Pairwise tests with Bonferroni correction did not find any pair significantly different at the corrected alpha. The data is consistent with C being a modest improvement over A, but more data is needed to be confident. Recommendation: continue the test for another week and re-analyze, or ship C tentatively if the cost of being wrong is low."

The deltas from the t-test case: contingency-table description, Cramer's V instead of Cohen's d, post-hoc pairwise tests with multiple-testing correction, Wilson CIs instead of mean-difference CIs. The structural workflow is the same; the test choice and the effect-size measure change.

## Edge cases

1. **The two groups are not actually independent**: same users measured before and after, same items in two conditions. The right test is a paired test (paired t-test, Wilcoxon signed-rank), not an independent-samples test. The most common silent mistake in product analytics.

2. **The metric is bounded** (e.g., proportions, counts with a low max): the normal approximation breaks down at the edges. Use a proportions test or Poisson regression instead of a t-test on the raw values.

3. **The data has heavy ties** (rank-based test on a metric that takes only 5 distinct values): Wilcoxon and Mann-Whitney handle ties but can become anti-conservative. With many ties, prefer a permutation test.

4. **One group has zero variance** (everyone in the group has the same value): t-test is undefined. Surface the finding directly; the question is no longer statistical, it is about why one group is uniform.

5. **The metric is a ratio (clicks per impression, revenue per session)** where each unit has a different denominator: a naive mean-of-ratios is biased. Use a ratio test that handles the denominator correctly (delta method, or rebuild the unit of analysis at the user level).

6. **The sample contains far-tail outliers that move the mean dramatically**: the test on the raw mean reflects the outliers, not the typical user. Either pre-spec a winsorization rule, switch to a median-based test, or split the analysis into "typical" and "tail" segments.

## Anti-patterns

1. **Reporting p without effect size**: a p-value alone hides whether the effect matters. Always pair with d, V, r, or whatever effect size matches the test.

2. **Peeking at p during data collection and stopping when it drops below 0.05**: inflates the false-positive rate well above the nominal alpha. If you want sequential stopping, pre-register the bounds (e.g., O'Brien-Fleming).

3. **Multiple comparisons without correction**: running 20 sub-group tests and reporting the three with p < 0.05. Apply FDR or Bonferroni, or treat the analysis as exploratory.

4. **Misinterpreting the null**: "p = 0.12 means there is no effect" is wrong. It means the data did not provide strong evidence against the null at this sample size. Absence of evidence is not evidence of absence.

5. **Using Student's t-test when variances are unequal**: yields a biased p-value. Use Welch's t-test as the default; the cost when variances are equal is negligible.

## When to chain with

- **data-profiling**: run BEFORE the test so you know the distributions, skew, missingness, outliers. A test on un-profiled data is a test on guesses.
- **hypothesis-design**: when the test is confirmatory (driving a decision), the pre-registration locks in the test, alpha, and decision rule before any data is seen.
- **rag-eval-method**: the paired-Wilcoxon and bootstrap-CI pieces come from this skill, called by the retrieval-eval workflow.
- **notebook-to-production**: the analysis cell that ran the test should be lifted into a tested function. The test pins the expected output on a fixture.

The skill rarely begins a chain. It typically completes one (after data is collected, after the hypothesis is set).

## Decision tree

```
Is the question confirmatory (drives a binary decision) or exploratory (looking for patterns)?
  Exploratory  -> run, but mark all conclusions as suggestive
  Confirmatory -> ideally pre-registered; if not, mark as post-hoc in the writeup
        |
        v
What type is the metric?
  Continuous  -> t-test, ANOVA, regression family
  Binary      -> chi-squared, Fisher's, proportions-z
  Ordinal     -> Mann-Whitney, Kruskal-Wallis, ordinal regression
  Count/rate  -> Poisson regression, rate-ratio test
        |
        v
How many groups?
  One vs reference  -> one-sample t-test
  Two               -> t-test (Welch's by default), or non-parametric variant
  Three or more     -> ANOVA / Kruskal-Wallis; with post-hoc if significant
        |
        v
Are observations independent?
  Yes -> standard tests
  No  -> paired test (paired t / Wilcoxon) OR mixed-effects model for clustering
        |
        v
Are assumptions met (normality, equal variance, expected counts)?
  Yes -> proceed with chosen test
  No  -> switch to non-parametric OR transform the metric OR fit a robust model
        |
        v
Run, compute effect size, compute CI, multiple-testing correct if relevant
        |
        v
Write up: hypothesis, test, result (effect size + CI + p), interpretation, caveats
```

## Output schema

The skill produces a markdown writeup plus a code artifact.

**Primary artifact: the analysis writeup.** Path convention: `reports/analyses/<YYYY-MM-DD>-<analysis-slug>.md`, or as a notebook markdown cell when the analysis lives in a notebook.

Required sections, in order:

1. Header (date, owner, status = confirmatory or exploratory).
2. `## Hypothesis` (H0 and H1 stated explicitly; reference to pre-registration if applicable).
3. `## Data` (source path, n per group, missingness summary, exclusions applied).
4. `## Assumption checks` (normality, equal variance, independence; with values).
5. `## Test` (test family, statistic, p-value, degrees of freedom where applicable).
6. `## Effect size` (Cohen's d / Cramer's V / Pearson r / etc., with the interpretation).
7. `## Confidence interval` (CI for the effect size or the mean difference, with method).
8. `## Multiple-testing correction` (only if multiple tests were run; method and adjusted p-values).
9. `## Interpretation` (plain-language paragraph for the decision-maker).
10. `## Caveats` (assumption violations, post-hoc nature, sample-size limits).

**Secondary artifact: the code.** A `.py` script or a notebook cell that runs the test on the input data and reproduces the numbers in the writeup. Path: `notebooks/<date>-<slug>.ipynb` or `scripts/analysis_<slug>.py`. Committed alongside the writeup.

**Optional artifact: a visualization.** One chart that supports the test (boxplot for t-test, bar chart with CI for chi-squared, scatter with regression line for correlation). Saved to `reports/figures/<date>-<slug>.png`.

**Chat reply summarizes:**

- The test, the result (effect size + CI + p), and the decision.
- Any caveats the decision-maker needs to hear.

Word count target for the writeup: 200 to 500 words. The numbers do the talking; the prose explains what they mean.

## Quality checks before delivery

Walk through these before handing the analysis to the user or to a stakeholder:

1. **Is the hypothesis stated as it was BEFORE the test ran?** If the writeup says "we wanted to test whether X" but the actual question was different until you saw the data, mark the analysis as exploratory.
2. **Is the test choice defended?** "Welch's t-test because variances were unequal (Levene p = 0.02)" is defensible. "T-test because that is what we usually use" is not.
3. **Is the effect size reported alongside the p-value?** Always. If the writeup leads with p, rewrite to lead with effect size.
4. **Is the CI for the effect provided?** A p-value tells you something is detectable; a CI tells you how big it might be. Both matter.
5. **Did you apply multiple-testing correction where relevant?** If you ran more than one test, report all of them and use FDR or Bonferroni. Selective reporting is unintentional p-hacking.
6. **Does the interpretation explain in plain language what the result means for the decision?** A stakeholder should not need a stats degree to read the conclusion.

If any check fails, rewrite before delivering. An analysis that surfaces the wrong number or hides the wrong caveat misleads the decision-maker, which is worse than no analysis.

## Limits

The skill produces frequentist NHST results. Bayesian estimation (PyMC, numpyro, Bambi) is a different paradigm and is not covered in depth. Use it when the team prefers posterior probabilities to p-values, or when a hierarchical model is the right shape for the question.

The skill assumes the data has already been collected. Pre-data design questions (sample size, MDE, alpha) belong to `hypothesis-design`. Mixing the two confuses the team about which discipline applies when.

The skill does not handle causal-inference questions (treatment effects in observational data, instrumental variables, regression discontinuity, difference-in-differences). Those require a different toolchain (econometrics, causal graphs) and different skepticism about identifying assumptions. For confirmatory causal claims, escalate to a causal-inference specialist or the relevant published guides.

The skill does not validate the data pipeline. If the upstream pipeline silently dropped rows or mislabeled the group, the test will faithfully run on the wrong data. Profile the data with `data-profiling` first to reduce the risk.

## Quick test selection reference

A compressed version of the decision tree as a lookup table. Useful when you know the design and just want the test name.

| Comparison                           | Metric type   | Design           | Default test               | Effect size  |
|--------------------------------------|---------------|------------------|----------------------------|--------------|
| Two-group, independent               | Continuous    | Independent      | Welch's t-test             | Cohen's d    |
| Two-group, independent               | Continuous    | Heavily skewed   | Mann-Whitney U             | rank-biserial r |
| Two-group, paired                    | Continuous    | Paired           | Paired t-test              | Cohen's d (paired) |
| Two-group, paired                    | Continuous    | Non-normal diff  | Wilcoxon signed-rank       | rank-biserial r |
| Three+ groups, independent           | Continuous    | Independent      | One-way ANOVA / Welch's    | eta-squared  |
| Three+ groups, independent           | Continuous    | Non-normal       | Kruskal-Wallis             | epsilon-squared |
| Three+ groups, repeated measures     | Continuous    | Repeated         | RM-ANOVA (Mauchly)         | partial eta-squared |
| Two-group, independent               | Binary        | Independent      | Chi-squared / Fisher's     | Cramer's V / phi |
| Two-group, paired                    | Binary        | Paired           | McNemar's test             | odds ratio   |
| Two categorical                      | Categorical   | Independent      | Chi-squared                | Cramer's V   |
| Two continuous                       | Continuous    | Linear           | Pearson correlation        | Pearson r    |
| Two continuous                       | Continuous    | Monotonic        | Spearman correlation       | Spearman rho |
| Time series, two regimes             | Continuous    | Sequential       | Change-point detection     | varies       |

Use the table to confirm your test choice. If the table does not list the design (mixed-effects models, hierarchical models, survival analysis), the skill points you to specialized tooling.

## Reporting templates

When the audience is a non-statistician, the writeup follows a fixed shape:

```
We compared <thing A> and <thing B> on <metric> using <test>.
The difference was <effect direction> by <effect size with CI>.
This was <statistically significant / not> at p=<p-value>, alpha=<alpha>.
The effect is <small / medium / large / negligible> by <effect-size measure> conventions.
Recommendation: <ship / do not ship / collect more data / investigate>.
Caveats: <pre-registration status / multiple testing / assumption violations>.
```

For a stats-literate audience, the writeup is the same but with the assumption checks and the test choice rationale inline.

For an executive audience, drop the test name and lead with the effect and the decision: "Variant C converts ~7% better than A; ship C." The full analysis stays in the writeup for whoever wants to audit it.
