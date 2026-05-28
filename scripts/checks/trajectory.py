"""Trajectory shape + frontmatter linter (ADR-0044, ADR-0046).

Self-contained check (per ADR-0024 sibling pattern). Reads the pre-loaded
PlaybookContent.trajectories from the dispatcher and enforces:

  * Required frontmatter fields: name, description, skill, scenario, version,
    owner, last_reviewed, adapter_scope, model_pinned
  * No frontmatter value may begin with `TODO` (catches scaffolder placeholders)
  * `name` matches `<skill>/<scenario>` (quotes are stripped before compare)
  * `skill` resolves to an existing skill (first-party OR imported)
  * `scenario` matches the filename (stem)
  * `adapter_scope` is a non-empty subset of the known adapters
  * `input.phrasings` has at least one entry (warn if below 5)
  * `assertions:` has at least one entry; the harness has nothing to assert without it
  * `llm_judge.threshold`, `.rubric`, and `.model` are all present
  * `llm_judge.threshold` is in [0, 1]

The reader (_reader.load_trajectories) is intentionally permissive; THIS
gate is where shape violations become CI failures.

Warn-only (does not fail CI):
  * Phrasing count below 5 (Anthropic guidance threshold for trigger tests).
    Projects adopt incrementally; the warn keeps the signal visible without
    blocking day-one onboarding.
"""

from __future__ import annotations

from pathlib import Path

from adapters.trace_record import KNOWN_TRACE_ADAPTERS

from . import CheckContext, CheckResult


REQUIRED_FRONTMATTER = (
    "name",
    "description",
    "skill",
    "scenario",
    "version",
    "owner",
    "last_reviewed",
    "adapter_scope",
    "model_pinned",
)


REQUIRED_JUDGE_KEYS = ("threshold", "rubric", "model")


# Known adapters live in adapters/trace_record.py as the single source.
# The linter imports the same set the harness and trace shims use.
KNOWN_TRAJECTORY_ADAPTERS = KNOWN_TRACE_ADAPTERS


MIN_PHRASING_COUNT_WARN = 5  # Anthropic best-practice: 5 phrasings for trigger tests


def _unquote(value: str) -> str:
    """Strip a single leading/trailing matching quote pair, if present.

    Matches the convention in scripts/frontmatter_lint.py for SKILL.md.
    Keeps the linter robust to quoted scalars like `skill: "demo-skill"`.
    """
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in {'"', "'"}:
        return v[1:-1]
    return v


def _skill_resolves(repo_root: Path, skill: str) -> bool:
    """Does some base/skills/<category>/<skill>/SKILL.md exist?

    Handles both first-party skills (base/skills/<category>/<skill>/) and
    imported skills (base/skills/imported/<source>/<skill>/). The imported
    case is two directories deeper than first-party; we walk all eligible
    paths rather than assuming layout.
    """
    base_skills = repo_root / "base" / "skills"
    if not base_skills.is_dir():
        return False
    # Fast path: first-party layout.
    for category_dir in base_skills.iterdir():
        if not category_dir.is_dir():
            continue
        if (category_dir / skill / "SKILL.md").exists():
            return True
    # Imported layout: base/skills/imported/<source>/<skill>/SKILL.md
    imported = base_skills / "imported"
    if imported.is_dir():
        for source_dir in imported.iterdir():
            if not source_dir.is_dir():
                continue
            if (source_dir / skill / "SKILL.md").exists():
                return True
    return False


