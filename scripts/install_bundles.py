"""MCP bundle lifecycle helpers (ADR-0026 / v0.8 C1 decomposition).

Per the ADR-0016 install.py size threshold, the bundle-related helpers
were extracted from `scripts/install.py` so the dispatcher module stays
under 1000 lines. This module owns:

  * `bundle_health_scripts(repo_root)` -- locate every
    `mcp/<name>/bundle/health.sh` (B1, ADR-0026 follow-through).
  * `run_bundle_health(script, timeout_sec=10)` -- subprocess wrapper
    with bounded timeout, returning (exit_code, stderr_tail). Exit code
    124 reserved for timeout per GNU `timeout(1)` convention.
  * `run_bundle_bootstraps(bundled_configs)` -- iterate every MCP config
    that ships a `bootstrap.sh` and invoke it. Idempotent; the bundle
    owns the logic.

The previous private underscore-prefix names (`_bundle_health_scripts`,
`_run_bundle_health`, `_run_bundle_bootstraps`) are re-exported from
`install.py` as thin shims to preserve the existing import contract for
the lifecycle tests.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


def bundle_health_scripts(repo_root: Path) -> list[Path]:
    """Return every `<mcp-root>/<name>/bundle/health.sh` found under repo_root.

    Bundles that conform to ADR-0026 ship a health.sh entry point that
    exits 0 when the bundle is healthy and non-zero with diagnostic
    stderr otherwise. `make doctor` aggregates these so a single command
    surfaces dead bundles (the v0.7 doctor-verify covers config + on-disk
    state; this layer covers runtime readiness specific to each bundle).

    v0.11 (ADR-0040): MCP bundles moved to base/mcp/ + overlays/team/mcp/.
    Walks both roots so doctor reports the full surface.
    """
    results: list[Path] = []
    for mcp_root in (
        repo_root / "base" / "mcp",
        repo_root / "overlays" / "team" / "mcp",
    ):
        if mcp_root.is_dir():
            results.extend(mcp_root.glob("*/bundle/health.sh"))
    return sorted(results)


def run_bundle_health(script: Path, *, timeout_sec: float = 10.0) -> tuple[int, str]:
    """Execute one bundle health.sh with a bounded timeout.

    Returns (exit_code, combined_stderr). Stderr is capped at 4 KiB so a
    runaway script can't flood the doctor output. Exit code 124 is
    reserved here for timeout (matches GNU `timeout(1)` convention) so
    callers can distinguish "script ran and failed" from "script hung".
    """
    try:
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        msg = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
        return 124, f"<timed out after {timeout_sec}s>\n{msg[:4096]}"
    stderr_tail = (result.stderr or "")[-4096:]
    return result.returncode, stderr_tail


def run_bundle_bootstraps(bundled_configs: list) -> None:
    """Run bootstrap.sh for each MCP bundle that ships one (ADR-0026).

    The bundle's bootstrap.sh is idempotent and self-contained: typically
    creates a venv, installs dependencies, prepares runtime state. The
    playbook installer just invokes it; the bundle owns the logic.

    Bundles WITHOUT bootstrap.sh are skipped silently (convention: if the
    file exists, run it).
    """
    for mcp in bundled_configs:
        if mcp.source_dir is None:
            continue
        # Per ADR-0026 (v0.5): heavy bundles ship bootstrap.sh under bundle/.
        # Legacy bundles may still place it at the bundle root; prefer
        # bundle/bootstrap.sh when present and fall back to the legacy
        # location for backwards compatibility.
        candidates = [
            mcp.source_dir / "bundle" / "bootstrap.sh",
            mcp.source_dir / "bootstrap.sh",
        ]
        bootstrap = next((c for c in candidates if c.is_file()), None)
        if bootstrap is None:
            continue
        print(f"  bootstrap: {mcp.name} ...", end=" ")
        try:
            result = subprocess.run(
                ["bash", str(bootstrap)],
                cwd=str(mcp.source_dir),
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode == 0:
                print("ok")
            else:
                print(f"failed (exit {result.returncode})")
                if result.stderr:
                    print(f"    stderr: {result.stderr[:400]}")
        except subprocess.TimeoutExpired:
            print("timeout (>180s)")
        except Exception as exc:  # pragma: no cover - defensive print only
            print(f"error: {exc}")


__all__ = [
    "bundle_health_scripts",
    "run_bundle_bootstraps",
    "run_bundle_health",
]
