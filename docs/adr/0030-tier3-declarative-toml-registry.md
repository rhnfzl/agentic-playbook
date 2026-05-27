# 0030. Tier 3 declarative TOML registry

## Status

Accepted (2026-05-25); landed in v0.5.

## Context

Tier 3 adapters (per ADR-0005) cover coding agents that read AGENTS.md natively at the project root and need no per-tool storage beyond that single file. The list grew from a handful in v0.2 to 20 in v0.4, and the grilling for v0.5 surfaced six more candidates on the watchlist.

Through v0.4, every Tier 3 entry was a Python literal in `scripts/adapters/agents_md.py` (renamed to `tier3.py` in v0.5 for naming-collision reasons):

```python
ADAPTERS: list[Adapter] = [
    TierThreeAdapter("kiro", lambda: (Path.home() / ".kiro").is_dir()),
    TierThreeAdapter("goose", lambda: _loader.which("goose") is not None),
    TierThreeAdapter(
        "junie", lambda: _loader.vscode_extension_present("jetbrains.junie")
    ),
    # ... 17 more ...
]
```

Two observations from the grilling:

1. **The detection rules cluster into five idioms.** All 20 lambdas use one of: `is_dir(~/.X)`, `which("X")`, `vscode_extension_present("vendor.X")`, `Path("/Applications/X.app").exists()`, or `any` of the first four. No exotic logic, no per-tool branching, no escape hatches.

2. **Adding a new Tier 3 tool requires a Python edit.** That is fine for a contributor familiar with the codebase, but it means a non-Python-fluent teammate cannot add the tool they actually use without going through a code-review cycle on a lambda they did not need to write.

The deletion test from the grilling: if we move all 20 to TOML, what changes? Adapter behavior is identical. Adding a new tool is now a data edit instead of a code edit. The cost is one parser function (`_build_detector`) and one TOML file. The win is that Tier 3 stops being a code surface that grows on every new tool added.

## Decision

The 20 Tier 3 entries move into `scripts/adapters/tier3.toml`. Schema:

```toml
[[tier3]]
name = "kiro"
detect.home_dir = ".kiro"

[[tier3]]
name = "goose"
detect.cli = "goose"

[[tier3]]
name = "junie"
detect.vscode_extension = "jetbrains.junie"

[[tier3]]
name = "zed"
detect.app_bundle = "/Applications/Zed.app"

[[tier3]]
name = "aide"
detect.any_of = [
    { home_dir = ".aide" },
    { cli = "aide" },
]
```

`scripts/adapters/tier3.py` becomes a thin loader:

```python
def _build_detector(detect: dict) -> Callable[[], bool]:
    if "home_dir" in detect:
        ...
    if "cli" in detect:
        ...
    if "vscode_extension" in detect:
        ...
    if "app_bundle" in detect:
        ...
    if "any_of" in detect:
        sub_detectors = [_build_detector(sub) for sub in detect["any_of"]]
        return lambda: any(d() for d in sub_detectors)
    raise ValueError(...)

def _load_tier3_adapters() -> list[Adapter]:
    with TIER3_TOML.open("rb") as f:
        data = tomllib.load(f)
    return [
        TierThreeAdapter(
            name=entry["name"],
            detector=_build_detector(entry["detect"]),
        )
        for entry in data.get("tier3", [])
    ]

ADAPTERS = _load_tier3_adapters()
```

TOML over JSON or YAML:

- **JSON** was considered for consistency with `mcp/<name>.json` bundles. Rejected because inline composite detection (`any_of`) reads worse in JSON than TOML, and because the rest of the playbook (`profiles/*.toml`, `pyproject.toml`) is already TOML-leaning.
- **YAML** was considered for AGENTS.md-style frontmatter consistency. Rejected because adding a YAML dependency is heavier than using `tomllib` from Py 3.11 stdlib, and because YAML's whitespace sensitivity has caused more bugs than it has prevented in the playbook's history.

tomllib is Python 3.11+ stdlib; no new third-party dependency.

## Consequences

### Good

- Adding a new Tier 3 tool with one of the five idioms is a data-only edit. No Python knowledge needed.
- The five-idiom schema documents the shape of "Tier 3 detection" explicitly, instead of implicitly through 20 lambdas.
- `tier3.py` shrinks; the install body is the only behavior surface.
- A future check (`scripts/checks/tier3_registry.py`) can validate that every entry is reachable through the five idioms without running Python.

### Bad

- Adding a new detection idiom (e.g. "true if homebrew formula is installed") requires touching both `tier3.py` (new branch in `_build_detector`) and the TOML schema definition in the file header. Two-place change instead of one-place, but the schema additions should be rare.
- Errors that previously were Python NameError ("which is not defined") are now ValueError from `_build_detector` at import time. The error path moved; the failure mode is still fail-fast.
- TOML inline tables for `any_of` are visually heavier than the Python `or` expression they replace. Acceptable tradeoff for the data-edit win.

## Implementation note

`tier3.toml` lives alongside `tier3.py` so the directory is self-contained. The loader runs at module import time (the file is read once per Python session); the parsed result populates `ADAPTERS` exactly as before.

`_build_detector` raises `ValueError` on an unknown detection idiom so a typo in `tier3.toml` fails at install time rather than at detect time (where the symptom would be "the tool silently never matches").

Future Tier 3 entries that need detection rules outside the five idioms remain possible: extend `_build_detector` with a new branch, document the new idiom in the schema comment block, and the rest of the system stays unchanged.
