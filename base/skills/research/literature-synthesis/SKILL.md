---
name: literature-synthesis
description: Use when the user wants a structured literature review on a topic (find recent papers, extract methods and results from each, build a comparison table, identify gaps) instead of an unstructured pile of summaries.
version: 1.1.0
owner: research-team
last_reviewed: 2026-05-25
tags: [research, literature, papers, synthesis]
scope: [research]
---

# Literature Synthesis

What this gets you: a structured synthesis of the recent work on a topic, with one row per paper covering method, dataset, results, and limitations, plus an explicit list of the gaps the literature has not closed. The output is suitable for a related-work section, a project kickoff brief, or a Confluence page.

This is not a paper search. A paper search returns titles. A synthesis turns titles into a decision: "what should we do that the field has not done yet?"

## When NOT to use this skill

- The user wants one paper summarized. Just summarize it (no synthesis structure needed).
- The user is doing a formal systematic review for publication (use the PRISMA-trAIce checklist and a dedicated tool like Covidence or Rayyan, not this lighter-weight skill).
- The user is asking a factual question with a known answer. Search the docs or ask directly.
- The topic is so narrow that fewer than three papers exist (write a one-paragraph note, not a synthesis).

## Inputs you need from the user

Confirm in one exchange:

1. **Topic** stated specifically. "RAG eval" is too broad. "Retrieval evaluation for code search RAG systems" is workable.
2. **Time window**. Default to the last 18 months for fast-moving topics (LLMs, RAG, agents). Default to 5 years for more stable areas. Ask if unclear.
3. **Scope of inclusion**. Peer-reviewed only? Include arxiv preprints? Include industry blog posts and tech reports? Default: arxiv plus peer-reviewed, exclude marketing posts.
4. **Target audience for the synthesis** (a teammate, a PR description, a slide deck, a Jira ticket). Affects depth and length.

If the user does not know the time window, propose one and proceed.

## Workflow

### Step 1: Frame the question

Before searching, write a one-sentence research question. The synthesis exists to answer this question, not to enumerate every paper on the topic.

Examples:

- "What are the current best practices for evaluating retrieval quality in RAG systems on long-document corpora?"
- "Which methods for parameter-efficient fine-tuning of LLMs work best for domain adaptation under 10B parameters?"
- "What evidence exists for the effectiveness of self-consistency prompting on math reasoning benchmarks?"

A vague question gives a vague synthesis. Rewrite until it has nouns specific enough that a paper either does or does not answer it.

### Step 2: Search

Use the search surfaces in roughly this order, depending on what the user has access to:

- **Tavily** (web search with snippets and source URLs). Good first pass for current work and gray literature.
- **arxiv-sanity** or arxiv search directly. Good for preprints in CS / ML.
- **Google Scholar** (via browser, no MCP). Good for citation chains.
- **Semantic Scholar** (API available). Good for citation graph traversal and paper recommendations.
- **Internal repos and Confluence**. Catches work the team has already done so you do not duplicate it.

Construct multiple queries from the question, not just one. For "retrieval evaluation for code search RAG":

```
"retrieval evaluation" code search RAG 2025
recall@k MRR code RAG benchmark
code retrieval evaluation embedding model
```

Cast a wider net than feels necessary. The wrong-result rate on the first query is high.

### Step 3: Triage candidates

Skim each candidate by title and abstract. Reject:

- Off-topic (mentions a keyword in passing).
- Industry blog posts that are marketing for a product (unless the product is the topic).
- Duplicates (preprint and conference version of the same paper, keep the conference version).
- Out-of-scope time window (unless seminal).

Keep candidates with one of:

- A method that directly addresses the question.
- A dataset or benchmark relevant to the question.
- A negative result or critique relevant to the question.

Aim for 8 to 20 papers in the keep pile. Fewer than 8 means the search was too narrow. More than 20 means the question was too broad and the triage should be tightened.

### Step 4: Read for extraction

For each kept paper, read the abstract, the methods section, and the results table (not the full paper). Extract into a structured record:

