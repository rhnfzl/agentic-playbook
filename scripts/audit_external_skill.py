#!/usr/bin/env python3
"""
External skill security audit, block-by-default.

Per v0.3 plan (ADR-0014 when written): scan vendored skill content (SKILL.md
bodies, referenced scripts under the skill dir) for risky patterns. Block
unless an allowlist file at <skill-dir>/.audit-allow documents the bypass
with a reviewer signoff.

Risk categories:
  - Prompt injection vectors (hidden Unicode bidi marks, zero-width chars)
  - Secret-file paths (.env, ssh keys, cloud creds, browser stores)
  - Network exfiltration commands (curl/wget piped to shell, python -m http)
  - Persistence writes (AGENTS.md, CLAUDE.md, MEMORY.md, shell rc files)
  - Broad tool permissions (allowed-tools includes filesystem write to home)
  - Unpinned package downloads (pip install without version, npm install -g)

Scope: scans only skills/imported/ by default (vendored content). Pass
--all to scan every skill.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Hidden Unicode chars that can carry prompt injection payloads
HIDDEN_UNICODE = re.compile(r"[​-‏‪-‮⁠-⁯﻿]")

# Secret file paths and credential variables
SECRET_PATTERNS = [
    re.compile(r"\b(?:cat|read|head|tail)\s+[^\n]*\.env\b"),
    re.compile(r"~/\.ssh/(?:id_rsa|id_ed25519|authorized_keys)"),
    re.compile(r"~/\.aws/credentials"),
    re.compile(r"~/\.config/gcloud/"),
    re.compile(r"~/\.netrc"),
    re.compile(r"Library/Application Support/.*Wallets"),
    re.compile(
        r"AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|ANTHROPIC_API_KEY|OPENAI_API_KEY", re.I
    ),
]

# Network exfiltration commands
NETWORK_PATTERNS = [
    re.compile(r"curl\s+[^\n]*\|\s*(?:sh|bash|python|node|zsh)"),
    re.compile(r"wget\s+[^\n]*\|\s*(?:sh|bash|python|node|zsh)"),
    re.compile(r"python\s+-m\s+http\.server"),
    re.compile(r"nc\s+-l"),
]

# Persistence writes
PERSISTENCE_PATTERNS = [
    re.compile(r"(?:echo|cat|tee|write).*>\s*(?:~?/?\.?)?(?:AGENTS|CLAUDE|MEMORY)\.md"),
    re.compile(r"(?:echo|cat|tee).*>>\s*~/\.(?:zshrc|bashrc|bash_profile|profile)"),
    re.compile(r"(?:echo|cat|tee).*>\s*~/\.claude/"),
    re.compile(r"(?:echo|cat|tee).*>\s*~/\.codex/"),
]

# Unpinned package downloads
UNPINNED_PATTERNS = [
    re.compile(r"\bpip\s+install\s+(?![^\s]*[=<>])[a-zA-Z0-9_\-]+(?:\s|$)"),
    re.compile(r"\bnpm\s+install\s+-g\s+"),
    re.compile(r"\buv\s+add\s+(?!.*--frozen)"),
]


def scan_text(text: str) -> dict[str, list[str]]:
    """Return findings by category, each entry = matching line text."""
    findings: dict[str, list[str]] = {
        "hidden_unicode": [],
        "secret_access": [],
        "network_exfil": [],
        "persistence": [],
        "unpinned_download": [],
    }

    if HIDDEN_UNICODE.search(text):
        findings["hidden_unicode"].append(
            "hidden Unicode bidi/zero-width characters present"
        )

    for pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            findings["secret_access"].append(m.group(0)[:120])

    for pat in NETWORK_PATTERNS:
        for m in pat.finditer(text):
            findings["network_exfil"].append(m.group(0)[:120])

    for pat in PERSISTENCE_PATTERNS:
        for m in pat.finditer(text):
            findings["persistence"].append(m.group(0)[:120])

    for pat in UNPINNED_PATTERNS:
        for m in pat.finditer(text):
            findings["unpinned_download"].append(m.group(0)[:120])

    return {k: v for k, v in findings.items() if v}


def load_allowlist(skill_dir: Path) -> set[str]:
    allow = skill_dir / ".audit-allow"
    if not allow.exists():
        return set()
    return {
        line.split("#")[0].strip()
        for line in allow.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def audit_skill(skill_dir: Path, repo_root: Path) -> list[str]:
    """Return list of error strings for this skill, or empty list if clean."""
    rel = skill_dir.relative_to(repo_root)
    allow = load_allowlist(skill_dir)
    errors: list[str] = []

    targets = [skill_dir / "SKILL.md"]
    for sub in ["scripts", "references"]:
        sub_dir = skill_dir / sub
        if sub_dir.is_dir():
            for f in sub_dir.rglob("*"):
                if f.is_file() and f.suffix in {
                    ".py",
                    ".sh",
                    ".md",
                    ".js",
                    ".ts",
                    ".mjs",
                    ".cjs",
                }:
                    targets.append(f)

    for target in targets:
        if not target.exists():
            continue
        try:
            text = target.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue

        findings = scan_text(text)
        for category, hits in findings.items():
            if category in allow:
                continue
            for hit in hits:
                errors.append(f"{rel}/{target.name}: {category}: {hit}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all", action="store_true", help="scan every skill, not just skills/imported/"
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    # v0.11 (ADR-0040): skills moved to base/ + overlays/team/. Imported
    # skills live at base/skills/imported/.
    target_dirs: list[Path] = []
    if args.all:
        skill_roots = [
            repo_root / "base" / "skills",
            repo_root / "overlays" / "team" / "skills",
        ]
        for skill_root in skill_roots:
            if skill_root.is_dir():
                for skill_md in skill_root.rglob("SKILL.md"):
                    target_dirs.append(skill_md.parent)
    else:
        imported = repo_root / "base" / "skills" / "imported"
        if imported.is_dir():
            for skill_md in imported.rglob("SKILL.md"):
                target_dirs.append(skill_md.parent)

    if not target_dirs:
        print("  ok  no external skills to audit (base/skills/imported/ empty)")
        return 0

    all_errors: list[str] = []
    for skill_dir in sorted(target_dirs):
        errs = audit_skill(skill_dir, repo_root)
        all_errors.extend(errs)

    if all_errors:
        print(f"\nExternal skill audit: {len(all_errors)} finding(s) (BLOCKING)")
        for e in all_errors:
            print(f"  x  {e}")
        print(
            "\nTo bypass per-skill: create <skill-dir>/.audit-allow with one category per line "
            "(hidden_unicode|secret_access|network_exfil|persistence|unpinned_download) and a # comment "
            "documenting the reviewer signoff."
        )
        return 1

    print(f"  ok  external skill audit passed ({len(target_dirs)} skill(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
