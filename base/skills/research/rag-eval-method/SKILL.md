---
name: rag-eval-method
description: Use when the user wants to evaluate the retrieval quality of a RAG system (encode documents, build an index, run queries, score with recall@k, MRR, NDCG, and report a defensible number, not vibes).
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, rag, retrieval, evaluation, metrics]
scope: [research]
---

# RAG Eval Method

What this gets you: a reproducible retrieval-quality measurement on a RAG system. The output is a small report with recall@k, MRR, and NDCG@k computed on a labeled query set against a real index, plus a per-query failure list a teammate can use to triage the worst cases. The number is the answer to "is the retriever good enough?", not "is the LLM hallucinating?" (that is generation eval, a separate question).

A 2026 RAG eval program tracks at least one retrieval-stage metric and at least one generation-stage metric. This skill covers the retrieval stage only. If the user wants end-to-end answer quality, pair this with a generation eval (faithfulness, answer correctness) afterward.

## When NOT to use this skill

- The user wants to evaluate the generation stage (faithfulness, answer relevance). Different skill, different tooling (RAGAS, FutureAGI, custom LLM-as-judge).
- The user has no labeled relevance judgments at all. Build a small labeled set first (Step 2). Eval without labels is just vibes.
- The user wants to A/B test two retrievers in production. Use the production eval harness (likely an MCP tool or a tracing platform), not this offline eval.
- The user has fewer than 20 labeled queries. The metrics will be too noisy to be informative. Either label more queries first or accept that you are doing a smoke test, not an evaluation.

## Inputs you need from the user

Confirm in one short exchange (do not ask one at a time):

1. **Document corpus**: where the documents live (a directory, a vector DB, a list of strings).
2. **Query set**: a list of queries with at least one labeled-relevant document each. JSONL or CSV is fine.
3. **Retriever to evaluate**: BM25, a specific embedding model, a hybrid stack, etc. If the user is comparing several, evaluate each separately and produce a comparison.
4. **Top-k values to report at**: defaults `[1, 3, 5, 10, 20]`. Match what production uses.
5. **Where to write the report**.

If the query set is missing or incomplete, build a labeled set first (see Step 2). Skip the eval until labels exist.

## Workflow

### Step 1: Frame the eval question

Before any code, write down what the eval will answer. Example:

> "On our 200-query labeled set, does the new bge-large-en-v1.5 embedder with FAISS HNSW retrieve at least 0.80 recall@10 and at least 0.65 NDCG@10? If yes, we ship. If no, we investigate failure cases by category."

The eval has a binary outcome (ship or investigate). If the eval cannot produce a binary outcome, it will not influence the decision.

### Step 2: Build (or audit) the labeled query set

A labeled query set has, for each query, a list of relevant document IDs (gold judgments). Two common shapes:

**Binary relevance** (simpler, faster to label):
```jsonl
{"query_id": "q1", "query": "what does Welch's t-test assume?", "relevant_docs": ["doc_42", "doc_117"]}
{"query_id": "q2", "query": "Cohen's d interpretation", "relevant_docs": ["doc_88"]}
```

**Graded relevance** (richer, slower; required for NDCG to be informative):
```jsonl
{"query_id": "q1", "query": "what does Welch's t-test assume?", "judgments": [{"doc_id": "doc_42", "grade": 3}, {"doc_id": "doc_117", "grade": 2}, {"doc_id": "doc_8", "grade": 1}]}
```

Targets for size:

- Smoke test: 20 to 50 queries. Reports are noisy but signal regressions.
- Working eval: 100 to 300 queries. Most teams operate here.
- Statistically meaningful comparison: 500 plus queries (especially for small effect sizes).

If labels do not exist, build them: sample queries from production logs (anonymized), have a domain expert annotate at least one relevant doc per query, and have a second annotator label a subset for inter-annotator agreement. Cohen's kappa above 0.6 is a reasonable floor.