| Field | Notes |
|---|---|
| Citation | Author, year, venue, link |
| Method | One sentence on the technique |
| Dataset | What was tested on |
| Key result | The headline number or finding |
| Compared against | The baselines / alternatives |
| Limitations | What the paper itself acknowledges |
| Relevance to question | One sentence on why this paper matters here |

If you cannot fill in "Key result" with a specific number, the paper is probably more of a position piece than an empirical contribution. Either keep it in a separate section (Theory / Position) or drop it.

For long papers, prioritize the abstract plus methods plus headline result plus limitations. Skipping the full discussion is fine; skipping methods is not.

### Step 5: Build the comparison table

Lay the extracted records side by side as a table. Use columns that let the reader compare on the same axes:

```markdown
| Paper | Method | Dataset | Recall@10 | MRR | Notes |
|---|---|---|---|---|---|
| Smith et al. 2024 (EMNLP) | Hybrid BM25 + dense | CodeSearchNet | 0.71 | 0.58 | Strong on Python, weaker on Java |
| Lee et al. 2025 (NAACL) | ColBERT v2 + reranker | CoIR | 0.78 | 0.64 | Best overall, GPU-heavy at index time |
| Patel et al. 2025 (arxiv) | Late-interaction with code AST | Internal | 0.82 | 0.69 | Not reproducible, dataset not released |
| Chen et al. 2024 (SIGIR) | Sparse retrieval baseline | CodeSearchNet | 0.62 | 0.49 | Used as baseline by Smith and Lee |
```

The table is the deliverable's center of gravity. If a column is mostly empty across papers (e.g., latency reported by only one paper), drop the column rather than pad it.

### Step 6: Identify gaps

After the table, write a short section on what the literature does not yet answer. Gaps come in several shapes:

- **Method gaps**: a combination of techniques nobody has tried.
- **Dataset gaps**: a domain or language nobody has tested on.
- **Evaluation gaps**: a metric the field uses inconsistently, or an important metric nobody measures.
- **Reproducibility gaps**: claims that nobody has independently verified.
- **Practical gaps**: results that work in benchmarks but break under realistic constraints (latency, cost, distribution shift).

Be specific. "More work is needed" is not a gap. "Nobody has tested ColBERT v2 on long-context (greater than 32k token) code corpora with reranking under 200ms latency" is a gap.

### Step 7: Synthesize the answer

Now answer the original question, citing the table rows that support each claim. Three to five paragraphs typically.

Structure:

1. **Consensus**: what most papers agree on.
2. **Disagreement**: where papers contradict each other and what the contradictions hinge on.
3. **Recommendation**: what the user should do given the evidence, with the assumptions called out.
4. **Open questions**: the most important unresolved questions, ranked.

### Step 8: Write the document

Output format depends on audience. For a teammate reading in a chat, a markdown document with the table inline. For a Confluence page, the same content with Confluence formatting. For a related-work section, prose paragraphs that cite the table rows.

Template:

```markdown
# Literature synthesis: <topic>

Question: <one sentence>
Time window: <range>
Scope: <peer reviewed / arxiv / etc>
Papers reviewed: <count>
Date of synthesis: 2026-05-24

## Comparison

<the table>

## Consensus
<2-3 sentences>

## Disagreement
<2-3 sentences>

## Gaps
- <gap 1, specific>
- <gap 2, specific>
- <gap 3, specific>

## Recommendation
<what the user should do, with the why>

## Sources
<numbered bibliography>
```

## Quality checks

Before delivering:

- Does every claim in the synthesis cite a row in the table? If not, either add the citation or drop the claim.
- Did you read each paper, or just its abstract? Mark abstract-only entries with `(abstract only)` so the user knows the depth.
- Did you check for the team's own prior work on this topic? Internal duplication is the most embarrassing gap.
- Are the gap claims specific enough that the user could turn one into a project plan?

## When the synthesis changes the plan

Common outcomes that change downstream work:

- **A paper already answers the question**: cite it and stop. No need to redo the work.
- **A baseline is missing from the table**: maybe the team is comparing against the wrong thing.
- **The field has converged on a metric your team is not using**: switch metrics.
- **No paper has tried the user's planned approach**: this might be a novel contribution or might be the "nobody tried it because it does not work" trap. Check the disagreement section.

