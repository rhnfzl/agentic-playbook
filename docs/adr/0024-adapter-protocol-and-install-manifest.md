# 0024. Adapter Protocol + InstallManifest (single-source-of-truth lockfile)

## Status

Accepted (2026-05-25); landed in v0.4 after the grill-with-docs session resolved the design.

## Context

Through v0.3 the installer pipeline carried two god-tables that encoded per-Adapter knowledge in `scripts/install.py`:

1. **`AGENTS` detection registry** (28 lambdas across three tiers). Each entry mapped an adapter slug to a one-line detection check. Adding a new tool required editing `install.py`.
2. **`ADAPTER_DEST_PATHS`** (per ADR-0023). Each entry enumerated the (dir, glob, ownership) tuples the lockfile + lifecycle commands needed to walk. The Adapter modules themselves separately re-encoded the same paths in their `install()` bodies. Two sources of truth, kept in sync by hand.

The Adapter dispatch was also duck-typed: most modules exposed `install(repo_root)`, but `agents_md` required `install(repo_root, agent_name)` (called 20 times from the dispatcher with different names). `install_for_agent` special-cased `if tier == 3`. Adapters loaded their own content via `_loader.load_*(repo_root)`, so the same skills got parsed N times. Target resolution coupled adapters to a `PLAYBOOK_TARGET` env-var contract that crashed if the dispatcher forgot to call `resolve_target()` first.

ADR-0023 flagged the manifest-emitted-by-Adapter direction as future work. ADR-0016 noted the Lockfile-from-scan approach as the v0.3 starting point. The grilling session in 2026-05-25 resolved the open design questions in one pass.

## Decision

Promote `Adapter` to a typed Protocol; the dispatcher walks an explicit registry of Adapter instances; the Lockfile is generated from each Adapter's install() return value.

### Adapter Protocol

```python
class Adapter(Protocol):
    name: str   # slug, e.g. "claude-code"
    tier: int   # 1, 2, or 3

    def detect(self) -> bool: ...

    def install(
        self,
        content: PlaybookContent,
        target: Path | None,
    ) -> Iterable[InstalledPath]: ...
```

`typing.Protocol` (structural typing) rather than ABC: Adapters satisfy the contract without inheriting from a base class, which keeps each module independent.

### PlaybookContent + InstalledPath

```python
@dataclass(frozen=True)
class PlaybookContent:
    skills: list[Skill]
    rules: list[Rule]
    hooks: list[Hook]
    mcp_configs: list[McpConfig]
    agents: list[Agent]
    commands: list[Command]
    prompts: list[Prompt]

    @classmethod
    def load(cls, repo_root: Path) -> "PlaybookContent": ...


class InstalledPath(NamedTuple):
    path: Path
    ownership: Literal["owned", "managed"]
```

Dispatcher pre-loads `PlaybookContent` once. Adapters take what they need; the seven `load_*(repo_root)` functions still exist but aren't called N times anymore. `InstalledPath` is the unit of the manifest each Adapter returns; the dispatcher computes sha256 at Lockfile-write time so Adapters don't carry hashing responsibility. Ownership semantics follow ADR-0023 (`owned` = playbook fully owns; safe to unlink. `managed` = mixes playbook + user content; remove never unlinks).

### Registry

Each Adapter module exposes `ADAPTERS: list[Adapter]`. Most modules export one Adapter; `agents_md` exports twenty (one per Tier 3 tool) via `TierThreeAdapter(name, detector)` instances that share install() body. `scripts/adapters/__init__.py` declares the union explicitly:

```python
ALL_ADAPTERS = [
    *claude_code.ADAPTERS,
    *codex.ADAPTERS,
    # ...
    *agents_md.ADAPTERS,
]
```

Auto-walk was considered and rejected for explicitness: adding an Adapter is a single, traceable diff.

### Target plumbing

`PLAYBOOK_TARGET` env var retires. Target is passed explicitly into `install(content, target)`. `_loader.get_target()` is deleted. `_loader.resolve_target()` keeps its UX prompt but no longer reads or writes the env var; the dispatcher resolves target once and passes it through.

### Lockfile generation

`.playbook-lock.json` is now built from the Adapter manifests, not scanned from a global table. The schema is unchanged from v0.3 (ADR-0023 already supports `{sha256, ownership}` entries), so existing lockfiles parse forward without migration.