Version-control the labeled set. Treat it like code: if you change the gold judgments, results are no longer comparable.

### Step 3: Build the index

Encode the corpus with the retriever being evaluated. For dense retrieval:

```python
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("BAAI/bge-large-en-v1.5")
doc_embeddings = model.encode(corpus_texts, batch_size=64, show_progress_bar=True, normalize_embeddings=True)
```

For a flat (exact) index:
```python
import faiss
dim = doc_embeddings.shape[1]
index = faiss.IndexFlatIP(dim)
index.add(doc_embeddings)
```

For HNSW (faster, approximate, what production probably uses):
```python
index = faiss.IndexHNSWFlat(dim, 32)
index.add(doc_embeddings)
```

For BM25 (a strong baseline that most dense retrievers should beat):
```python
from rank_bm25 import BM25Okapi
tokenized = [doc.lower().split() for doc in corpus_texts]
bm25 = BM25Okapi(tokenized)
```

Record the index config (model name, dimension, index type, parameters like `M` and `efConstruction` for HNSW). Without these, the result is not reproducible.

### Step 4: Run queries

For each query, retrieve the top-K (use the max K you want to evaluate at; do not re-encode for each k):

```python
K_MAX = 20
query_embs = model.encode(queries, normalize_embeddings=True)
scores, indices = index.search(query_embs, K_MAX)
# indices[q_i] is the ranked list of doc indices for query q_i
```

Map indices back to document IDs so the result joins to the gold labels.

### Step 5: Compute retrieval metrics

The four core retrieval-stage metrics. Implement them once, reuse for every eval:

```python
import numpy as np

def precision_at_k(retrieved_ids, relevant_ids, k):
    top_k = retrieved_ids[:k]
    if not top_k:
        return 0.0
    return sum(1 for d in top_k if d in relevant_ids) / k

def recall_at_k(retrieved_ids, relevant_ids, k):
    if not relevant_ids:
        return 0.0
    top_k = set(retrieved_ids[:k])
    return sum(1 for d in relevant_ids if d in top_k) / len(relevant_ids)

def reciprocal_rank(retrieved_ids, relevant_ids):
    for rank, doc_id in enumerate(retrieved_ids, start=1):
        if doc_id in relevant_ids:
            return 1.0 / rank
    return 0.0

def dcg_at_k(retrieved_ids, gains_by_doc, k):
    top_k = retrieved_ids[:k]
    return sum(gains_by_doc.get(d, 0) / np.log2(i + 2) for i, d in enumerate(top_k))

def ndcg_at_k(retrieved_ids, gains_by_doc, k):
    dcg = dcg_at_k(retrieved_ids, gains_by_doc, k)
    ideal = sorted(gains_by_doc.values(), reverse=True)[:k]
    idcg = sum(g / np.log2(i + 2) for i, g in enumerate(ideal))
    return dcg / idcg if idcg > 0 else 0.0
```

Aggregate across queries by averaging. Report mean and a confidence interval (bootstrap or simple SE):

```python
recalls_at_10 = [recall_at_k(retrieved[q], relevant[q], 10) for q in queries]
mean = np.mean(recalls_at_10)
se = np.std(recalls_at_10, ddof=1) / np.sqrt(len(queries))
print(f"recall@10: {mean:.3f} +/- {1.96*se:.3f}")
```

Targets that the field considers reasonable in 2026:

- recall@5: greater than 0.7 for narrow domains, greater than 0.5 for broad
- recall@10: greater than 0.8 at k=10 for broad datasets
- MRR: depends on dataset, but compare to baselines, not absolute thresholds
- NDCG@10: greater than 0.8 (with graded relevance)

These are starting points, not contracts. The right target depends on the downstream LLM's tolerance for irrelevant context.

### Step 6: Look at the failures

The aggregate number tells you the system's average behavior. The failure list tells you what is broken. For each query where the relevant doc was not in the top-k, capture:

- The query text.
- The top-k retrieved doc IDs (and snippets).
- The gold relevant doc IDs (and snippets).
- A bucket: lexical mismatch, semantic drift, chunking boundary, missing from index, ambiguous query.

Without the failure categories, the eval cannot influence the fix. Aggregate metrics motivate change; failure categories direct it.

### Step 7: Compare to baselines

A retriever's score is only meaningful against an alternative. Always include at least:

- A trivial baseline (random retrieval, popularity-by-doc-length).
- A lexical baseline (BM25).
- The previous version of the retriever (the one in production).

A new model that scores recall@10 of 0.78 sounds great until BM25 scores 0.81 on the same set.

### Step 8: Statistical significance

If two retrievers produce per-query scores `a` and `b` on the same query set (paired observations), test the difference with a paired test:

```python
from scipy import stats
stat, p = stats.wilcoxon(recalls_a, recalls_b)
print(f"Wilcoxon paired test: stat={stat:.3f}, p={p:.4f}")
```

Wilcoxon signed-rank is the safe default (does not assume normality). Pair this with the effect size: the average per-query improvement and a 95% CI.

A p-value below 0.05 on 200 queries with mean improvement of 0.01 recall@10 is statistically significant but probably not worth shipping. Ship on effect size with CIs, not on p-value alone.

### Step 9: Write the report

The report is the deliverable. Structure:

```markdown
# Retrieval eval: <retriever name> vs <baseline>

Date: 2026-05-24
Eval query set: code-search-200-v3.jsonl (200 queries, graded relevance, kappa=0.71)
Corpus: docs/processed/ (12,440 chunks)
Retriever under test: bge-large-en-v1.5 + FAISS HNSW (M=32, efConstruction=200)
Baseline: BM25 on the same chunks

## Aggregate metrics (mean across 200 queries, +/- 1.96 SE)

| Metric    | bge-large-en-v1.5 | BM25         | Diff (95% CI)            |
|-----------|-------------------|--------------|--------------------------|
| recall@5  | 0.74 +/- 0.04     | 0.62 +/- 0.05 | +0.12 [+0.07, +0.17]    |
| recall@10 | 0.83 +/- 0.03     | 0.72 +/- 0.04 | +0.11 [+0.06, +0.16]    |
| MRR       | 0.58 +/- 0.04     | 0.49 +/- 0.04 | +0.09 [+0.04, +0.14]    |
| NDCG@10   | 0.71 +/- 0.03     | 0.61 +/- 0.04 | +0.10 [+0.06, +0.14]    |

Paired Wilcoxon on recall@10: p=0.0003. Effect is significant and meaningful.

## Failure categories (38 of 200 queries miss at recall@10)

| Category               | Count | Example query                                                |
|------------------------|-------|--------------------------------------------------------------|
| Acronym mismatch       | 14    | "MRR for irl tasks" -> chunks use "Mean Reciprocal Rank"     |
| Code-specific phrasing | 11    | "how do you call np.var with ddof" -> chunks use variance    |
| Chunk boundary loss    | 7     | Query needs context split across two chunks                  |
| Out of corpus          | 4     | Query asks about something not in the docs (expected miss)   |
| Genuinely ambiguous    | 2     | Query could match either of two valid answers                |

## Recommendation

Ship bge-large-en-v1.5. The recall@10 improvement of 0.11 on 200 queries exceeds the
ship threshold (>= 0.05 absolute, statistically significant).

Open follow-ups:

1. Acronym mismatch is the biggest fixable bucket. Add an acronym expansion preprocessor.
2. Chunk boundary loss suggests re-chunking with larger overlap (currently 50 tokens, try 150).
3. Re-eval after both fixes; if recall@10 climbs to 0.88, set that as the new floor.
```

### Step 10: Reproducibility checklist

Before closing the loop, confirm the eval can be re-run by a teammate from scratch:

- Eval script committed (not a notebook with hard-coded paths).
- Labeled query set committed (or pointer to its versioned location).
- Retriever config recorded (model name, version, index params).
- Random seeds pinned (for any sampling steps).
- Environment captured (uv.lock or requirements.txt).

If any item is missing, the eval is a one-time snapshot, not a repeatable measurement.

## Common pitfalls

- **Evaluating on the dataset you trained on**: the embedder memorized those queries. Hold out a fresh set.
- **Tiny query set**: a 10-query eval has 95% CIs so wide that any "improvement" is noise.
- **Reading recall@1000**: at k that high, almost everything recalls; the metric stops discriminating.
- **Ignoring the chunker**: changing chunk size invalidates the labeled gold IDs. Re-label or fix the chunker before the eval.
- **Evaluating only retrieval when the user cares about answers**: tell the user explicitly that retrieval-quality and answer-quality are separate, and they need both.
- **Not versioning the labeled set**: if labels change between runs, the result delta could be noise from relabeling, not retriever change.

## Subagent option

For large query sets (greater than 200 queries) or multiple retrievers compared, delegate to the `agents/rag-evaluator.md` subagent. It runs in its own context window and returns just the aggregate metrics, the failure categories, and the recommendation.

## Output shape

A markdown report (with the table, failure categories, recommendation) plus a chat reply summarizing the headline metric, the comparison to baselines, and the top three failure categories.

## Sources

- Future AGI, "RAG Evaluation Metrics 2026: The Complete Guide" (2026), https://futureagi.com/blog/rag-evaluation-metrics-2025
- Nemorize, "Evaluation & Quality Metrics", 2026 Modern AI Search & RAG Roadmap
- Label Your Data, "RAG Evaluation" enterprise guide (2025)
- Evidently AI, "A complete guide to RAG evaluation"

## Pre-flight checklist

Before triggering an eval, confirm:

1. **The question is "is the retriever good enough to ship?", not "why is the retriever bad?"** The latter is a debugging question, not an eval. An eval ends in a number; debugging ends in a hypothesis.
2. **Labels exist and are versioned.** No labels means no eval, full stop. A small unversioned label set is fine for a smoke test but should be made durable before any decision rides on the number.
3. **The corpus the eval runs on matches the corpus production uses.** Evaluating on a 1000-doc sample when production runs over 100k is informative but not definitive. Be honest about the gap.
4. **The retriever config is fully specified.** Model name, version, index type, parameters, tokenizer (for sparse). Reproducibility starts here.
5. **Baselines are available.** A score in isolation is uninformative. BM25 takes 5 minutes to set up; do not skip it.

If two or more answers are unclear, address them before any compute is spent. An eval on a shaky setup is worse than no eval.

## Second worked example: comparing three retrievers on a customer-support corpus

The first walkthrough showed a single-retriever eval (test vs BM25 baseline). The harder case is a multi-way comparison, where the team is choosing between (a) BM25 alone, (b) bge-large-en-v1.5 dense, (c) a hybrid that re-ranks BM25 top-100 with the dense embedder.

Scenario: 5k support documents, 150 labeled queries with graded relevance, the team wants to pick one retriever to ship.

Phase A: design the comparison upfront. With three retrievers, the table grows wider and the per-query scoring volume triples. Decide whether the comparisons of interest are A vs B, A vs C, B vs C, or all three. For a ship decision, the relevant comparison is "best two, then pick by latency or cost"; if A and B are clearly worst, there is no need to ship C against them.

Phase B: build all three indexes. The dense and hybrid retrievers share the same embedder, so encode once:

```python
from sentence_transformers import SentenceTransformer
import faiss
from rank_bm25 import BM25Okapi

texts = corpus["text"].tolist()
ids = corpus["doc_id"].tolist()

# Shared dense encoding (used by retrievers b and c)
embedder = SentenceTransformer("BAAI/bge-large-en-v1.5")
doc_embs = embedder.encode(texts, batch_size=64, normalize_embeddings=True, show_progress_bar=True)

# (a) BM25
tokenized = [t.lower().split() for t in texts]
bm25 = BM25Okapi(tokenized)

# (b) dense FAISS HNSW
dense_index = faiss.IndexHNSWFlat(doc_embs.shape[1], 32)
dense_index.add(doc_embs)

# (c) hybrid: BM25 top-100, re-rank by cosine similarity
def hybrid_retrieve(query, k=10):
    q_tokens = query.lower().split()
    bm25_scores = bm25.get_scores(q_tokens)
    top100 = np.argsort(bm25_scores)[-100:][::-1]
    q_emb = embedder.encode([query], normalize_embeddings=True)[0]
    rerank_scores = doc_embs[top100] @ q_emb
    reranked = top100[np.argsort(rerank_scores)[::-1]]
    return reranked[:k]
```

Phase C: run all queries against all three retrievers. Persist per-retriever per-query top-K results to disk before any scoring happens. The metrics can be recomputed from disk without re-running the retrieval, which becomes important when the team asks "what if we report at k=20 instead of k=10?".

Phase D: score each retriever. Build a three-column table per metric:

```
| Metric    | BM25 (a) | dense (b) | hybrid (c) | Best |
|-----------|----------|-----------|------------|------|
| recall@5  | 0.62     | 0.71      | 0.74       | c    |
| recall@10 | 0.72     | 0.81      | 0.85       | c    |
| MRR       | 0.49     | 0.55      | 0.61       | c    |
| NDCG@10   | 0.61     | 0.68      | 0.73       | c    |
```

Phase E: paired significance for the three pairwise comparisons. Adjust for multiple testing because three retrievers means three pairs:

```python
from scipy import stats
from statsmodels.stats.multitest import multipletests

p_ab = stats.wilcoxon(per_query_a, per_query_b).pvalue
p_ac = stats.wilcoxon(per_query_a, per_query_c).pvalue
p_bc = stats.wilcoxon(per_query_b, per_query_c).pvalue
_, p_adj, _, _ = multipletests([p_ab, p_ac, p_bc], alpha=0.05, method="fdr_bh")
print(f"Adjusted p-values: a vs b = {p_adj[0]:.4f}, a vs c = {p_adj[1]:.4f}, b vs c = {p_adj[2]:.4f}")
```

Phase F: latency check. The hybrid retriever has a re-ranking step, so latency matters. Measure p50 / p95 / p99 query latency for each retriever:

```
| Retriever | p50   | p95   | p99    |
|-----------|-------|-------|--------|
| BM25      | 8ms   | 14ms  | 22ms   |
| dense     | 24ms  | 38ms  | 51ms   |
| hybrid    | 38ms  | 58ms  | 82ms   |
```

The hybrid wins on quality but costs ~2x BM25's latency. The team's budget is the deciding factor.

Phase G: per-query failure analysis. For each retriever, look at the queries it misses that the other two get right. This is the most actionable view: "if hybrid is wrong but dense is right, what is hybrid doing wrong?" Often, the BM25 stage in hybrid is filtering out a doc that the dense embedder would have ranked highly.

Phase H: synthesize. The report ends in a binary recommendation per latency budget:

- Latency budget greater than 100ms: ship hybrid.
- Latency budget 50 to 100ms: ship dense.
- Latency budget less than 50ms: ship BM25 and prioritize a hybrid latency optimization.

The deltas from the single-retriever case: multiple paired tests (FDR correction), latency comparison alongside quality, per-pair failure analysis, conditional recommendation. The eval volume triples but the structural workflow is the same.

## Edge cases

1. **Labels and corpus drift apart**: the labeled query set references doc IDs that no longer exist in the corpus (docs were deleted, re-chunked, or re-indexed). Surface as a finding before running the eval. Either fix the labels, re-anchor to current doc IDs, or accept that some queries will count as zero-recall through no fault of the retriever.

