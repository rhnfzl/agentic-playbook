---
name: hypothesis-design
description: Use when the user wants to design an experiment before collecting data (articulate the null and alternative hypotheses, pick a statistical test, compute the required sample size, define stopping criteria, write a short pre-registration).
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, experiment-design, pre-registration, power-analysis, statistics]
scope: [research]
---

# Hypothesis Design

What this gets you: a short pre-registration document for an experiment that fixes the hypothesis, the test, the sample size, and the stopping rule before any data is collected. The output stops the experiment from drifting into HARKing (hypothesizing after the result is known) and stops the team from running a stat-underpowered study that cannot detect the effect it is looking for.

The discipline this skill enforces: decide what would convince you before you look at the data. That single rule prevents most of the failure modes in experimental research.

## When NOT to use this skill

- The user has already collected data and wants to run a test on it. Use `skills/research/statistical-analysis/`. This skill is pre-data only.
- The user wants exploratory analysis (no hypothesis, just looking for patterns). Use `skills/research/data-profiling/`. Pre-registration is meaningful only for confirmatory work.
- The user is running a Bayesian sequential study with optional stopping built into the design. Power analysis is different; use the skill body's pointers and switch to a Bayesian planning tool.
- The experiment is a one-off observational study with no comparison. Pre-registration adds little value when there is no test to fix.

## Inputs you need from the user

Confirm in one short exchange:

1. **The research question** in plain language ("Does the new prompt improve answer accuracy?").
2. **The unit of analysis** (a query, a user, a session, a code commit).
3. **The metric** that will measure the outcome and its expected distribution shape (binary, continuous, ordinal).
4. **The expected effect size** the team cares about (in metric units, not standardized). If unknown, pull from prior work or pilot data.
5. **The cost of one observation** (time, money, or risk). Influences how strict the alpha should be.
6. **The decision the experiment will inform** (ship, do not ship, learn, escalate).

If the user does not have an expected effect size, run a small pilot (10 to 50 observations) first, estimate, then come back for the power analysis.

## Workflow

### Step 1: State the hypotheses

Two flavors. Write both explicitly:

**Null hypothesis (H0)**: the boring outcome. The thing you would believe if no effect existed.

**Alternative hypothesis (H1)**: the interesting outcome. What you would believe if the data showed the effect.

Example:

> H0: the new prompt produces the same accuracy as the current prompt on our eval set (mean difference = 0).
> H1: the new prompt produces higher accuracy (mean difference > 0).

Decide whether H1 is one-sided ("higher", "lower") or two-sided ("different"). Most product-driven hypotheses are one-sided. Most scientific hypotheses are two-sided. Default to two-sided unless the team has a strong directional reason.

### Step 2: Pick the statistical test

Pick the test before the data, based on metric type and design. See `skills/research/statistical-analysis/` for the full decision tree. Common cases:

- Two-group continuous metric, independent: Welch's t-test.
- Two-group continuous metric, paired (same items, two conditions): paired t-test.
- Two-group binary metric: chi-squared or Fisher's exact (small n) or proportions z-test.
- Multi-group continuous: one-way ANOVA.
- Multi-group with covariates: regression with a treatment indicator.
- Ratio of rates (events per unit time): rate-ratio test (Poisson family).

If the design is novel, name the test and the assumptions. "We will fit a hierarchical Bayesian model with a treatment indicator" is fine if the team can actually do it.

### Step 3: Define the effect size of interest

Translate the product question into a number. "Does the new prompt improve accuracy?" needs a numeric answer to "by how much would we care?":

- A 1% relative improvement might be too small to matter (or might be huge, depending on baseline).
- A 5% absolute improvement might be the minimum that changes a roadmap decision.

This is the **minimum detectable effect (MDE)**: the smallest effect you want the experiment to detect with high confidence. Smaller MDE means larger sample size. Set MDE based on:

- What change would influence the decision (the business-meaningful threshold).
- What change is realistic given the intervention (the effect-size literature suggests).
- What change is detectable given budget (you may not be able to detect 0.1 percentage points).

Document the MDE explicitly. A study designed for a 5% MDE that observes a 2% effect is not underpowered; it is a study that successfully concluded "the effect, if any, is smaller than we care about."

### Step 4: Set alpha, beta, and power

Three threshold knobs:

- **Alpha**: the false-positive rate. Default 0.05 for two-sided tests, 0.025 for one-sided. Lower (0.01) for high-stakes decisions, higher (0.10) only when the cost of a missed effect dominates.
- **Beta**: the false-negative rate. Default 0.20.
- **Power**: 1 minus beta. Default 0.80. Means: if the true effect is at least MDE, the test has 80% chance of detecting it.

If the experiment will inform a costly decision (a major architecture change, a model rollback), tighten alpha to 0.01 and bump power to 0.90. Document the choice.

### Step 5: Compute the sample size

For two-group continuous comparison (t-test):

```python
from statsmodels.stats.power import TTestIndPower
analysis = TTestIndPower()
n_per_group = analysis.solve_power(
    effect_size=0.3,    # Cohen's d for the MDE
    alpha=0.05,
    power=0.80,
    ratio=1.0,
    alternative="two-sided",
)
print(f"n per group: {n_per_group:.0f}")
```

Cohen's d = (mean1 - mean2) / pooled_std. If you have a baseline std but no idea of the difference, you cannot compute d without choosing an MDE in std units. Common shortcut: use the literature's "small / medium / large" buckets (0.2 / 0.5 / 0.8). Better: compute d using the actual baseline std and the MDE in raw units.

For two-group proportions (binary outcome):

```python
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize
es = proportion_effectsize(0.10, 0.13)  # baseline 10%, MDE +3pp absolute
analysis = NormalIndPower()
n_per_group = analysis.solve_power(effect_size=es, alpha=0.05, power=0.80)
print(f"n per group: {n_per_group:.0f}")
```

For multi-group ANOVA, paired tests, or non-parametric tests, `statsmodels.stats.power` and `pingouin` cover the common cases. For more exotic designs (hierarchical, clustered), use simulation (run 1000 synthetic experiments at varying n, see when power crosses 0.80).

Buffer the result: add 10% to 20% to the computed n to absorb attrition, exclusions, and the inevitable observation loss.

### Step 6: Define the stopping rule

A pre-defined stopping rule is what separates an experiment from a fishing expedition. Three patterns:

**Fixed n**: collect exactly N observations, then stop and analyze. Simplest. Default for most cases.