## Subagent option

For larger syntheses (greater than 10 papers), delegate to the `agents/literature-synthesizer.md` subagent. It runs in its own context window so the paper text does not pollute the parent agent's context. The subagent returns just the structured table plus gaps plus recommendation.

## Output shape

A markdown document at a path the user picks, plus a chat reply with the top three takeaways and the recommendation. If the user wants HTML for human review, follow the human-html artifact convention (`docs/human-html/YYYY-MM-DD-research-<topic>.html`).

## Sources

- PRISMA-trAIce checklist for AI-assisted systematic reviews, JMIR AI 2025, https://ai.jmir.org/2025/1/e80247
- Carleton University, "Guide to Produce Scoping Literature Reviews Using AI Tools" (2025)
- General prior art: PRISMA 2020 statement for systematic review reporting

## Pre-flight checklist

Run through these before triggering a full synthesis. Many literature questions can be answered faster with a smaller move.

1. **Has a recent synthesis on this topic been done in-house?** Check the team's wiki, Confluence, ADRs, or `docs/research/` directory. A 3-month-old synthesis on the same question saves a day of work. Update the existing one rather than starting over.
2. **Is the question narrow enough to triage in under a day?** "Survey of all RAG techniques" is a multi-week effort. "Recent comparisons of ColBERT v2 vs bge-large on long-context corpora" is a few hours. Tighten before starting.
3. **Does the team already know the canonical 3 papers on the topic?** If yes, start by reading those, then synthesize. If no, the search step is heavier and the keep-rate lower.
4. **Will the synthesis change a decision the team is about to make?** If no, the synthesis is academic exercise. Save it for when it has stakes.
5. **Is the topic moving fast enough that a 6-month-old synthesis would be stale?** For LLM-related topics, yes. For classical ML, often no. Calibrate the time window in Step 2 accordingly.

If three or more of these tilt against running the full synthesis, propose a smaller move (read 1 paper, ask an expert, summarize the existing wiki page).

## Second worked example: industry / gray literature synthesis

The first walkthrough assumed peer-reviewed and arxiv sources. Many practical questions ("how are people running RAG at production scale?") are answered better by industry blog posts, engineering talks, and tech reports than by academic papers. The workflow needs adjustment.

Scenario: the team wants to understand current best practices for RAG in production, specifically around chunking strategy and retrieval latency budgets. The relevant sources are largely engineering blogs (LangChain, LlamaIndex, Pinecone, Anthropic), conference talks (HackerNews, fwdays, AI Engineer Summit), and tech reports from vendors. Academic papers exist but lag the practice.

Phase A: scope the sources. Decide up front: include peer-reviewed (yes), include arxiv (yes), include vendor blog posts (yes, but tag separately), include personal blog posts (yes if the author has provenance), include tweets / threads (no, too low-signal even when correct). The synthesis will be more practitioner-oriented than the first example.

Phase B: search with Tavily on practitioner-flavored queries:

```
"RAG production" chunk size 2025
"retrieval latency" vector database production
"hybrid retrieval" RAG production blog
```

Tavily returns blog posts with snippets and source URLs. The hit rate for relevant content is usually higher than arxiv for production questions, but the noise floor is also higher (a lot of marketing).

Phase C: triage harder. Industry posts often repeat each other or rephrase a vendor's marketing. Reject:

- Posts that are clearly product positioning ("LangChain announces new chunking API").
- Posts that summarize other posts without adding evidence.
- Posts older than 12 months for fast-moving topics.

Keep posts that:

- Report a specific benchmark or production metric.
- Describe an implementation in detail (with code or config).
- Contradict the consensus and explain why.

Phase D: read for extraction. Industry posts often hide the key claim in a chart or table. Extract that explicitly:

```yaml
- citation: "Pinecone engineering blog, 'Chunking strategies for RAG', 2025"
  source_type: vendor blog
  key_claim: "256-token chunks with 50-token overlap outperform 1024-token chunks for code-search RAG by +5pp recall@10"
  evidence: "Internal benchmark on 1M chunks, 2k queries"
  caveats: "Used Pinecone's hybrid index; result may not transfer to FAISS or BM25 only"
  relevance: "Directly addresses the chunking question"
```

