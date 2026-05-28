"""Trajectory shape + frontmatter linter (ADR-0043, ADR-0045).

Self-contained check (per ADR-0024 sibling pattern). Reads the pre-loaded
PlaybookContent.trajectories from the dispatcher and enforces:

  * Required frontmatter fields: name, description, skill, scenario, version,
    owner, last_reviewed, adapter_scope, model_pinned
  * `name` matches `<skill>/<scenario>`
  * `skill` resolves to an existing base/skills/<category>/<skill>/ directory
  * `scenario` matches the filename (stem)
  * `adapter_scope` is a subset of the known Tier-1 + Tier-2 adapters
  * `input.phrasings` has at least one entry
  * `llm_judge.threshold` is in [0, 1] when present

The reader (_reader.load_trajectories) is intentionally permissive; THIS
gate is where shape violations become CI failures.

Warn-only (does not fail CI):
  * Phrasing count below 5 (Anthropic guidance threshold for trigger tests).
    Projects adopt incrementally; the warn keeps the signal visible without
    blocking day-one onboarding.
"""

from __future__ import annotations

from pathlib import Path

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


# Known adapters the harness can run against (subset of the playbook's
# install adapters). Updated when new trace shims land per ADR-0044.
# v0.2 Phase 0: only adapter shape is locked; the actual shims arrive in
# Phase 1 (Claude Code) and Phase 3-4 (Codex, Cursor, Windsurf).
KNOWN_TRAJECTORY_ADAPTERS = {
    "claude-code",
    "codex",
    "cursor",
    "windsurf",
}


MIN_PHRASING_COUNT_WARN = 5  # Anthropic best-practice: 5 phrasings for trigger tests


def _skill_resolves(repo_root: Path, skill: str) -> bool:
    """Does <root>/base/skills/<category>/<skill>/ exist for some category?"""
    base_skills = repo_root / "base" / "skills"
    if not base_skills.is_dir():
        return False
    for category_dir in base_skills.iterdir():
        if not category_dir.is_dir():
            continue
        if (category_dir / skill / "SKILL.md").exists():
            return True
        # Imported skills layer one level deeper.
        if (category_dir / skill).is_dir() and any(
            (category_dir / skill).rglob("SKILL.md")
        ):
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

        for field in REQUIRED_FRONTMATTER:
            if not fm.get(field, "").strip():
                errors.append(f"{rel}: missing or empty frontmatter field '{field}'")

        declared_name = fm.get("name", "").strip()
        expected_name = f"{traj.skill}/{traj.scenario}"
        if declared_name and declared_name != expected_name:
            errors.append(
                f"{rel}: frontmatter name '{declared_name}' does not match "
                f"expected '{expected_name}' (skill/scenario from path)"
            )

        declared_skill = fm.get("skill", "").strip()
        if declared_skill and declared_skill != traj.skill:
            errors.append(
                f"{rel}: frontmatter skill '{declared_skill}' does not match "
                f"directory '{traj.skill}'"
            )

        declared_scenario = fm.get("scenario", "").strip()
        if declared_scenario and declared_scenario != traj.scenario:
            errors.append(
                f"{rel}: frontmatter scenario '{declared_scenario}' does not match "
                f"filename stem '{traj.scenario}'"
            )

        if traj.skill and not _skill_resolves(ctx.repo_root, traj.skill):
            errors.append(
                f"{rel}: skill '{traj.skill}' does not resolve to any "
                f"base/skills/<category>/{traj.skill}/SKILL.md"
            )

        for adapter in traj.adapter_scope:
            if adapter not in KNOWN_TRAJECTORY_ADAPTERS:
                errors.append(
                    f"{rel}: adapter_scope contains unknown adapter "
                    f"'{adapter}' (known: {sorted(KNOWN_TRAJECTORY_ADAPTERS)})"
                )

        if not traj.input_phrasings:
            errors.append(
                f"{rel}: input.phrasings is empty (at least one phrasing required)"
            )
        elif len(traj.input_phrasings) < MIN_PHRASING_COUNT_WARN:
            warnings.append(
                f"{rel}: only {len(traj.input_phrasings)} phrasing(s); "
                f"Anthropic best-practice is {MIN_PHRASING_COUNT_WARN}"
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
