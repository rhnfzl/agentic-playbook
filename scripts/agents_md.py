"""AgentsMd document type (ADR-0027).

A parsed-and-render-able representation of an AGENTS.md file. Today's
codebase touches AGENTS.md in five places (check_agents_md, playbook_init,
playbook_update, adapter _loader managed-block helpers, and the per-project
init scaffold) with five different mental models. AgentsMd consolidates the
parse / render / validate surface so each consumer can lean on one type.

Schema (per ADR-0013):

  ---
  Owner: <handle>
  last_reviewed: YYYY-MM-DD
  profile: <slug>
  ---

  READ <playbook>/AGENTS.md BEFORE ANYTHING (skip if missing).

  ## Purpose
  ...
  ## What Lives Here
  ...
  (+ 6 other required sections)

The 8-section template is NOT enforced structurally; validate() reports
missing or extra sections against a configured required list, so a malformed
or partial AGENTS.md still parses (issues surface via validate()).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

# Per Codex review P2 (round 2): importing from adapters at module load
# time triggers adapters/__init__.py, which loads each adapter module,
# each of which imports AgentsMd back from this still-loading module. A
# direct `import agents_md` from a fresh interpreter previously raised
# ImportError. Fix: duplicate MARKER_ID locally (single-string constant;
# value matches adapters._protocol.MARKER_ID) and defer Rule to
# TYPE_CHECKING so the type lookup happens at static-analysis time only.
# The module is now standalone-importable.
MARKER_ID = "coding-agents-playbook"

if TYPE_CHECKING:
    from adapters._protocol import Rule

# Per ADR-0013, AGENTS.md files we author follow this 8-section template.
DEFAULT_REQUIRED_SECTIONS = [
    "Purpose",
    "What Lives Here",
    "Local Commands",
    "Edit Rules",
    "Required Checks",
    "Required Skills",
    "Do Not",
    "Owner And Freshness",
]

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?\n)---\s*\n", re.DOTALL)
_POINTER_RE = re.compile(r"^READ\s+.+?\s+BEFORE\s+ANYTHING.*?$", re.MULTILINE)
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_LAST_REVIEWED_RE = re.compile(r"^last_reviewed:\s*\d{4}-\d{2}-\d{2}\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Section:
    """One H2 section of an AGENTS.md. Body is everything until the next H2."""

    heading: str
    body: str


@dataclass(frozen=True)
class ValidationIssue:
    """One problem flagged by AgentsMd.validate(). Severity follows the
    CheckResult vocabulary from Candidate 5 so check_agents_md can route
    issues directly without translation.
    """

    severity: Literal["warn", "fail"]
    message: str


@dataclass(frozen=True)
class AgentsMd:
    """Parsed AGENTS.md document. Parse via AgentsMd.parse(text); round-trip
    via .render(). validate() reports schema issues per ADR-0013's template.
    """

    frontmatter: dict[str, str] = field(default_factory=dict)
    pointer: str | None = None
    sections: list[Section] = field(default_factory=list)
    raw: str = ""

    @classmethod
    def parse(cls, text: str) -> "AgentsMd":
        """Best-effort parse: malformed input still produces an AgentsMd
        with whatever was recoverable.
        """
        frontmatter: dict[str, str] = {}
        body = text
        match = _FRONTMATTER_RE.match(text)
        if match:
            block = match.group(1)
            for line in block.splitlines():
                m = re.match(r"^([\w_-]+)\s*:\s*(.*)$", line.strip())
                if m:
                    frontmatter[m.group(1)] = m.group(2).strip()
            body = text[match.end() :]

        pointer_match = _POINTER_RE.search(body)
        pointer = pointer_match.group(0).strip() if pointer_match else None

        sections: list[Section] = []
        headings = list(_SECTION_RE.finditer(body))
        for i, h in enumerate(headings):
            heading = h.group(1).strip()
            start = h.end()
            end = headings[i + 1].start() if i + 1 < len(headings) else len(body)
            sections.append(Section(heading=heading, body=body[start:end].strip()))

        return cls(
            frontmatter=frontmatter,
            pointer=pointer,
            sections=sections,
            raw=text,
        )

    @classmethod
    def load(cls, path: Path) -> "AgentsMd":
        """Load and parse an AGENTS.md file from disk."""
        return cls.parse(path.read_text(encoding="utf-8"))

    def render(self) -> str:
        """Return the original raw text. Round-trips losslessly; mutation
        methods (refresh_pointer, with_last_reviewed) return new instances
        whose raw is the updated text.
        """
        return self.raw

    def with_last_reviewed(self, today: str) -> "AgentsMd":
        """Return a new AgentsMd with the last_reviewed frontmatter line
        bumped to `today` (YYYY-MM-DD). No-op if the line is already current.
        """
        new_raw = _LAST_REVIEWED_RE.sub(f"last_reviewed: {today}", self.raw, count=1)
        if new_raw == self.raw:
            return self
        return AgentsMd.parse(new_raw)

    def with_refreshed_pointer(self, playbook_root: Path) -> "AgentsMd":
        """Return a new AgentsMd whose pointer line points at the current
        playbook_root. No-op if the pointer is already correct.
        """
        new_pointer = (
            f"READ {playbook_root}/AGENTS.md BEFORE ANYTHING (skip if missing)."
        )
        new_raw = re.sub(
            r"^READ .+ BEFORE ANYTHING.+$",
            new_pointer,
            self.raw,
            count=1,
            flags=re.MULTILINE,
        )
        if new_raw == self.raw:
            return self
        return AgentsMd.parse(new_raw)

    def validate(
        self,
        required_sections: list[str] | None = None,
    ) -> list[ValidationIssue]:
        """Report schema issues against the ADR-0013 template.

        Default required sections = DEFAULT_REQUIRED_SECTIONS (the 8-section
        template). Pass a custom list to validate against a different schema
        (e.g. a minimal 3-section subset for tier-3 tools).
        """
        required = required_sections or DEFAULT_REQUIRED_SECTIONS
        issues: list[ValidationIssue] = []
        heading_set = {s.heading for s in self.sections}
        for needed in required:
            if needed not in heading_set:
                issues.append(
                    ValidationIssue("fail", f"missing required section: {needed}")
                )

        # Duplicate-heading detection: if any heading appears more than once,
        # section() will silently return the first occurrence and downstream
        # consumers may render the wrong body. Flag as warn so users see it.
        seen: set[str] = set()
        for sec in self.sections:
            if sec.heading in seen:
                issues.append(
                    ValidationIssue("warn", f"duplicate section heading: {sec.heading}")
                )
            seen.add(sec.heading)

        if "Owner" not in self.frontmatter and "owner" not in self.frontmatter:
            issues.append(
                ValidationIssue("warn", "no Owner / owner field in frontmatter")
            )
        if "last_reviewed" not in self.frontmatter:
            issues.append(
                ValidationIssue("warn", "no last_reviewed field in frontmatter")
            )
        return issues

    def section(self, heading: str) -> Section | None:
        """Look up a section by heading. Case-sensitive exact match."""
        for s in self.sections:
            if s.heading == heading:
                return s
        return None

    @classmethod
    def empty(cls) -> "AgentsMd":
        """Return an empty AgentsMd. Used as the starting point when the
        on-disk file does not yet exist and an adapter is about to write
        its managed block.
        """
        return cls()

    @classmethod
    def load_or_empty(cls, path: Path) -> "AgentsMd":
        """Load an AGENTS.md from disk, or return empty() if the file does
        not exist. Convenience for the common adapter pattern
        AgentsMd.load_or_empty(p).with_managed_rules(...).save_to(p).
        """
        if path.exists():
            return cls.load(path)
        return cls.empty()

    def with_managed_rules(
        self,
        rules: list[Rule],
        *,
        label: str | None = None,
        comment_style: Literal["html", "hash"] = "html",
    ) -> "AgentsMd":
        """Return a new AgentsMd with the playbook managed block updated.

        Composes the supplied rules into the canonical AGENTS.md body and
        inserts (or replaces) a marker-delimited managed block. Content
        outside the markers is preserved across calls, so hand-authored
        sections survive re-installs.

        comment_style="hash" emits Codex-style `# ... #` markers; "html"
        emits the default `<!-- ... -->` markers used everywhere else.
        label, when supplied, names the consuming adapter so a future
        reader can tell which adapter authored a given AGENTS.md.

        Raises ValueError if self.raw already contains malformed markers
        (BEGIN with no matching END, or duplicate BEGIN markers); refuses
        to silently corrupt user content.
        """
        body = _compose_rules_body(rules).rstrip()
        if label:
            intro = (
                f"Behavioral rules loaded by the {label} adapter from the "
                f"coding-agents-playbook installer."
            )
        else:
            intro = "Behavioral rules loaded from the coding-agents-playbook installer."
        header_text = (
            "# AGENTS.md\n\n"
            f"{intro} The block below is auto-managed; content outside the "
            f"markers is hand-authored and preserved across re-installs."
        )

        if comment_style == "hash":
            comment_prefix, comment_suffix = "#", ""
        else:
            comment_prefix, comment_suffix = "<!--", "-->"
        begin = _marker_line(comment_prefix, comment_suffix, MARKER_ID, "BEGIN")
        end = _marker_line(comment_prefix, comment_suffix, MARKER_ID, "END")
        block = f"{begin}\n{body}\n{end}"

        text = self.raw

        if not text:
            new_raw = header_text.rstrip() + "\n\n" + block + "\n"
            return AgentsMd.parse(new_raw)

        begin_idx = text.find(begin)
        if begin_idx >= 0:
            end_idx = text.find(end, begin_idx + len(begin))
            if end_idx < 0:
                raise ValueError(
                    f"AGENTS.md contains '{begin}' but no matching '{end}'. "
                    f"Refusing to corrupt. Resolve the file manually."
                )
            stray = text.find(begin, end_idx + len(end))
            if stray >= 0:
                raise ValueError(
                    f"AGENTS.md contains multiple '{begin}' markers. "
                    f"Refusing to choose. Resolve the file manually."
                )
            new_raw = text[:begin_idx] + block + text[end_idx + len(end) :]
        else:
            separator = (
                ""
                if text.endswith("\n\n")
                else ("\n" if text.endswith("\n") else "\n\n")
            )
            new_raw = text + separator + block + "\n"

        return AgentsMd.parse(new_raw)

    def save_to(self, path: Path) -> Literal["created", "unchanged", "replaced"]:
        """Write the rendered document to path; report the action taken.

        Returns:
          "created"   - path did not exist; file (and parents) were created.
          "unchanged" - on-disk content already matches self.render().
          "replaced"  - on-disk content was overwritten with self.render().
        """
        rendered = self.render()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(rendered, encoding="utf-8")
            return "created"
        existing = path.read_text(encoding="utf-8")
        if existing == rendered:
            return "unchanged"
        path.write_text(rendered, encoding="utf-8")
        return "replaced"


def _compose_rules_body(rules: list[Rule]) -> str:
    """Concatenate rules into a single AGENTS.md body.

    Each rule's first heading becomes a section. Rules without headings
    get a heading derived from the filename slug. This duplicates the
    private composition logic from adapters/_writer.py to keep AgentsMd
    self-contained (no cross-package dependency on the adapter writer).
    """
    parts: list[str] = []
    for rule in rules:
        body = rule.body.strip()
        if not body.startswith("#"):
            heading = "# " + rule.name.replace("-", " ").title()
            body = f"{heading}\n\n{body}"
        parts.append(body)
    return "\n\n".join(parts) + "\n"


def _marker_line(prefix: str, suffix: str, marker_id: str, label: str) -> str:
    body = f"{prefix} {marker_id} {label}"
    return f"{body} {suffix}" if suffix else body
