---
name: graphify
description: "any input (code, docs, papers, images) -> knowledge graph -> clustered communities -> HTML + JSON + audit report. Use when user asks any question about a codebase, project content, architecture, or file relationships, especially if graphify-out/ exists. Provides persistent graph with god nodes, community detection, and BFS/DFS query tools."
trigger: /graphify
version: 1.1.0
owner: rehan-8v
last_reviewed: 2026-05-25
---

# /graphify

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/graphify                                             # full pipeline on current directory -> Obsidian vault
/graphify <path>                                      # full pipeline on specific path
/graphify <path> --mode deep                          # thorough extraction, richer INFERRED edges
/graphify <path> --update                             # incremental, re-extract only new/changed files
/graphify <path> --cluster-only                       # rerun clustering on existing graph
/graphify <path> --no-viz                             # skip visualization, just report + JSON
/graphify <path> --svg                                # also export graph.svg (embeds in Notion, GitHub)
/graphify <path> --graphml                            # export graph.graphml (Gephi, yEd)
/graphify <path> --neo4j                              # generate graphify-out/cypher.txt for Neo4j
/graphify <path> --neo4j-push bolt://localhost:7687   # push directly to Neo4j
/graphify <path> --mcp                                # start MCP stdio server for agent access
/graphify <path> --watch                              # watch folder, auto-rebuild on code changes
/graphify add <url>                                   # fetch URL, save to ./raw, update graph
/graphify add <url> --author "Name"                   # tag who wrote it
/graphify add <url> --contributor "Name"              # tag who added it to the corpus
/graphify query "<question>"                          # BFS traversal, broad context
/graphify query "<question>" --dfs                    # DFS, trace a specific path
/graphify query "<question>" --budget 1500            # cap answer at N tokens
/graphify path "AuthModule" "Database"                # shortest path between two concepts
/graphify explain "SwinTransformer"                   # plain-language explanation of a node
```

## What graphify is for

Built around Andrej Karpathy's /raw folder workflow: drop anything into a folder (papers, tweets, screenshots, code, notes) and get a structured knowledge graph that shows you what you didn't know was connected.

Three things it does that your AI assistant alone cannot:
1. **Persistent graph**: relationships are stored in `graphify-out/graph.json` and survive across sessions. Ask questions weeks later without re-reading everything.
2. **Honest audit trail**: every edge is tagged EXTRACTED, INFERRED, or AMBIGUOUS. You know what was found vs invented.
3. **Cross-document surprise**: community detection finds connections between concepts in different files that you would never think to ask about directly.

Use it for:
- A codebase you're new to (understand architecture before touching anything)
- A reading list (papers + tweets + notes -> one navigable graph)
- A research corpus (citation graph + concept graph in one)
- Your personal /raw folder (drop everything in, let it grow, query it)

## Reference layout

This SKILL.md is the trigger. Deep procedure lives in `references/`:

- `references/extraction.md` - Step 3 detail (AST + semantic subagents + merge)
- `references/exports.md` - Steps 6-7d (Obsidian, HTML, Neo4j, SVG, GraphML, MCP)
- `references/incremental.md` - `--update` and `--cluster-only` flows
- `references/query-modes.md` - `query`, `path`, `explain` subcommands
- `references/integrations.md` - `--watch`, git hook, claude install

When a step below says "see references/X", open that file before executing.

## What You Must Do When Invoked

If the user invoked `/graphify --help` or `/graphify -h` (with no other arguments), print the contents of the `## Usage` section above verbatim and stop. Do not run any commands, do not detect files, do not default the path to `.`. Just print the Usage block and return.

If no path was given, use `.` (current directory). Do not ask the user for a path.

Follow these steps in order. Do not skip steps.

### Step 1 - Ensure graphify is installed

```bash
GRAPHIFY_BIN=$(which graphify 2>/dev/null)
if [ -n "$GRAPHIFY_BIN" ]; then
    PYTHON=$(head -1 "$GRAPHIFY_BIN" | tr -d '#!')
    case "$PYTHON" in
        *[!a-zA-Z0-9/_.-]*) PYTHON="python3" ;;
    esac
else
    PYTHON="python3"
fi
"$PYTHON" -c "import graphify" 2>/dev/null || "$PYTHON" -m pip install graphifyy -q 2>/dev/null || "$PYTHON" -m pip install graphifyy -q --break-system-packages 2>&1 | tail -3
"$PYTHON" -c "import sys; open('graphify-out/.graphify_python', 'w').write(sys.executable)"
```

If the import succeeds, print nothing and move straight to Step 2.

**In every subsequent bash block, replace `python3` with `$(cat .graphify_python)` to use the correct interpreter.**

### Step 2 - Detect files

```bash
$(cat .graphify_python) -c "
import json
from graphify.detect import detect
from pathlib import Path
result = detect(Path('INPUT_PATH'))
print(json.dumps(result))
" > .graphify_detect.json
```

