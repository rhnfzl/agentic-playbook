"""Quality-gate checks (ADR-0024 sibling pattern: Adapter Protocol for checks).

Each check module exposes:
    name: str
    def run(ctx: CheckContext) -> CheckResult: ...

scripts/check.py is the dispatcher; it iterates CHECKS and aggregates the
exit code. Adding a check is one new file in this package plus one row in
CHECKS.

Architecture:

  * Self-contained checks (hook_source_unification, pyright_zero,
    human_html_allowlist) implement their logic directly in
    `scripts/checks/<name>.py` and return a fully-populated CheckResult
    with detail lines.

  * Legacy-wrapping checks (frontmatter, em-dashes, decay, size,
    agents-md, external-skill-audit, no-versions, skill-description-
    length, hook-metadata) call `capture_legacy_main` from
    `_legacy.py` to invoke a `scripts/<name>.py:main()` body and turn
    its stdout + exit code into a CheckResult. The standalone scripts
    stay shellable as `python3 scripts/<name>.py` -- a handful are
    invoked that way from Makefile targets (`make audit`) and from
    docs/templates/tests.

  v0.10: extracted the legacy-capture helper into its own module so the
  package's public surface is just CheckResult + CheckContext. Future
  versions can migrate individual checks into self-contained form by
  moving the legacy main() body into `scripts/checks/<name>.py`
  directly; until then each shim is two lines.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal, NamedTuple


class CheckResult(NamedTuple):
    """One check's outcome. Status drives the dispatcher's exit code:
    fail -> overall fail; warn -> success but printed prominently; ok -> success.
    """

    status: Literal["ok", "warn", "fail"]
    summary: str
    details: list[str]


@dataclass(frozen=True)
class CheckContext:
    """Shared by every check. `repo_root` is the playbook checkout; `content`
    is the pre-loaded PlaybookContent (per ADR-0024) so checks that walk the
    seven content types don't re-load them.
    """

    repo_root: Path
    content: object  # PlaybookContent; typed as object to avoid import cycle


from . import (  # noqa: E402
    adr_number_unique,
    agents_md,
    decay,
    em_dashes,
    external_skill_audit,
    frontmatter,
    hook_metadata,
    hook_source_unification,
    human_html_allowlist,
    ignored_containment,
    no_versions,
    playbook_version,
    pyright_zero,
    size,
    skill_description,
    skill_security,
    trajectory,
)


@dataclass(frozen=True)
class _Check:
    name: str
    run: Callable[[CheckContext], CheckResult]


CHECKS: list[_Check] = [
    _Check("frontmatter", frontmatter.run),
    _Check("agents-md", agents_md.run),
    _Check("external-skill-audit", external_skill_audit.run),
    _Check("skill-security", skill_security.run),
    _Check("size", size.run),
    _Check("decay", decay.run),
    _Check("em-dashes", em_dashes.run),
    _Check("no-versions-in-readmes", no_versions.run),
    _Check("skill-description-length", skill_description.run),
    _Check("hook-metadata", hook_metadata.run),
    _Check("hook-source-unification", hook_source_unification.run),
    _Check("pyright-zero", pyright_zero.run),
    _Check("human-html-allowlist", human_html_allowlist.run),
    _Check("adr-number-unique", adr_number_unique.run),
    _Check("ignored-containment", ignored_containment.run),
    _Check("playbook-version", playbook_version.run),
    _Check("trajectory", trajectory.run),
]