2. **A retriever returns duplicates in its top-K** (same doc ID, different chunks): recall@k can be inflated if duplicates count as multiple hits. Dedupe at the doc-ID level before scoring, or evaluate at chunk-ID level and document the choice.

3. **The query set has queries the retriever was trained on**: contamination inflates the score. Check the embedder's training corpus and the labeled query set for overlap. If the model is a public one and the corpus is also public (e.g., MS-MARCO, BEIR), the overlap is almost certain. Switch to a held-out query set.

4. **Some queries have hundreds of relevant docs** (an "open" query): recall@10 is going to be low for these queries regardless of the retriever. Report recall on closed queries (5 or fewer relevant docs) separately from open queries.

5. **A retriever returns a score, not a rank**: when comparing retrievers with different score distributions (BM25 raw scores vs cosine similarity vs cross-encoder logits), do not mix scores across retrievers in the same plot. Compare ranks or per-retriever-normalized scores.

6. **The "gold" relevance judgments come from an LLM, not human annotators**: this is becoming common. The eval is then comparing the retriever to the LLM's notion of relevance, not to ground truth. Be explicit about this in the report and ideally calibrate the LLM judge against a small human-labeled subset (kappa greater than 0.6 is a reasonable floor).

## Anti-patterns

1. **Ship on a single retrieval metric**: recall@10 hides MRR; MRR hides NDCG; all three hide failure categories. Report all four and let the team weigh them.

2. **Tune the retriever on the eval set**: tuning leaks the eval into the training. Hold out a separate test set the eval uses, and tune on a dev set.

3. **Compare retrievers on different query sets**: even small differences in queries can swing scores by 10pp. All retrievers MUST run on the same query set for the comparison to be valid.

4. **Skip the baseline**: a dense retriever that scores recall@10 = 0.78 sounds great until BM25 hits 0.81 on the same set. Always include BM25.

5. **Treat recall@1000 as a meaningful metric**: at k that high, almost everything recalls. The metric stops discriminating. Stick to k in {1, 3, 5, 10, 20}.

## When to chain with

- **data-profiling**: profile the labeled query set before the eval. Query length distribution, judgment-grade distribution, per-topic coverage. Skipping this is how a query set with 80% one-topic queries leads to a misleading "retrieval is great" finding.
- **hypothesis-design**: when comparing two retrievers, the pre-registration locks in the comparison test, the alpha, and the ship threshold before the eval runs.
- **statistical-analysis**: the paired-significance test (Wilcoxon) and the bootstrap CIs come from the statistical-analysis playbook.
- **notebook-to-production**: a one-off retrieval-eval notebook should become `scripts/eval_retrieval.py` so it can run on every retriever change. Reproducibility is the whole point.
- **literature-synthesis**: when picking the retriever to evaluate, the literature tells you which baselines and datasets are canonical for the domain. Without this anchor, the eval is in a vacuum.

A retrieval eval is rarely the last step. It feeds into a ship decision, a follow-up tuning sprint, or a generation-quality eval. Plan the chain end to end.

## Decision tree

```
Are there labeled relevance judgments for the queries?
  No  -> stop, build labels first (smoke test = 20-50 queries, real eval = 100-300)
  Yes -> continue
        |
        v
Is the question "is the retriever good enough?" or "why is the retriever bad?"
  "why is..."  -> use a debugging workflow, not an eval
  "is it..."   -> continue
        |
        v
Is this a single-retriever eval or a multi-way comparison?
  Single  -> standard 10-step workflow
  Multi   -> follow second worked example (latency table, multi-pair significance)
        |
        v
Is the labeled set greater than 50 queries?
  No  -> proceed as smoke test only; do not ship on this alone
  Yes -> proceed as full eval
        |
        v
Is the corpus larger than 1M chunks?
  No  -> encode and index in-process
  Yes -> use ANN index (FAISS HNSW or similar), sample for the eval
        |
        v
Persist per-query retrieval output, then score, then write the report
```