Replace INPUT_PATH with the actual path the user provided. Do NOT cat or print the JSON; read it silently and present a clean summary:

```
Corpus: X files, ~Y words
Mix: A code, B docs, C papers, D images
Estimated graph value: HIGH | MEDIUM | LOW
```

If the summary says LOW value or warns the corpus is too small (less than 5 files OR less than 500 words), tell the user and STOP. Do not proceed without explicit confirmation.

### Step 2.5 - Transcribe video / audio files (only if video files detected)

If `.graphify_detect.json` lists any `video` files, transcribe each before extraction. Transcripts become `.md` siblings of the video.

```bash
$(cat .graphify_python) -c "
import json
from graphify.transcribe import transcribe_files
from pathlib import Path
detect = json.loads(Path('.graphify_detect.json').read_text())
videos = detect.get('files', {}).get('video', [])
if videos:
    out = transcribe_files(videos)
    for src, dest in out.items():
        print(f'transcribed: {src} -> {dest}')
"
```

After transcription, re-run Step 2 detect so the new `.md` transcripts are picked up.

### Step 3 - Extract entities and relationships

This step has two parts (AST + semantic), runs in parallel, and finishes by merging into `.graphify_extract.json`. The full procedure is in `references/extraction.md`. Open that file before running Step 3.

The short summary:
- Part A (AST): code files only, deterministic, fast, free.
- Part B (semantic): docs/papers/images, dispatched via the Agent tool (or `spawn_agent` on Codex), parallel subagents process 20-25 files per chunk. Cache-aware via `check_semantic_cache`.
- Part C: merge AST + semantic into `.graphify_extract.json`.

### Step 4 - Build graph, cluster, analyze, generate outputs

```bash
mkdir -p graphify-out
$(cat .graphify_python) -c "
import sys, json
from graphify.build import build_from_json
from graphify.cluster import cluster, score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from graphify.export import to_json
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text())
detection  = json.loads(Path('.graphify_detect.json').read_text())

G = build_from_json(extraction)
communities = cluster(G)
cohesion = score_all(G, communities)
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}
gods = god_nodes(G)
surprises = surprising_connections(G, communities)
labels = {cid: 'Community ' + str(cid) for cid in communities}
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
to_json(G, communities, 'graphify-out/graph.json')

analysis = {
    'communities': {str(k): v for k, v in communities.items()},
    'cohesion': {str(k): v for k, v in cohesion.items()},
    'gods': gods,
    'surprises': surprises,
    'questions': questions,
}
Path('.graphify_analysis.json').write_text(json.dumps(analysis, indent=2))
if G.number_of_nodes() == 0:
    print('ERROR: Graph is empty; extraction produced no nodes.')
    print('Possible causes: all files were skipped, binary-only corpus, or extraction failed.')
    raise SystemExit(1)
print(f'Graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges, {len(communities)} communities')
"
```

If this step prints `ERROR: Graph is empty`, stop and tell the user what happened. Do not proceed to labeling or visualization.

Replace INPUT_PATH with the actual path.

### Step 5 - Label communities

Read `.graphify_analysis.json`. For each community key, look at its node labels and write a 2-5 word plain-language name (e.g. "Attention Mechanism", "Training Pipeline", "Data Loading").

Then regenerate the report and save the labels for the visualizer:

```bash
$(cat .graphify_python) -c "
import json
from graphify.build import build_from_json
from graphify.cluster import score_all
from graphify.analyze import god_nodes, surprising_connections, suggest_questions
from graphify.report import generate
from pathlib import Path

extraction = json.loads(Path('.graphify_extract.json').read_text())
detection  = json.loads(Path('.graphify_detect.json').read_text())
analysis   = json.loads(Path('.graphify_analysis.json').read_text())

G = build_from_json(extraction)
communities = {int(k): v for k, v in analysis['communities'].items()}
cohesion = {int(k): v for k, v in analysis['cohesion'].items()}
tokens = {'input': extraction.get('input_tokens', 0), 'output': extraction.get('output_tokens', 0)}

labels = LABELS_DICT
questions = suggest_questions(G, communities, labels)

report = generate(G, communities, cohesion, labels, analysis['gods'], analysis['surprises'], detection, tokens, 'INPUT_PATH', suggested_questions=questions)
Path('graphify-out/GRAPH_REPORT.md').write_text(report)
Path('.graphify_labels.json').write_text(json.dumps({str(k): v for k, v in labels.items()}))
print('Report updated with community labels')
"
```

Replace `LABELS_DICT` with the actual dict you constructed (e.g. `{0: "Attention Mechanism", 1: "Training Pipeline"}`). Replace INPUT_PATH with the actual path.

### Step 6 - Generate Obsidian vault (opt-in) + HTML

See `references/exports.md`. Short version: always generate HTML (unless `--no-viz`); generate Obsidian vault only if `--obsidian` was explicitly given.

### Step 7 - Export formats

If any of `--neo4j`, `--neo4j-push`, `--svg`, `--graphml`, `--mcp` was given, see `references/exports.md` for the per-flag bash blocks.