def run(ctx: CheckContext) -> CheckResult:
    content = ctx.content
    trajectories = getattr(content, "trajectories", [])
    if not trajectories:
        return CheckResult(
            status="ok",
            summary="trajectory lint",
            details=["  ok  no trajectories to lint"],
        )

    errors: list[str] = []
    warnings: list[str] = []
    checked = 0

    for traj in trajectories:
        checked += 1
        rel = traj.path
        try:
            rel = traj.path.relative_to(ctx.repo_root)
        except ValueError:
            rel = traj.path

        fm = traj.frontmatter

        # Required fields present and non-empty.
        for field in REQUIRED_FRONTMATTER:
            raw = fm.get(field, "")
            if not raw.strip():
                errors.append(f"{rel}: missing or empty frontmatter field '{field}'")
                continue
            if _unquote(raw).upper().startswith("TODO"):
                errors.append(
                    f"{rel}: frontmatter field '{field}' is still a TODO "
                    f"placeholder ({raw!r}); fill it in before committing"
                )

        declared_name = _unquote(fm.get("name", ""))
        expected_name = f"{traj.skill}/{traj.scenario}"
        if declared_name and declared_name != expected_name:
            errors.append(
                f"{rel}: frontmatter name '{declared_name}' does not match "
                f"expected '{expected_name}' (skill/scenario from path)"
            )

        declared_skill = _unquote(fm.get("skill", ""))
        if declared_skill and declared_skill != traj.skill:
            errors.append(
                f"{rel}: frontmatter skill '{declared_skill}' does not match "
                f"directory '{traj.skill}'"
            )

        declared_scenario = _unquote(fm.get("scenario", ""))
        if declared_scenario and declared_scenario != traj.scenario:
            errors.append(
                f"{rel}: frontmatter scenario '{declared_scenario}' does not match "
                f"filename stem '{traj.scenario}'"
            )

        if traj.skill and not _skill_resolves(ctx.repo_root, traj.skill):
            errors.append(
                f"{rel}: skill '{traj.skill}' does not resolve to any "
                f"base/skills/<category>/{traj.skill}/SKILL.md "
                f"(or imported/<source>/{traj.skill}/SKILL.md)"
            )

        # adapter_scope must be non-empty AND every entry known.
        if not traj.adapter_scope:
            errors.append(
                f"{rel}: adapter_scope is empty; trajectory will never be "
                f"executed by the harness. Set adapter_scope: [claude-code, ...] "
                f"as an inline list (block-list YAML is not supported)."
            )
        else:
            for adapter in traj.adapter_scope:
                if adapter not in KNOWN_TRAJECTORY_ADAPTERS:
                    errors.append(
                        f"{rel}: adapter_scope contains unknown adapter "
                        f"'{adapter}' (known: {sorted(KNOWN_TRAJECTORY_ADAPTERS)})"
                    )

        # Body sections.
        if not traj.input_phrasings:
            errors.append(
                f"{rel}: input.phrasings is empty (at least one phrasing required)"
            )
        elif len(traj.input_phrasings) < MIN_PHRASING_COUNT_WARN:
            warnings.append(
                f"{rel}: only {len(traj.input_phrasings)} phrasing(s); "
                f"Anthropic best-practice is {MIN_PHRASING_COUNT_WARN}"
            )

        # Body TODO scan: phrasings and rubric must not carry scaffolder
        # placeholders (third-review P2). The scaffolder writes "TODO first
        # phrasing" and "TODO Score the trajectory on:" intentionally; the
        # linter must refuse to accept them.
        for phrasing in traj.input_phrasings:
            if phrasing.strip().upper().startswith("TODO"):
                errors.append(
                    f"{rel}: input.phrasings still contains a TODO "
                    f"placeholder ({phrasing!r}); replace before committing"
                )
                break
        rubric_text = traj.llm_judge.get("rubric", "")
        if isinstance(rubric_text, str) and rubric_text.strip().upper().startswith("TODO"):
            errors.append(
                f"{rel}: llm_judge.rubric starts with TODO; replace the "
                f"scaffolded placeholder text before committing"
            )

        # Block-style call_order is intentionally NOT supported by the naive
        # YAML reader (third-review P2). The reader returns the value as an
        # empty string when it sees `- call_order:` followed by indented
        # block-list items, which would otherwise reach the matcher as
        # "expected list of dicts, got str." Fail closed at the linter.
        for assertion in traj.assertions:
            if "call_order" in assertion:
                value = assertion["call_order"]
                if not isinstance(value, list):
                    errors.append(
                        f"{rel}: call_order assertion must use inline "
                        f"list-of-dicts syntax (e.g. "
                        f"`call_order: [{{tool: X, before: Y}}]`). Block-style "
                        f"`- call_order:` followed by indented dict items is "
                        f"not supported by the naive YAML reader."
                    )
                else:
                    for entry in value:
                        if not isinstance(entry, dict):
                            errors.append(
                                f"{rel}: call_order entry is not a dict: {entry!r}"
                            )

        if not traj.assertions:
            errors.append(
                f"{rel}: assertions is empty; trajectory has no deterministic "
                f"checks for the harness to run (add at least one DSL primitive, "
                f"e.g. first_skill_loaded: {traj.skill or '<skill>'})"
            )

        # llm_judge required keys all present.
        for key in REQUIRED_JUDGE_KEYS:
            if not traj.llm_judge.get(key):
                errors.append(
                    f"{rel}: llm_judge.{key} is missing or empty; the hybrid "
                    f"match contract (ADR-0046) requires all three of "
                    f"{list(REQUIRED_JUDGE_KEYS)}"
                )

        threshold = traj.llm_judge.get("threshold")
        if threshold is not None:
            try:
                t = float(threshold)
            except (TypeError, ValueError):
                errors.append(
                    f"{rel}: llm_judge.threshold '{threshold}' is not a number"
                )
            else:
                if not (0.0 <= t <= 1.0):
                    errors.append(
                        f"{rel}: llm_judge.threshold {t} outside [0, 1]"
                    )

    details: list[str] = []
    if errors:
        details.append(f"  Trajectory lint: {len(errors)} error(s) in {checked} trajectory file(s)")
        details.extend(f"  x  {e}" for e in errors)
    if warnings:
        details.append(f"  Trajectory lint: {len(warnings)} warning(s)")
        details.extend(f"  !  {w}" for w in warnings)
    if not errors and not warnings:
        details.append(f"  ok  all {checked} trajectory file(s) valid")

    if errors:
        return CheckResult(
            status="fail",
            summary=f"trajectory lint ({len(errors)} error(s))",
            details=details,
        )
    if warnings:
        return CheckResult(
            status="warn",
            summary=f"trajectory lint ({len(warnings)} warning(s))",
            details=details,
        )
    return CheckResult(
        status="ok",
        summary="trajectory lint",
        details=details,
    )