**Sequential with bounded looks**: pre-specify K interim looks at the data, with adjusted alpha (e.g., O'Brien-Fleming bounds). Allows early stopping for efficacy or futility without inflating alpha. Useful when each observation is expensive.

**Bayesian sequential**: stop when the posterior probability of an effect exceeds a threshold. Different framework; do not mix with frequentist stopping.

Anti-pattern: peeking at the data and stopping when the result looks good. This inflates the false-positive rate from 0.05 to often greater than 0.20. If the team wants to peek, build the sequential design from the start and adjust alpha accordingly.

### Step 7: Define exclusion criteria

What observations will be excluded from the analysis, decided before looking at the data:

- Data quality filters (missing values, timeouts, errors).
- Population filters (only users in regions A and B).
- Time filters (only sessions in the last 90 days).

Exclusions discovered after seeing the data are post-hoc and undermine the pre-registration. Define them up front, including the expected exclusion rate.

### Step 8: Define the primary analysis

The exact analysis that will be run once data is collected:

- The test (Welch's t-test, two-sided, alpha=0.05).
- The variable (mean accuracy on the eval set).
- The grouping (control vs treatment, defined by the random assignment).
- The handling of exclusions and missing data.
- The effect-size measure (Cohen's d, with 95% CI).

If there will be secondary analyses (subgroup effects, sensitivity analyses), label them as secondary. The primary analysis is the one that drives the decision.

### Step 9: Write the pre-registration

Output is a short document committed before data collection starts. Template:

```markdown
# Pre-registration: <experiment name>

Date: 2026-05-24
Owner: <name>
Status: pre-registered (no data collected yet)

## Research question
Does the new prompt template improve answer correctness on the customer-support
RAG eval relative to the current production prompt?

## Hypotheses
- H0: mean correctness (new) = mean correctness (current)
- H1: mean correctness (new) > mean correctness (current)
  (one-sided; the decision is whether to ship the new prompt)

## Design
- Unit: an eval query
- Conditions: each of the 400 queries answered by both prompts (paired design)
- Random assignment: not applicable; both prompts run on the same queries
- Blinding: graders are blind to which prompt produced which answer

## Primary metric
- Correctness, scored 0 to 1 by an LLM judge with the v3 rubric
- Per-query difference (new minus current), averaged across queries

## Statistical test
- Paired t-test (one-sided), alpha = 0.025
- Effect size: Cohen's d on the per-query differences, with 95% CI

## Sample size
- 400 paired queries, computed for MDE = 0.05 (5pp absolute), alpha = 0.025, power = 0.80
- Buffer of 50 queries planned in case of LLM-judge timeouts

## Stopping rule
- Fixed n. Collect all 400 query pairs, analyze once, then decide.

## Exclusions (pre-specified)
- Queries where either prompt's response timed out (expected rate: <2%)
- Queries flagged by safety filter (expected rate: <1%)

## Decision rule
- Ship the new prompt if p < 0.025 AND Cohen's d >= 0.2
- Do not ship if p >= 0.025
- Investigate further if p < 0.025 but d < 0.2 (statistically significant, practically tiny)

## Secondary analyses (exploratory, do not drive decision)
- Per-topic subgroup analysis (finance, healthcare, retail)
- Failure-case clustering on the LLM judge rationales

## Deviations
- None as of pre-registration date. Any deviation from this plan will be logged here
  before the analysis is run.
```

Commit the file. The act of commit (with a timestamp) is the pre-registration. Public registries (OSF, AsPredicted) exist for formal contexts; for internal research, a versioned doc in the repo is enough.

### Step 10: Run, then write up

After data collection, run the exact analysis specified. Use `skills/research/statistical-analysis/` for the test, the effect size, and the writeup. The writeup must reference the pre-registration and call out any deviations.

If during the run a deviation became necessary (the chosen test does not apply because an assumption was violated), document the deviation honestly. Pre-registration is about transparency, not about handcuffing the analyst.

## Common pitfalls

- **Choosing MDE based on what is detectable rather than what matters**: yields underpowered tests that "find" tiny effects.
- **Vague hypotheses**: "the new system is better" is not a hypothesis. "Mean correctness is higher by at least 5pp" is.
- **Skipping the stopping rule**: peeking and stopping when results look good is the second most common form of accidental p-hacking.
- **Treating exploratory subgroup analyses as confirmatory**: if it was not pre-specified, it is exploratory and the p-value is suggestive, not conclusive.
- **Pre-registering then ignoring it**: if the writeup does not reference the pre-registration, the discipline does not work.
- **Using rule-of-thumb effect sizes (0.5 = medium) when a domain-specific MDE is available**: the rules of thumb were never meant as universal.

## Output shape

A markdown pre-registration document committed to the repo at a stable path (suggest `docs/preregistrations/YYYY-MM-DD-<slug>.md`). Plus a chat reply summarizing the hypothesis, the sample size, the test, and the decision rule. Plus a notebook cell or Python snippet with the power calculation so the user can rerun it if parameters shift.

## Sources

- Springer, "Preregistration in practice: A comparison of preregistered and non-preregistered studies in psychology" (2024), https://link.springer.com/article/10.3758/s13428-023-02277-0
- Embassy Science, "Statistical pre-registration" (2026), https://embassy.science/wiki/Theme:349f9eb9-b796-46cb-9a98-214c06db9046
- Kameleoon, "What is a power analysis?" practical guide
- General prior art: Center for Open Science (osf.io) pre-registration templates; Cohen (1988) statistical power tables

## Pre-flight checklist

Before invoking this skill, confirm:

1. **No data has been collected yet on this question.** If data exists, the right move is `statistical-analysis`, not pre-registration. Pre-registering an analysis after seeing the data is performative; it does not get the discipline benefit.
2. **The decision has a meaningful binary outcome** (ship, do not ship, learn, escalate). Pre-registering an open-ended "what is going on here?" exploration is a waste; that is what exploratory analysis is for.
3. **The team is willing to honor the plan.** If the user is going to tweak the analysis after seeing the data anyway, the pre-registration is theater. Push back kindly.
4. **There is enough budget to collect the computed sample size.** If you cannot collect enough observations to detect the effect, either lower the MDE, accept lower power, or escalate the decision.
5. **The metric is operationalizable.** "Customer satisfaction" is not a metric until someone says "we mean the average of the post-call rating, on the 1 to 5 scale, computed across all calls in the last 30 days, excluding test calls."

If two or more of these fail, propose an alternative (run a pilot, redefine the metric, do an exploratory pass first) before forcing a pre-registration.

## Second worked example: A/B test on a binary product metric

The first worked example (paired t-test on LLM prompts) showed a paired-design pre-registration. Here is the contrasting case: an A/B test on a binary product metric with random assignment at the user level.

Scenario: the product team wants to test whether a new onboarding flow increases the fraction of new signups that complete their first transaction within 7 days. Current baseline is 18%; the team wants to detect a +3 percentage-point lift or larger.

Phase A: state the hypothesis precisely. The metric is "first-transaction-within-7-days", a binary per-user outcome. The unit of analysis is a user (not a session, not a visit). H0: p_treatment = p_control. H1: p_treatment > p_control (one-sided, because the team will not ship a flow that hurts the metric).

Phase B: set the parameters. Baseline p_control = 0.18. MDE in absolute terms = 0.03 (so detect p_treatment >= 0.21). Alpha = 0.025 (one-sided equivalent of 0.05 two-sided). Power = 0.80. The product team is happy with the conventional choices because the rollout cost is moderate.

Phase C: compute the sample size for a proportions test.

```python
from statsmodels.stats.power import NormalIndPower
from statsmodels.stats.proportion import proportion_effectsize
es = proportion_effectsize(0.18, 0.21)
analysis = NormalIndPower()
n_per_group = analysis.solve_power(effect_size=es, alpha=0.025, power=0.80, alternative="larger")
print(f"n per group: {n_per_group:.0f}")
```

The result is roughly 2300 users per group, so 4600 total. The team gets about 800 new signups per day, so collecting the sample takes about 6 days. Add a 20% buffer for users who never complete onboarding (excluded by pre-spec), and budget 8 days of collection.

Phase D: random assignment plan. Each new signup is assigned uniformly at random to control or treatment, using a hash of `user_id` modulo 2. The hash is deterministic so re-assignments are stable if the user retries onboarding. Document the hash function and the seed.

Phase E: stopping rule. Fixed n at 4600 (2300 per group). No interim analysis. The team is tempted to peek after day 3, but peeking inflates alpha. If they want to peek, the design needs to change to a sequential design with adjusted alpha (e.g., O'Brien-Fleming with 2 looks).

Phase F: exclusions. Pre-specify:

- Users whose signups are flagged by the fraud system (excluded; not real users).
- Users who land on a landing page A / B that runs an unrelated test (excluded; confounded).
- Users in markets where the new flow has not been localized (excluded; flow does not apply).

Expected exclusion rate: 5 to 8% based on past data.

Phase G: decision rule. Ship the new flow if p < 0.025 AND the observed lift is at least +2 pp (so the lower CI bound is roughly +0 or better). The MDE was set at +3 pp; observing exactly +3 pp at p = 0.024 would ship. Observing +1 pp at p = 0.04 would not, because the effect is below the meaningful threshold even if statistically detectable in the next run.

Phase H: secondary analyses (exploratory). Per-channel breakdown (organic vs paid), per-device breakdown (web vs mobile app). These do not drive the ship decision but inform follow-up work.

Phase I: write the pre-registration doc, commit it. Run the experiment for 8 days. Compute the primary test. Honor the decision rule.

The deltas from the paired-t-test case: independent samples (not paired), proportions test (not t-test), random assignment plan (not "same items both conditions"), and exclusion criteria specific to the user funnel. The structural workflow is identical; only the test choice and the assignment plan differ.

## Edge cases

1. **The effect is in a sub-population, not the overall population**: pre-registering an overall-effect test and then "discovering" the sub-population effect is HARKing. Either pre-register the sub-population as the primary analysis, or pre-register it as secondary and accept that the finding is suggestive, not confirmatory.

2. **The metric is heavily right-skewed (e.g., revenue per user)**: a t-test on the raw values is dominated by the tail. Pre-register the transformation explicitly (e.g., log-revenue, or a Mann-Whitney U on the raw scale) so the analyst does not get to pick the convenient one after the fact.

3. **The unit of analysis is clustered (multiple observations per user, multiple users per organization)**: ignore clustering and the test becomes anti-conservative. Pre-register a cluster-robust standard error or a mixed-effects model. The sample-size calculation also needs to inflate by the design effect.

4. **The treatment is rolled out gradually (not all at once)**: time-varying confounders contaminate the comparison. Either run the test on the first day of full rollout, or model time explicitly. Pre-register the time-window before any data is collected.

5. **The team has run pilots and has prior data**: this is good news, not bad. Use the pilot data to refine the baseline estimate and the variance estimate. The pre-registration explicitly cites the pilot ("based on pilot data 2026-04, baseline std = 0.12") so reviewers can audit the assumption.

6. **The cost of an observation is dropping fast (e.g., the team can collect 10x more data next week)**: tempting to delay, but the longer the wait, the more the world changes around the experiment. Run the test on the budget available now, then run a confirmatory test if the result is borderline.

## Anti-patterns

1. **Pre-register, then "adjust" the plan after the data comes in**: at this point you are doing post-hoc analysis pretending to be confirmatory. If the plan was wrong, say so in the deviations section; do not silently change it.

2. **Skip the power analysis because "we have lots of data"**: lots of data does not mean enough data for the effect size you actually care about. A 100k-user A/B test is dramatically underpowered for a +0.1pp lift if the baseline rate is 0.5%.

3. **Pre-register only the primary metric and ignore guardrail metrics**: shipping a treatment that improves the primary metric while tanking a guardrail (latency, error rate, churn) is worse than no change. Pre-register the guardrails as ship-blocking secondary metrics.

4. **Conflate "statistical significance" with "decision evidence"**: p < 0.05 is necessary but not sufficient. The decision rule needs the effect-size threshold and the CI bounds.

5. **Treat alpha = 0.05 as a law of nature**: alpha is a knob that trades false positives against false negatives. For high-stakes decisions, tighten it. For exploratory triage, loosen it. The default exists so you have something when there is no reason to deviate, not because it is correct.

## When to chain with

- **data-profiling**: run on the historical data BEFORE designing the experiment so the baseline rate and variance are real, not assumed. A pre-registration based on guessed parameters is half a pre-registration.
- **literature-synthesis**: if the question has been studied before, the prior effect-size estimate from the literature beats a guess. Run a 30-minute synthesis to anchor the MDE.
- **statistical-analysis**: the post-hoc partner. Once the data is collected, the analyst runs the exact test pre-specified, then writes up.
- **rag-eval-method**: when the experiment IS a retrieval-quality eval, pair this skill with the eval method so the labeled query set size matches the power calc.
- **notebook-to-production**: the pre-registration is a doc, but the power-analysis code lives in a script. Productionize the power-calc snippet so the team can re-run with new parameters.

The skill is rarely a terminal step. It is the contract that other skills then execute against.

## Decision tree

```
Has any data been collected on this question?
  Yes -> use statistical-analysis, do NOT pre-register post-hoc
  No  -> continue
        |
        v
Is there a clear binary decision the test will inform?
  No  -> use exploratory analysis instead
  Yes -> continue
        |
        v
Is the metric operationalizable today?
  No  -> resolve the metric definition before pre-registering
  Yes -> continue
        |
        v
Does the team have an effect-size estimate (literature, pilot, intuition)?
  No  -> run a small pilot (10 to 50 obs), then return
  Yes -> continue
        |
        v
Can you afford the computed sample size?
  No  -> raise MDE OR lower power OR escalate the decision
  Yes -> continue
        |
        v
Is the design simple (two-group, fixed n) or complex (sequential, clustered, hierarchical)?
  Simple  -> standard 10-step workflow
  Complex -> add interim look bounds OR mixed-effects model spec to the pre-registration
        |
        v
Commit the pre-registration doc before collecting any data
```

## Output schema

The skill produces a single committed pre-registration document. Path convention: `docs/preregistrations/YYYY-MM-DD-<slug>.md`. The slug is a short, kebab-case description of the question.

Required sections, in order:

1. Header (date, owner, status = `pre-registered (no data collected yet)`).
2. `## Research question` (one paragraph, plain language).
3. `## Hypotheses` (H0 and H1, explicit and operational).
4. `## Design` (unit of analysis, conditions, random assignment, blinding).
5. `## Primary metric` (definition, scoring rubric, aggregation).
6. `## Statistical test` (test family, alpha, tail).
7. `## Sample size` (n, computed for what MDE, alpha, power; buffer if any).
8. `## Stopping rule` (fixed, sequential with bounds, Bayesian).
9. `## Exclusions (pre-specified)` (criteria and expected rates).
10. `## Decision rule` (the exact thresholds for ship / do not ship / investigate).
11. `## Secondary analyses (exploratory, do not drive decision)` (subgroup analyses, guardrail metrics).
12. `## Deviations` (initially empty; updated honestly during execution).

The chat reply summarizes:

- The hypothesis in one sentence.
- The sample size (n) and the rationale (for MDE = X with power = Y).
- The test choice and why.
- The decision rule (one sentence).

The accompanying Python snippet (committed alongside the doc, or inline in the doc as a code block) re-runs the power calculation. The snippet is what survives a parameter change; the doc captures the original assumption.

Word count target: 400 to 800 words for the doc. Longer if the design is unusually complex (e.g., hierarchical with interim looks). Shorter is fine if the test is the textbook Welch t-test on a single metric.

## Quality checks before delivery

Walk through these before committing the pre-registration:

1. **Is the hypothesis falsifiable?** "The new prompt is better" is not. "Mean correctness is at least 5pp higher on the eval set" is. The hypothesis must reduce to a number the test can produce.
2. **Is the MDE meaningful, not just detectable?** A 0.1pp MDE on a 10pp baseline is technically detectable with enough n but uninteresting. The MDE should be the smallest change that would influence the decision.
3. **Is the test correctly matched to the metric type?** Continuous metric -> t-test or Welch's; binary -> proportions or chi-squared; counts -> Poisson. A wrong test produces a wrong p-value.
4. **Is the stopping rule explicit and respected?** "Fixed n at 4600" or "sequential with 2 looks using O'Brien-Fleming bounds". No peeking that is not in the rule.
5. **Are the exclusion criteria pre-specified with expected rates?** Surprise exclusions after seeing the data are post-hoc and undermine the pre-registration.
6. **Does the decision rule include both significance AND effect-size threshold?** A pre-registration that ships on p alone is broken; it cannot distinguish a meaningful effect from a tiny detectable one.

If any check fails, fix before committing. A flawed pre-registration is worse than none because it lends false discipline to a sloppy plan.

## Limits

The skill assumes the team will honor the plan. If the analyst plans to "see what the data says" and adjust the analysis afterwards, the pre-registration is theater. The discipline only works if the team commits to the contract.

The skill produces a frequentist NHST plan by default. Bayesian, sequential, and hierarchical designs are mentioned but the skill does not deeply walk through them. For complex designs (multi-level models with multiple grouping factors, structural equation models), the analyst should consult a statistician or a Bayesian planning tool in addition to this skill.

The power calculation depends on the analyst's effect-size guess. If the guess is wrong (because no pilot was run or the prior literature is misleading), the experiment can be underpowered even though the math looks correct. Build a small pilot first whenever possible.

The pre-registration is a contract with future-you, not a magic shield against bias. Honest deviations are recorded in the deviations section. Hidden deviations defeat the purpose.

## Worked sample-size table

For two-group comparisons with default alpha (0.05 two-sided) and power (0.80), the sample size per group depends on the standardized effect size. Useful anchors for intuition:

| Cohen's d | Interpretation | n per group |
|-----------|----------------|-------------|
| 0.1       | tiny           | ~1570       |
| 0.2       | small          | ~393        |
| 0.3       | small-medium   | ~175        |
| 0.5       | medium         | ~64         |
| 0.8       | large          | ~25         |

The takeaway: detecting small effects requires large samples. If the team cares about a 0.2 effect, plan for n ~400 per group. If they only care about 0.5, n ~64 is enough. Use this table to calibrate intuition before committing to a costly data collection.

For binary outcomes, the equivalent table depends on the baseline rate. At baseline 0.10 with MDE +0.05 absolute (so 10% to 15%), n per group is roughly 480. At baseline 0.50 with the same MDE (50% to 55%), n per group is roughly 1500 because variance is higher near 0.50.

These numbers are not contracts; they are calibration. The actual power calc uses the team's specific MDE, baseline, alpha, and power.

## Common pre-registration mistakes from team retrospectives

Patterns that have shown up in past pre-registration reviews:

1. **MDE set by sample-size budget, not by what matters**: "we have data for 200 users, so we will use the MDE that detects at n=200". This inverts the logic. Set MDE first based on the decision; if the sample size is impractical, escalate before collecting.

2. **"Primary metric" with three competing primary metrics**: there is no such thing as three primary metrics. Pick one; the others are secondary. Multiple primary metrics multiply false-positive risk.

3. **Stopping rule "we will stop when we have enough data"**: not a rule. A stopping rule is a fixed n, a sequential plan with bounds, or a Bayesian posterior threshold. "When we have enough" lets the team peek and stop opportunistically.

4. **Exclusion criteria that conveniently exclude the unusual high-treatment-effect rows**: post-hoc exclusion. Pre-specify the criteria up front, including the expected exclusion rate.

5. **No deviations section because "we will follow the plan exactly"**: deviations happen; pretending they will not undermines honesty. Include the section empty, fill it during execution if needed.

## Tooling notes

The skill uses:

- **statsmodels** for the power calculation (`TTestIndPower`, `NormalIndPower`, `FTestAnovaPower`).
- **scipy** for distribution functions used in alpha / beta calculations.
- **numpy** for any simulation-based power calc (when the design is complex enough that the closed-form formulas do not apply).
- A plain text file (markdown) as the pre-registration artifact, committed alongside the analysis code.

Optional but recommended:

- **pingouin** for power calculations on less common designs (ANCOVA, mediation analysis).
- **OSF or AsPredicted** for formal external pre-registration when the audience extends beyond the team.

The skill does not need a heavy compute environment. Power calculations run in seconds. The discipline is in the writing, not the computation.

## Re-using the pre-registration

Once committed, the pre-registration is a contract that other skills execute against:

- **statistical-analysis** runs the exact test specified, reports the result, and notes any deviations.
- **rag-eval-method** treats the pre-registration's sample size, ship threshold, and decision rule as inputs.
- **notebook-to-production** lifts the power-calc snippet into a script so the team can re-run with new parameters.

The pre-registration's life cycle:

1. Designed (this skill).
2. Committed before any data is collected.
3. Referenced by the analysis when data is in.
4. Closed out with a writeup that compares plan to outcome, including honest deviations.

A pre-registration that is created but never referenced is theater. The downstream reference is what makes the discipline real.

## Worked sensitivity analysis

Before committing the pre-registration, run a sensitivity check on the sample size:

| Parameter           | Plan        | Optimistic  | Pessimistic |
|---------------------|-------------|-------------|-------------|
| Baseline rate       | 0.18        | 0.16        | 0.20        |
| MDE (absolute)      | +0.03       | +0.04       | +0.02       |
| Alpha               | 0.025       | 0.05        | 0.01        |
| Power               | 0.80        | 0.80        | 0.90        |
| n per group         | 2300        | 1450        | 5800        |

A 50% increase in the n estimate (from 2300 to 5800) under pessimistic assumptions tells the team how risky the budget is. If the optimistic-only number fits the budget but the pessimistic does not, the project is at risk.

The sensitivity table is optional but recommended for high-stakes pre-registrations. It surfaces the budget risk before the experiment commits.

## Anti-fragile pre-registration

A well-designed pre-registration absorbs surprises without compromising integrity. Patterns that make it anti-fragile:

1. **Pre-specify a robustness analysis**: in addition to the primary test, pre-specify one or two robustness checks (different exclusion rule, different time window). If the primary and the robustness analyses agree, the result is stronger; if they disagree, the surprise is informative.

2. **Pre-specify what would change the conclusion**: "if MDE assumption is off by 50%, the conclusion would be...". This forces the analyst to think about boundary conditions before the data arrives.

3. **Pre-specify the writeup template**: a one-pager template the analyst fills in after the data is collected. The template constrains the analyst to the planned analyses; freeform writeups invite scope creep.

4. **Pre-specify the decision-maker**: who reads the writeup and makes the ship / do not ship call. Without a named decision-maker, the result floats and the discipline degrades.

Anti-fragile pre-registrations cost an extra 15 to 30 minutes upfront and save days of post-hoc argumentation. The cost-benefit tilts strongly toward doing them.