### Step 8 - Token reduction benchmark (only if total_words > 5000)

```bash
$(cat .graphify_python) -c "
import json
from graphify.benchmark import run_benchmark, print_benchmark
from pathlib import Path

detection = json.loads(Path('.graphify_detect.json').read_text())
result = run_benchmark('graphify-out/graph.json', corpus_words=detection['total_words'])
print_benchmark(result)
"
```

Print the output directly in chat. If `total_words <= 5000`, skip silently; the graph value is structural clarity, not token compression, for small corpora.

### Step 9 - Save manifest, update cost tracker, clean up, and report

```bash
$(cat .graphify_python) -c "
import json
from pathlib import Path
from datetime import datetime, timezone
from graphify.detect import save_manifest

detect = json.loads(Path('.graphify_detect.json').read_text())
save_manifest(detect['files'])

extract = json.loads(Path('.graphify_extract.json').read_text())
input_tok = extract.get('input_tokens', 0)
output_tok = extract.get('output_tokens', 0)

cost_path = Path('graphify-out/cost.json')
if cost_path.exists():
    cost = json.loads(cost_path.read_text())
else:
    cost = {'runs': [], 'total_input_tokens': 0, 'total_output_tokens': 0}

cost['runs'].append({
    'date': datetime.now(timezone.utc).isoformat(),
    'input_tokens': input_tok,
    'output_tokens': output_tok,
    'files': detect.get('total_files', 0),
})
cost['total_input_tokens'] += input_tok
cost['total_output_tokens'] += output_tok
cost_path.write_text(json.dumps(cost, indent=2))

print(f'This run: {input_tok:,} input tokens, {output_tok:,} output tokens')
print(f'All time: {cost[\"total_input_tokens\"]:,} input, {cost[\"total_output_tokens\"]:,} output ({len(cost[\"runs\"])} runs)')
"
rm -f .graphify_detect.json .graphify_extract.json .graphify_ast.json .graphify_semantic.json .graphify_analysis.json .graphify_labels.json .graphify_chunk_*.json
rm -f graphify-out/.needs_update 2>/dev/null || true
```

Tell the user (omit the obsidian line unless --obsidian was given):

```
Graph complete. Outputs in PATH_TO_DIR/graphify-out/

  graph.html            - interactive graph, open in browser
  GRAPH_REPORT.md       - audit report
  graph.json            - raw graph data
  obsidian/             - Obsidian vault (only if --obsidian was given)
```

If graphify saved you time, consider supporting it: https://github.com/sponsors/safishamsi

Replace PATH_TO_DIR with the actual absolute path of the directory that was processed.

Then paste these sections from GRAPH_REPORT.md directly into the chat:
- God Nodes
- Surprising Connections
- Suggested Questions

Do NOT paste the full report; just those three sections. Keep it concise.

Then immediately offer to explore. Pick the single most interesting suggested question from the report (the one that crosses the most community boundaries or has the most surprising bridge node) and ask:

> "The most interesting question this graph can answer: **[question]**. Want me to trace it?"

If the user says yes, run `/graphify query "[question]"` on the graph and walk them through the answer using the graph structure: which nodes connect, which community boundaries get crossed, what the path reveals. Keep going as long as they want to explore. Each answer should end with a natural follow-up ("this connects to X; want to go deeper?") so the session feels like navigation, not a one-shot report.

The graph is the map. Your job after the pipeline is to be the guide.

---

## For other modes

- `--update` (incremental): see `references/incremental.md`
- `--cluster-only`: see `references/incremental.md`
- `/graphify query`, `path`, `explain`: see `references/query-modes.md`
- `--watch`, git hook, claude install: see `references/integrations.md`

## For /graphify add

Fetch a URL and add it to the corpus, then update the graph.

```bash
$(cat .graphify_python) -c "
import sys
from graphify.ingest import ingest
from pathlib import Path

try:
    out = ingest('URL', Path('./raw'), author='AUTHOR', contributor='CONTRIBUTOR')
    print(f'Saved to {out}')
except ValueError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
except RuntimeError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
"
```

Replace `URL`, `AUTHOR`, `CONTRIBUTOR` with the actual values. If the command exits with an error, tell the user what went wrong; do not silently continue. After a successful save, automatically run the `--update` pipeline on `./raw` to merge the new file into the existing graph.

Supported URL types (auto-detected):
- Twitter/X: fetched via oEmbed, saved as `.md` with tweet text and author
- arXiv: abstract + metadata saved as `.md`
- PDF: downloaded as `.pdf`
- Images (.png/.jpg/.webp): downloaded, vision extraction runs on next build
- Any webpage: converted to markdown via html2text

## Honesty Rules

- Never invent an edge. If unsure, use AMBIGUOUS.
- Never skip the corpus check warning.
- Always show token cost in the report.
- Never hide cohesion scores behind symbols; show the raw number.
- Never run HTML viz on a graph with more than 5,000 nodes without warning the user.