For tech talks, the slides plus a 5-minute scan of the talk transcript or summary is enough. Do not watch full talks unless absolutely needed; transcripts are faster.

Phase E: build the comparison table with a "Source type" column (peer-reviewed / arxiv / vendor blog / personal blog / talk). The reader can weight findings by source type.

Phase F: identify gaps with practitioner framing. Where academic papers report "+5% recall@10", industry posts often report "we doubled p99 latency". The gaps are usually around the metrics academic work does not measure: cost, latency tail, ops complexity, drift over time.

Phase G: synthesize with explicit weighting. Industry sources are weighted lower for "what is true" claims and higher for "what is feasible at scale" claims. Make the weighting explicit in the synthesis paragraphs.

Phase H: deliverable. The output is the same shape (comparison table, consensus, disagreement, gaps, recommendation) but the recommendation often takes the form "this is what the field is doing in practice; here is what is open" rather than "method X beats method Y by Z%".

The deltas from the academic case: broader source scope, more aggressive triage, source-type tagging in the table, practitioner-flavored gaps. Same structural workflow, different judgment calls at every step.

## Edge cases

1. **The topic is so new that no peer-reviewed papers exist yet**: lean on preprints, blog posts, and talks. State explicitly in the synthesis header that the evidence base is preprint-heavy and what that implies for confidence.

2. **One paper is cited by half the others as the canonical reference**: read it carefully (full read, not abstract + methods) because it shapes the whole field. The synthesis should treat it as the anchor and structure the comparison around its framing.

3. **Two papers contradict each other on the same dataset with the same metric**: this is the most interesting finding. Read both papers' methods sections carefully to find the source of the discrepancy. Surface it as a disagreement in the synthesis, do not pick a winner. Possible sources: different preprocessing, different splits, different metric definitions despite identical names.

4. **A paper makes a strong claim with proprietary data**: the result cannot be independently verified. Mark as "claim, not verified" in the relevance column. Do not drop the paper, but discount its weight in the synthesis.

5. **The search returns a "survey paper" on the exact question**: read it first, then extend rather than redo. The survey saves weeks of work, but it is also probably 12 to 18 months stale. Your synthesis becomes "since the [survey] in 2024, the following has changed".

6. **The team's own prior work appears in the candidate list**: keep it, but flag it as internal. The synthesis should not appear to "discover" the team's own paper.

## Anti-patterns

1. **Listing papers without comparing them**: a list of summaries is not a synthesis. The deliverable is the comparison table plus the gaps plus the recommendation. If those three are missing, the work is a paper search, not a synthesis.

2. **Reading only abstracts and pretending you read the papers**: abstracts lie. Methods sections do not. If you only had time for the abstract, mark the entry `(abstract only)` so the reader knows the depth.

3. **Bias toward what is in the cache / Tavily index**: search engines have biases. Cross-check with at least one alternative source (Semantic Scholar, Google Scholar, arxiv search) before declaring the literature sparse.

4. **Synthesizing without naming the gaps**: the gaps are the bridge between "what the literature says" and "what we should do". Without gaps, the synthesis is descriptive, not actionable.

5. **Pretending consensus exists when it does not**: if the literature is genuinely contested, say so. A synthesis that papers over real disagreement misleads the reader more than no synthesis.

## When to chain with

- **agent-repo-briefing**: when starting work on a new repo, the brief may reveal an open research question. Run literature-synthesis before designing the experiment to avoid reinventing.
- **hypothesis-design**: the literature provides the effect-size prior. Synthesis -> MDE -> power calc -> pre-registration.
- **rag-eval-method**: when evaluating a new retrieval approach, the synthesis tells you which baselines to include and which datasets are canonical. Skip the synthesis and you risk evaluating in isolation.
- **statistical-analysis**: the synthesis tells you which tests the field uses for which metrics. Following convention makes results easier to compare to prior work.

The skill rarely needs anything before it (it can run cold from a research question). It frequently feeds into another skill.