### materialize_rules helper (bundled per the grilling-session design)

The 8-fold repetition of the rules-write boilerplate (load + compose + hand-rolled header + upsert_managed_block) collapses into one helper in `_loader.py`:

```python
def materialize_rules(
    rules: list[Rule],
    path: Path,
    *,
    comment_style: Literal["html", "hash"] = "html",
    label: str | None = None,
) -> str: ...
```

Codex passes `comment_style="hash"`; every other Adapter uses the default. The canonical header lives in this helper and stops drifting across Adapters.

## Consequences

- The two god-tables in `install.py` (`AGENTS`, `ADAPTER_DEST_PATHS`) are deleted; adapter-specific knowledge lives only in each Adapter module.
- Adding a new Tier 1 / 2 tool: one new file under `scripts/adapters/`, one import in `__init__.py`. No edits to `install.py`.
- Adding a new Tier 3 tool: one new `TierThreeAdapter(...)` entry in `agents_md.ADAPTERS`.
- The Tier 3 dispatcher special case (`if tier == 3`) is gone; the 20 Tier 3 instances participate uniformly.
- `make list` / `make status` / `make remove` all read the Lockfile that the Adapters themselves authored. Drift between "what the Adapter writes" and "what the Lockfile records" is no longer possible (per ADR-0023 lifecycle ownership).
- Test surface: `test_adapters.py` validates the ADAPTERS list shape + `install(content, target)` contract directly, plus the existing idempotency + content-preservation rounds. All 192 checks pass.
- `materialize_rules` removes ~100 lines across the 8 Adapters that previously hand-rolled the same dance.

## Rejected alternatives

- **`install()` returns None + separate `installed_paths()` method.** Slight efficiency win (lifecycle commands can scan without re-running install), but two sources of truth (the write and the declaration) can silently drift. ADR-0023's "lifecycle drift" finding came from exactly this shape.
- **Bundle into Group Adapter for Tier 3.** `agents_md` would be one Adapter that internally iterates 20 tools. Lockfile entries for Tier 3 would collapse into one section, making `make remove` per-Tier-3-tool unobservable. Rejected: hiding multiplicity behind a wrapper is the worse abstraction.
- **Keep `PLAYBOOK_TARGET` env var.** Backward-compatible but loses one of the clearest wins from going to a typed Protocol (explicit DI removes hidden coupling). Tests injecting a target without setting env vars was the deciding factor.
- **Staged migration with dispatcher supporting both old + new shapes.** Smaller PRs but more code at any given moment, and the old code keeps working so contributors might not convert promptly. Big-bang migration of all 10 Adapters in one PR was preferred.

## v0.8 amendment: known gap, per-(adapter, config_path) managed_keys

The `managed_keys.mcp_servers` field records playbook-owned MCP server names per adapter. For adapters that write to a SINGLE native MCP config (claude-code, codex, windsurf), the schema is sufficient. For Cursor, which writes to BOTH `~/.cursor/mcp.json` AND `<target>/.cursor/mcp.json`, the same-name-different-config case is not representable: a name pre-existing in user config but freshly inserted into project (or vice versa) cannot be classified as "managed in config A, user-authored in config B".

The v0.8 work picked the safer trade-off (union pre-existing across configs to avoid claiming ownership over user-authored entries, accepting that project entries can orphan after profile narrow). Successive Codex reviews validated this is a known architectural gap. The proper fix is a per-(adapter, config_path) `managed_keys` schema with reconcile that honors per-config ownership. Tracked as v0.9 work in the handoff doc.

## Related

- ADR-0016 (Installer lifecycle): the Lockfile is now Adapter-emitted, not scanned via `ADAPTER_DEST_PATHS`.
- ADR-0023 (Lifecycle ownership + anchored-fs scope): the per-Adapter manifest noted as future work in v0.3 lands here in v0.4.
- ADR-0025 (Profile end-to-end): builds on `PlaybookContent` to filter before adapters see it.
- ADR-0027 (AgentsMd document type): can consume the materialize_rules helper as a primitive.
- Source: 2026-05-25 grilling session captured in `docs/human-html/2026-05-25-architecture-coding-agents-playbook-architecture-opportunities.html`.