## Output schema

The skill produces one or two artifacts.

**Primary artifact: the markdown report.** Path convention: `reports/eval/<YYYY-MM-DD>-retrieval-<retriever-slug>.md`.

Required sections, in order:

1. Header (date, eval query set name + version, corpus name + size, retriever under test + config, baseline retriever + config).
2. `## Aggregate metrics` (mean with 1.96 SE confidence intervals, comparison table).
3. `## Paired significance` (Wilcoxon results, mean per-query improvement with CI).
4. `## Failure categories` (categorized table of queries that missed at the operating k).
5. `## Recommendation` (binary decision: ship, do not ship, investigate; with the why).
6. `## Reproducibility` (paths to eval script, query set, env lock; random seeds).

Optional sections:

- `## Latency` (p50 / p95 / p99 query latency when relevant to the ship decision).
- `## Per-segment metrics` (per-topic, per-language, per-query-length breakdowns).
- `## Open follow-ups` (the top 1 to 3 fixes the failure analysis suggests).

**Secondary artifact: the per-query retrieval output.** A parquet or jsonl file at `reports/eval/<date>-retrieval-<slug>.queries.jsonl` with `query_id, retrieved_doc_ids[], relevant_doc_ids[], per_metric_scores`. Committed to git or stored in versioned object storage. The aggregates can be recomputed from this file without re-running the retrieval.

**Chat reply summarizes:**

- The headline metric (recall@10 with CI vs baseline).
- The recommendation (one sentence).
- The top failure category and its count.

Word count target for the markdown report: 400 to 800 words for a single-retriever eval, up to 1200 for a multi-way comparison. The tables dominate; the prose is the recommendation and the caveats.

## Quality checks before delivery

Walk through these before handing the report to the user or to a downstream skill:

1. **Are the baseline numbers plausible?** BM25 on a normal corpus usually lands in the 0.5 to 0.7 range for recall@10. A baseline score of 0 or 1.0 indicates an indexing bug. Verify before reporting.
2. **Do per-query metric arrays match the query set size?** Mismatched lengths usually mean some queries silently dropped (encoding failure, ID mismatch). Confirm n_queries before averaging.
3. **Is the recommendation a binary decision?** "Ship", "do not ship", "investigate" are decisions. "It depends" is a non-answer; if you mean conditional, state the condition.
4. **Did you cite the exact configs?** Model name, version, index parameters, top-k values. Without these, the result is not reproducible.
5. **Are statistical significance and effect size both reported?** A p < 0.05 with mean improvement of 0.005 recall@10 is significant but probably not ship-worthy. Lead with the effect size.
6. **Did you surface anything that surprised you?** Latency outliers, unusual score distributions, suspect labels. The user benefits from knowing what the eval did NOT cleanly resolve.

If any check fails, fix before delivering. A flawed eval that misclassifies the ship decision is worse than no eval.

## Limits

The skill evaluates retrieval quality only. Generation-stage evaluations (faithfulness, answer correctness, hallucination rate) require a different toolchain (RAGAS, FutureAGI, custom LLM-as-judge). If the user actually cares about end-to-end answer quality, schedule a generation-quality eval as a follow-up.

The skill assumes the labeled query set reflects the production query distribution. If the labeled set is biased (only easy queries, only one topic), the eval will overstate or understate production performance. Cross-check the label set's coverage against a sample of production queries when possible.

The skill cannot validate the labels themselves. If the gold judgments are wrong (the labeler picked the wrong relevant doc), the eval will faithfully reflect the wrong gold standard. Have a domain expert sanity-check a 10% sample of judgments before relying on the labels.

The skill measures retrieval at a point in time. Drift over time (new documents added, query patterns shifting) requires re-running the eval on a fresh labeled set, not extrapolating from an old number.