## Decision tree

```
Is the research question specific (named methods, datasets, or metrics)?
  No  -> tighten the question before searching
  Yes -> continue
        |
        v
Does a recent in-house synthesis exist?
  Yes -> read and update, do not redo
  No  -> continue
        |
        v
Is the topic peer-reviewed-heavy or practitioner-heavy?
  Peer-reviewed -> standard 8-step workflow (Tavily + arxiv + Semantic Scholar)
  Practitioner  -> follow second worked example (broader sources, harder triage)
        |
        v
Estimate kept-paper count after Step 3 triage:
  Less than 3   -> escalate to the user, may need primary research
  3 to 8        -> short synthesis (one paragraph per paper)
  8 to 20       -> standard synthesis (comparison table)
  Greater than 20 -> tighten question; cap inclusion criteria
        |
        v
Will the synthesis exceed 1500 words?
  Yes -> delegate to literature-synthesizer subagent
  No  -> run inline in the current session
```

## Output schema

The skill produces a single committed synthesis document. Path convention: `docs/research/<YYYY-MM-DD>-literature-<topic-slug>.md`, or `docs/human-html/<YYYY-MM-DD>-research-<topic-slug>.html` if a human will review.

Required sections, in order:

1. Header (question, time window, scope, paper count, date of synthesis).
2. `## Comparison` (the table; 4 to 6 columns; rows are papers).
3. `## Consensus` (2 to 3 sentences on what papers agree).
4. `## Disagreement` (2 to 3 sentences on where papers contradict each other and why).
5. `## Gaps` (3 to 6 specific, actionable gap statements).
6. `## Recommendation` (what the user should do, with the why).
7. `## Sources` (numbered bibliography matching the citations in the table).

Optional sections:

- `## Theory / Position` (papers that argue a viewpoint without empirical results).
- `## Open questions ranked` (when the synthesis surfaces multiple unresolved questions worth follow-up).
- `## Search summary` (how many candidates, how many kept, what queries were used).

The chat reply summarizes:

- The top 3 takeaways (one sentence each).
- The recommendation.
- The path to the full doc.

Word count target: 600 to 1500 words for the doc. The comparison table dominates the page; the prose is supporting.

## Quality checks before delivery

Before handing the synthesis to the user (or to a downstream skill that depends on it), walk these:

1. **Does every claim cite a row in the comparison table?** If a sentence makes a claim without a citation, either add the citation or drop the sentence. Uncited claims erode the synthesis's credibility.
2. **Are abstract-only entries explicitly marked?** Mark them `(abstract only)` in the table so the reader knows the depth of reading. An abstract-only paper cannot support a methods-level claim.
3. **Is each gap actionable?** A gap that reads "more research is needed" is not actionable. A gap that reads "no paper has tested ColBERT v2 on long-context code corpora with reranking under 200ms latency" is.
4. **Did you check the team's own prior work?** Internal duplication is the most common embarrassment. Search the team's wiki, ADRs, and Jira for the topic before declaring a "gap" that the team has already filled.
5. **Are the gap claims specific enough that the user could turn one into a project plan?** If not, tighten until they are.
6. **Is the search summary honest?** Number of candidates, number kept, number rejected. The user uses this to decide whether to commission a deeper search.

If any check fails, fix before delivering. A synthesis with shaky citations or vague gaps is worse than no synthesis because it gives false confidence.

## Limits and honesty

The skill is a synthesis instrument, not a primary-research one. If the literature is genuinely sparse, the synthesis should say so and recommend a follow-up (commission an experiment, ask a domain expert, broaden the search), not pad with off-topic papers.

The skill reads what is accessible. Paywalled papers that the user cannot reach are flagged in the bibliography. The synthesis does not fabricate findings from those papers.

The recommendation reflects the evidence at the time of synthesis. For fast-moving topics (LLMs, RAG, agents), the half-life is roughly 6 months; for classical ML, 18 months; for theory, 3 to 5 years. Note the date prominently. Future readers should re-run the skill when the evidence base shifts.

