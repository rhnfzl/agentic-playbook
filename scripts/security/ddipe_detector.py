"""Document-Driven Implicit Payload Execution detector.

The threat: a skill's SKILL.md includes a "reference implementation"
fenced code block that the agent reads as instructions and then
reproduces in the user's terminal. The block looks like documentation
but is actually a payload (curl|sh, rm -rf, eval-of-base64, etc.).

We extract fenced code blocks and flag risky tokens. We do NOT scan
the prose around them because the existing pattern audit already
catches most narrative risks; this detector is specifically for the
"agent will copy this verbatim" payload surface.

Pure Python, no external dependencies. Findings are not dispositive
on their own; the aggregator pairs them with severity + skill context.
"""

from __future__ import annotations

import re
from pathlib import Path

from . import Finding


FENCE = re.compile(r"```(?:\w+)?\n(.*?)```", re.DOTALL)

RISKY = [
    (
        re.compile(r"\bcurl\s+[^\n]*\|\s*(?:sh|bash|zsh|python|node)"),
        "high",
        "curl piped to shell",
    ),
    (
        re.compile(r"\bwget\s+[^\n]*\|\s*(?:sh|bash|zsh|python|node)"),
        "high",
        "wget piped to shell",
    ),
    (re.compile(r"\beval\s+[\"`]\$\("), "high", "eval of command substitution"),
    (
        re.compile(r"\beval\s*\(\s*atob\(", re.IGNORECASE),
        "critical",
        "eval of base64-decoded payload",
    ),
    (
        re.compile(r"\brm\s+-rf\s+~?/?\s*$", re.MULTILINE),
        "critical",
        "rm -rf of home or root",
    ),
    (re.compile(r"\bsudo\s+rm\s+-rf"), "critical", "sudo rm -rf"),
    (re.compile(r"\bchmod\s+\+s\b"), "high", "setuid bit set"),
    (re.compile(r"\bnc\s+-l\b"), "high", "netcat listener"),
    (
        re.compile(r"\bpython\s+-c\s+[\"']import\s+os.*?system\("),
        "high",
        "python -c os.system payload",
    ),
    (re.compile(r">\s*/dev/tcp/"), "high", "bash /dev/tcp redirection (reverse shell)"),
]


def scan_skill_md(skill_md: Path, repo_root: Path) -> list[Finding]:
    """Return findings for one SKILL.md file."""
    try:
        text = skill_md.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    findings: list[Finding] = []
    for block in FENCE.findall(text):
        for pat, severity, label in RISKY:
            for hit in pat.finditer(block):
                snippet = hit.group(0).replace("\n", " ")[:120]
                findings.append(
                    Finding(
                        source="ddipe",
                        severity=severity,
                        skill_path=str(skill_md.parent.relative_to(repo_root)),
                        category=label,
                        message=f"fenced block contains {label}: {snippet}",
                        raw=snippet,
                    )
                )
    return findings


def scan_skill_dirs(skill_dirs: list[Path], repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for d in skill_dirs:
        md = d / "SKILL.md"
        if md.is_file():
            findings.extend(scan_skill_md(md, repo_root))
    return findings
