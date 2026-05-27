"""Internal helper for the remaining checks that wrap a legacy
`scripts/<name>.py:main()` body.

v0.10 lifted the helper out of `scripts/checks/__init__.py` so the
package's public surface is just `CheckResult` + `CheckContext`. Once
every check migrates its logic directly into `scripts/checks/<name>.py`
(future v0.x work), this whole module disappears.

Why keep the legacy-main capture pattern at all?

The five files under `scripts/check_*.py` and the three under
`scripts/{decay_check,frontmatter_lint,size_check,audit_external_skill}.py`
ARE invoked as standalone CLIs (Makefile `make audit`, hooks/templates
docs, ADR cross-references, tests). Moving each body into
`scripts/checks/<name>.py` would require also rewriting the standalone
script as a thin wrapper, which is more churn than a single v0.10
release should land. Instead we capture stdout from the legacy main()
and turn it into a CheckResult; the standalone invocation path stays
identical.
"""

from __future__ import annotations

import importlib
import io
from contextlib import redirect_stdout

from . import CheckResult


def capture_legacy_main(module_name: str, *, summary: str) -> CheckResult:
    """Invoke `<module>.main()` and wrap stdout into a CheckResult.

    The dispatcher's per-check section prints CheckResult.details, so
    capturing stdout preserves the legacy main()'s output verbatim.
    Exit code 0 maps to status="ok", anything else maps to "fail".

    Caller does not need to pass the playbook root: scripts/check.py
    already inserts the scripts/ directory into sys.path before
    invoking the check, so `importlib.import_module(<legacy-name>)`
    resolves without further setup.
    """
    legacy = importlib.import_module(module_name)
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = legacy.main()
    details = [line for line in buf.getvalue().splitlines() if line.strip()]
    return CheckResult(
        status="ok" if rc == 0 else "fail",
        summary=summary,
        details=details,
    )