The recommendation does not weigh organizational considerations (team investments, deadlines, political constraints). Those belong to the user, who reads the synthesis and applies their own judgment.

## Tooling notes

The skill's effective range depends on which retrieval tools are available.

**Tavily** is the default search tool. It returns titles, abstracts, and source URLs. For each kept candidate, use `tavily_extract` or `WebFetch` to pull the full HTML / PDF content.

**arxiv search** reaches preprints faster than Tavily. Run an arxiv search as a supplement for fast-moving topics.

**Semantic Scholar** is the best tool for citation chain traversal. Given a seminal paper, it finds forward citations and backward references.

**Google Scholar** (browser-only) covers more ground in some fields but lacks a clean API. Use only when other tools come up empty.

**WebFetch** is the universal fallback for any URL.

If only one tool is available, the synthesis is still possible but the coverage is narrower. State the tool set explicitly in the search summary.

## Common failure modes

1. **Ambiguous term**: "schema" could mean XML schema, database schema, or JSON schema. The first search variant should disambiguate.
2. **Survey-of-surveys loop**: synthesizing three surveys is not a synthesis. Extend with primary work published after the surveys.
3. **Marketing leak**: vendor blog posts that look neutral until you read them. Tag vendor sources explicitly and discount their weight.
4. **Single-paper bias**: one strong paper dominates the results and the synthesis over-cites it. Cap inclusion to 1 paper per author, 2 per group, to force diversity.

Surface to the user if any of these patterns produce a synthesis you are not confident in.

## Reading depth strategy

Not all papers need the same depth. A pragmatic reading strategy:

**Depth 1 (abstract only)**: 1 to 2 minutes per paper. Use for triage; do not let depth-1 reads support methods-level claims in the synthesis.

**Depth 2 (abstract + methods + headline result + limitations)**: 10 to 15 minutes per paper. The default for kept papers. Captures enough to fill the comparison table accurately.

**Depth 3 (full read including discussion + appendix)**: 30 to 60 minutes per paper. Reserve for the 1 to 3 most important papers in the keep pile (the canonical reference, the contradictory result, the paper the synthesis hinges on).

Most syntheses end up with about 12 papers at depth 2 and 2 papers at depth 3. That is roughly 3 to 4 hours of focused reading time, plus the search and the writeup.

If the user is under time pressure, scale down: 6 papers at depth 2 and 1 at depth 3, in about 90 minutes. Mark the depth in the synthesis so the reader knows the confidence level.

## Common topic shapes and their pitfalls

Three recurring shapes in literature-synthesis requests:

1. **"Survey of method X"**: the risk is producing a list of papers using X without comparing them. Fix: structure the comparison around the method's parameters (model size, dataset, evaluation metric).

2. **"X vs Y showdown"**: the risk is cherry-picking the benchmark where X wins. Fix: include all reported benchmarks even when they favor Y; the disagreement section names the contested ones.

3. **"State of the art on benchmark Z"**: the risk is missing methods that beat the SOTA on Z but were reported as side results in papers about something else. Fix: search for "Z" as a free-text term, not just in titles.

Each shape has a standard pitfall. Awareness of which shape the user asked for makes the synthesis tighter.

## Re-use and maintenance

A one-time synthesis is a snapshot. A maintained one is durable infrastructure. Patterns for maintenance:

1. **Date prominently**: the header has `Date of synthesis: YYYY-MM-DD`. Future readers know its age. If the date is greater than 6 months for a fast-moving topic, treat the synthesis as a draft rather than a reference.

2. **Track diffs across versions**: when re-running on the same question, the new doc has a "Since [prior date]" section listing papers added or claims that have shifted. This makes the second run cheaper than the first.

3. **Promote durable syntheses to wiki / Confluence**: if the synthesis is referenced by multiple downstream documents, lift it from `docs/research/` to a shared knowledge base. Leave a stub in the repo pointing to the canonical version.

4. **Schedule re-runs**: for fast-moving topics, calendar reminder 6 months out. For classical topics, 18 months. The skill itself can be invoked again with the same question to refresh.

5. **Surface as the team's prior work on the next session**: when an agent runs `agent-repo-briefing` on the repo, the brief should list `docs/research/` syntheses so the next session does not re-derive them.

A synthesis that is created and forgotten loses value within 6 months for any fast-moving area. A synthesis that is maintained becomes the team's canonical reference on the topic.

## Final delivery checklist

Before declaring the synthesis complete:

1. Document committed (or returned inline per user preference).
2. Comparison table has 4 to 6 columns and every row has a citation.
3. Consensus, disagreement, gaps, and recommendation sections all populated.
4. Bibliography numbered, with URLs for every reference.
5. Abstract-only entries marked explicitly with `(abstract only)`.
6. Date of synthesis in the header (current date, not the dataset date).
7. Search summary present (candidates found, kept, rejected).
8. No em dashes in the document.
9. Word count is within target (600 to 1500 for typical, up to 2000 for unusually broad questions).
10. Chat reply summarizes top 3 takeaways, the recommendation, and the doc path.

If any item fails, fix before delivery. A synthesis with shaky bibliographies or unsupported claims loses credibility and the user discounts the recommendation.

## Failure modes to surface

When the synthesis cannot complete cleanly, the right move is honesty rather than padding. Common failure modes:

1. **Sparse literature (less than 3 keeps)**: synthesis says "the literature on this topic is sparse; recommend commissioning primary research or running an internal experiment".
2. **Contested key result**: synthesis names the contradiction explicitly; does not pick a winner; recommends the experiment that would resolve it.
3. **Paywall walls on critical papers**: synthesis flags inaccessible papers in the bibliography; user resolves through library or by contacting authors.
4. **Topic too broad to triage**: synthesis asks the user to narrow the question; partial synthesis if appropriate.
5. **Topic outside the search tools' coverage**: synthesis flags the gap and recommends an alternative source (a specific journal, a conference proceedings page, an expert).

Each of these is a finding worth surfacing in its own right. The synthesis is most valuable when it tells the truth about what is and is not known, including the gaps in the synthesis itself.

## Worked synthesis fragments

To illustrate the level of specificity the skill targets, here are sample fragments showing what good output looks like.

**Sample comparison-table row:**

```
| Smith et al. 2025 (EMNLP) | Hybrid BM25 + bge-large reranker | CodeSearchNet Python | recall@10 = 0.78 | MRR = 0.62 | Latency p95 = 38ms on CPU; not reproducible (internal eval set) |
```

**Sample consensus paragraph:**

```
The literature converges on two findings. First, dense embedding models with at least
500M parameters consistently beat BM25 on recall@10 for code search by 7 to 12 percentage
points (rows 1, 3, 5, 7). Second, hybrid retrievers (BM25 top-100 reranked by a dense
model) close 60 to 80% of the remaining gap with a cross-encoder reranker, at a 2 to 3x
latency cost (rows 2, 4, 8).
```

**Sample disagreement paragraph:**

```
The literature disagrees on whether the reranker's choice of base embedder matters at
scale. Lee et al. 2025 (row 2) claims ColBERT v2 beats bge-large by +0.04 NDCG@10 on
their internal corpus; Chen et al. 2025 (row 5) reports the opposite on CoIR. The two
papers use different chunkers and different relevance grading scales, which likely drives
much of the gap. A clean comparison on a single benchmark is missing.
```

**Sample gap statement:**

```
- No paper has evaluated ColBERT v2 + bge-large hybrid on long-context (greater than 32k
  tokens) code corpora with reranker latency capped at 200ms. The closest is Patel et al.
  2025 (row 7), but their evaluation excluded queries with multi-file relevant docs.
```

**Sample recommendation paragraph:**

```
Given that the team needs to ship a code-search retriever within a 100ms p95 latency
budget, we recommend bge-large-en-v1.5 + FAISS HNSW. The literature (rows 1, 3, 5)
supports this configuration as the best balance of quality and latency at the team's
scale (~5M chunks). The hybrid reranker would add +0.04 recall@10 but doubles latency;
defer until the latency budget is relaxed.
```

These fragments show what "specific" looks like. Compare to the anti-pattern of "more research is needed in this area" or "method X is better in some cases" which are not actionable.
