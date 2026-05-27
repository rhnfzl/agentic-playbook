#!/usr/bin/env python3
"""Create, index, and validate human-facing HTML review artifacts.

Workspace-agnostic: resolves the workspace root via $HUMAN_HTML_ROOT,
then by walking up from CWD looking for docs/human-html/, then falling
back to CWD (used by `init` to seed a new workspace).

Canonical source: ~/.agents/skills/human-html/human_html_artifacts.py.
Per-workspace copies should be symlinks to this file.
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import os
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit


KINDS = (
    "plan",
    "review",
    "architecture",
    "understanding",
    "research",
    "decision",
    "prototype",
    "status",
)

NAME_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})-"
    r"(?P<kind>plan|review|architecture|understanding|research|decision|prototype|status)-"
    r"(?P<slug>[a-z0-9]+(?:-[a-z0-9]+)*)\.html$"
)
TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)


def resolve_root() -> Path:
    """Resolve the workspace root via env var, CWD walk-up, or CWD fallback."""
    env = os.environ.get("HUMAN_HTML_ROOT")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd().resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "docs" / "human-html").is_dir():
            return candidate
    return cwd


def artifact_dir(root: Path) -> Path:
    return root / "docs" / "human-html"


def index_file(root: Path) -> Path:
    return artifact_dir(root) / "index.html"


@dataclass(frozen=True)
class Artifact:
    path: Path
    href: str
    date: str
    kind: str
    slug: str
    title: str
    source: str


class ArtifactHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}
        self.has_body_marker = False
        self.hrefs: list[str] = []
        self.asset_refs: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {name.lower(): value or "" for name, value in attrs}
        tag_name = tag.lower()
        if tag_name == "meta":
            name = attr_map.get("name", "").lower()
            if name.startswith("artifact-"):
                self.meta[name] = html.unescape(attr_map.get("content", ""))
        if tag_name == "body" and attr_map.get("data-human-html-artifact") == "true":
            self.has_body_marker = True
        if tag_name == "a" and attr_map.get("href"):
            self.hrefs.append(html.unescape(attr_map["href"]))
        if tag_name == "script" and attr_map.get("src"):
            self.asset_refs.append(("script", html.unescape(attr_map["src"])))
        if tag_name == "img" and attr_map.get("src"):
            self.asset_refs.append(("img", html.unescape(attr_map["src"])))
        if (
            tag_name == "link"
            and attr_map.get("href")
            and "stylesheet" in attr_map.get("rel", "").lower().split()
        ):
            self.asset_refs.append(("stylesheet", html.unescape(attr_map["href"])))


def slugify(value: str) -> str:
    slug = value.lower().replace("&", " and ")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "artifact"


def parse_title(content: str, fallback: str) -> str:
    match = TITLE_RE.search(content)
    if not match:
        return fallback
    title = re.sub(r"\s+", " ", match.group("title")).strip()
    return html.unescape(title) or fallback


def iter_html_files(root: Path) -> list[Path]:
    adir = artifact_dir(root)
    if not adir.exists():
        return []
    idx = index_file(root).resolve()
    return sorted(p for p in adir.rglob("*.html") if p.is_file() and p.resolve() != idx)


def _validate_local_reference(
    root: Path,
    source_path: Path,
    raw_ref: str,
    label: str,
    errors: list[str],
) -> None:
    ref = raw_ref.strip()
    if not ref or ref.startswith("#"):
        return
    parsed = urlsplit(ref)
    if parsed.scheme or parsed.netloc:
        return
    if not parsed.path:
        return
    rel = source_path.relative_to(root)
    target_path = Path(unquote(parsed.path))
    if target_path.is_absolute():
        errors.append(f"{rel}: {label} {ref!r} must be relative, not absolute")
        return
    resolved = (source_path.parent / target_path).resolve()
    artifact_root = artifact_dir(root).resolve()
    try:
        resolved.relative_to(artifact_root)
    except ValueError:
        if label != "href":
            errors.append(f"{rel}: {label} {ref!r} leaves docs/human-html/")
        return
    if not resolved.exists():
        errors.append(f"{rel}: broken {label} {ref!r}")


def read_artifacts(root: Path) -> tuple[list[Artifact], list[str]]:
    artifacts: list[Artifact] = []
    errors: list[str] = []

    for path in iter_html_files(root):
        rel = path.relative_to(root)
        rel_from_artifacts = path.relative_to(artifact_dir(root))
        is_top_level = path.parent == artifact_dir(root)
        match = NAME_RE.match(path.name)
        content = path.read_text(encoding="utf-8")
        parser = ArtifactHTMLParser()
        parser.feed(content)
        meta = parser.meta

        identity_valid = True
        date = meta.get("artifact-created", "")
        kind = meta.get("artifact-kind", "")
        slug = rel_from_artifacts.with_suffix("").as_posix()

        if is_top_level and not match:
            errors.append(f"{rel}: filename must match YYYY-MM-DD-kind-slug.html")
            identity_valid = False

        if match:
            filename_date = match.group("date")
            filename_kind = match.group("kind")
            slug = match.group("slug")
            try:
                dt.date.fromisoformat(filename_date)
            except ValueError:
                errors.append(f"{rel}: invalid ISO date in filename")
                identity_valid = False
            if date and date != filename_date:
                errors.append(f"{rel}: artifact-created does not match filename date")
                identity_valid = False
            if kind and kind != filename_kind:
                errors.append(f"{rel}: artifact-kind does not match filename kind")
                identity_valid = False
            date = date or filename_date
            kind = kind or filename_kind

        if not parser.has_body_marker:
            errors.append(f'{rel}: missing body marker data-human-html-artifact="true"')
        if meta.get("artifact-audience") != "human":
            errors.append(f"{rel}: missing or invalid artifact-audience=human")
        if kind not in KINDS:
            errors.append(f"{rel}: missing or invalid artifact-kind")
            identity_valid = False
        try:
            dt.date.fromisoformat(date)
        except ValueError:
            errors.append(f"{rel}: missing or invalid artifact-created date")
            identity_valid = False

        for href in parser.hrefs:
            _validate_local_reference(root, path, href, "href", errors)
        for asset_kind, ref in parser.asset_refs:
            _validate_local_reference(root, path, ref, asset_kind, errors)

        if identity_valid:
            artifacts.append(
                Artifact(
                    path=path,
                    href=rel_from_artifacts.as_posix(),
                    date=date,
                    kind=kind,
                    slug=slug,
                    title=parse_title(
                        content, Path(slug).name.replace("-", " ").title()
                    ),
                    source=meta.get("artifact-source", "local"),
                )
            )

    return artifacts, errors


def root_html_errors(root: Path) -> list[str]:
    return [
        f"{p.relative_to(root)}: HTML artifacts are not allowed at workspace root"
        for p in sorted(root.glob("*.html"))
    ]


def render_index(artifacts: list[Artifact]) -> str:
    rows = "\n".join(
        "      <tr>"
        f"<td>{html.escape(a.date)}</td>"
        f'<td><span class="kind">{html.escape(a.kind)}</span></td>'
        f'<td><a href="{html.escape(a.href)}">{html.escape(a.title)}</a></td>'
        f"<td>{html.escape(a.source)}</td>"
        "</tr>"
        for a in sorted(
            artifacts, key=lambda item: (item.date, item.kind, item.slug), reverse=True
        )
    )
    if not rows:
        rows = '      <tr><td colspan="4" class="empty">No artifacts yet.</td></tr>'

    latest = max((a.date for a in artifacts), default="no artifacts")
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Human HTML Artifacts</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172033;
      --muted: #5f6d82;
      --line: #dce3ec;
      --soft: #f6f8fb;
      --accent: #226fb2;
      --accent-2: #c5542d;
      --good: #2d7a55;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    body {{ margin: 0; color: var(--ink); background: #fff; }}
    main {{ width: min(1120px, calc(100vw - 40px)); margin: 0 auto; padding: 44px 0 64px; }}
    header {{ display: flex; justify-content: space-between; gap: 24px; align-items: flex-end; border-bottom: 1px solid var(--line); padding-bottom: 24px; margin-bottom: 28px; }}
    h1 {{ margin: 0; font-size: clamp(2rem, 4vw, 3.4rem); line-height: 1; letter-spacing: 0; }}
    p {{ color: var(--muted); line-height: 1.55; max-width: 74ch; }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 13px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: var(--soft); color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
    tr:last-child td {{ border-bottom: 0; }}
    a {{ color: var(--accent); text-decoration: none; font-weight: 650; }}
    a:hover {{ text-decoration: underline; }}
    code {{ background: var(--soft); border: 1px solid var(--line); border-radius: 6px; padding: 2px 5px; }}
    .kind {{ display: inline-block; border: 1px solid color-mix(in srgb, var(--accent) 30%, var(--line)); background: color-mix(in srgb, var(--accent) 8%, white); color: var(--accent); border-radius: 999px; padding: 3px 9px; font-size: .8rem; font-weight: 700; }}
    .meta {{ color: var(--muted); font-size: .9rem; }}
    .empty {{ color: var(--muted); text-align: center; padding: 28px; }}
    .rules {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; margin: 28px 0; }}
    .rule {{ border: 1px solid var(--line); background: var(--soft); border-radius: 8px; padding: 16px; }}
    .rule b {{ display: block; margin-bottom: 6px; }}
    @media (max-width: 760px) {{
      header {{ display: block; }}
      .rules {{ grid-template-columns: 1fr; }}
      th:nth-child(4), td:nth-child(4) {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>Human HTML Artifacts</h1>
        <p>Workspace lane for review, planning, architecture, understanding, research, decision, prototype, and status artifacts intended for human reviewers.</p>
      </div>
      <div class="meta">Latest artifact {html.escape(latest)}</div>
    </header>
    <section class="rules" aria-label="Rules">
      <div class="rule"><b>One lane</b><code>docs/human-html/</code> and nested collections are validated.</div>
      <div class="rule"><b>One pattern</b><code>YYYY-MM-DD-kind-slug.html</code> keeps top-level files sortable.</div>
      <div class="rule"><b>One audience</b>Human review surfaces are HTML. Agent scratch notes can remain Markdown.</div>
    </section>
    <table>
      <thead>
        <tr><th>Date</th><th>Kind</th><th>Artifact</th><th>Source</th></tr>
      </thead>
      <tbody>
{rows}
      </tbody>
    </table>
  </main>
</body>
</html>
"""


def write_index(root: Path) -> None:
    adir = artifact_dir(root)
    adir.mkdir(parents=True, exist_ok=True)
    artifacts, errors = read_artifacts(root)
    if errors:
        raise SystemExit(
            "Cannot build index with invalid artifacts:\n" + "\n".join(errors)
        )
    idx = index_file(root)
    idx.write_text(render_index(artifacts), encoding="utf-8")
    print(f"indexed {len(artifacts)} artifact(s) -> {idx.relative_to(root)}")


def render_artifact(title: str, kind: str, date: str, source: str) -> str:
    escaped_title = html.escape(title)
    escaped_source = html.escape(source)
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="artifact-kind" content="{kind}">
  <meta name="artifact-audience" content="human">
  <meta name="artifact-created" content="{date}">
  <meta name="artifact-source" content="{escaped_source}">
  <title>{escaped_title}</title>
  <style>
    :root {{
      --ink: #172033;
      --muted: #5d6b7f;
      --line: #dce3ec;
      --soft: #f6f8fb;
      --blue: #226fb2;
      --orange: #c5542d;
      --green: #2d7a55;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; color: var(--ink); background: #ffffff; }}
    main {{ width: min(1180px, calc(100vw - 40px)); margin: 0 auto; padding: 42px 0 70px; }}
    header {{ border-bottom: 1px solid var(--line); padding-bottom: 24px; margin-bottom: 28px; }}
    .eyebrow {{ color: var(--blue); font-size: .78rem; font-weight: 750; text-transform: uppercase; letter-spacing: .12em; }}
    h1 {{ margin: 10px 0 12px; font-size: clamp(2rem, 4.4vw, 3.8rem); line-height: 1; letter-spacing: 0; }}
    h2 {{ margin: 0 0 12px; font-size: 1.25rem; }}
    p {{ color: var(--muted); line-height: 1.58; max-width: 78ch; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin: 28px 0; }}
    .panel {{ border: 1px solid var(--line); border-radius: 8px; padding: 18px; background: var(--soft); }}
    .panel strong {{ display: block; color: var(--ink); margin-bottom: 6px; }}
    .section {{ margin-top: 30px; }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }}
    th {{ background: var(--soft); color: var(--muted); font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; }}
    tr:last-child td {{ border-bottom: 0; }}
    code {{ background: white; border: 1px solid var(--line); border-radius: 6px; padding: 2px 5px; }}
    @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body data-human-html-artifact="true">
  <main>
    <header>
      <div class="eyebrow">{kind} artifact</div>
      <h1>{escaped_title}</h1>
      <p>Replace this scaffold with the reviewable artifact. Keep the file self-contained, visual where useful, and optimized for a human making a decision.</p>
    </header>
    <section class="grid" aria-label="Review frame">
      <div class="panel"><strong>Why it exists</strong><p>State the decision, review, or understanding task this page supports.</p></div>
      <div class="panel"><strong>What changed</strong><p>Summarize the relevant code, architecture, product, or research delta.</p></div>
      <div class="panel"><strong>Reviewer focus</strong><p>Call out where a human should spend attention first.</p></div>
    </section>
    <section class="section">
      <h2>Checklist</h2>
      <table>
        <thead><tr><th>Area</th><th>Signal</th><th>Status</th></tr></thead>
        <tbody>
          <tr><td>Contract</td><td>External behavior and API shape are explicit.</td><td>Draft</td></tr>
          <tr><td>Risk</td><td>Failure modes and rollback are visible.</td><td>Draft</td></tr>
          <tr><td>Verification</td><td>Checks and evidence are linked or embedded.</td><td>Draft</td></tr>
        </tbody>
      </table>
    </section>
  </main>
</body>
</html>
"""


WORKSPACE_README = """# Human HTML Artifacts

## What lives here

This directory holds the HTML pages your team actually opens to review work.
Plans before they get built. Code reviews before they get merged. Architecture
explainers when someone new is trying to understand a system. Status snapshots
when a stakeholder asks "where are we." Decision aids when there is a real
choice to make.

If the artifact is meant for a human to read and act on, it lives here as
a single self-contained `.html` file. Open one in a browser, share the path,
print to PDF, archive it; it is portable and it is legible.

Agent scratch notes, ticket drafts, durable references, and meeting transcripts
stay as Markdown elsewhere in the repo. Those are the agent's memory layer.
This directory is the human's review layer.

## Naming pattern

```text
YYYY-MM-DD-kind-slug.html
```

Nested portable collections under `docs/human-html/<collection>/` may use short
filenames such as `index.html` or `flow-overview.html`. They are still checked
recursively for required metadata, the human body marker, and local links.

Allowed kinds:

```text
plan review architecture understanding research decision prototype status
```

## Commands

The global script (resolves the workspace root automatically by walking up
from your current directory):

```bash
python3 ~/.agents/skills/human-html/human_html_artifacts.py new plan "Title to review"
python3 ~/.agents/skills/human-html/human_html_artifacts.py check
python3 ~/.agents/skills/human-html/human_html_artifacts.py index
```

The `new` command refreshes `index.html` after creating an artifact. The
autoindex hook also regenerates `index.html` after direct edits to HTML files in
this directory.

## Canonical source

Skill: `~/.agents/skills/human-html/SKILL.md`. Updates to the script, hooks,
or contract land there and propagate to every workspace that has wired the
hooks.
"""


def cmd_init(args: argparse.Namespace) -> None:
    """Initialise docs/human-html/ in the current directory."""
    root = Path.cwd().resolve() if not args.root else Path(args.root).resolve()
    adir = artifact_dir(root)
    if adir.exists() and not args.force:
        raise SystemExit(
            f"{adir} already exists; pass --force to overwrite README and reset index"
        )
    adir.mkdir(parents=True, exist_ok=True)
    readme = adir / "README.md"
    if not readme.exists() or args.force:
        readme.write_text(WORKSPACE_README, encoding="utf-8")
        print(f"created {readme.relative_to(root)}")
    write_index(root)
    print(f"initialised human-html harness at {adir.relative_to(root)}")


def cmd_new(args: argparse.Namespace) -> None:
    root = resolve_root()
    adir = artifact_dir(root)
    adir.mkdir(parents=True, exist_ok=True)
    date = args.date or dt.date.today().isoformat()
    try:
        dt.date.fromisoformat(date)
    except ValueError as exc:
        raise SystemExit(f"invalid --date value: {date}") from exc
    slug = slugify(args.slug or args.title)
    path = adir / f"{date}-{args.kind}-{slug}.html"
    if path.exists() and not args.force:
        raise SystemExit(
            f"{path.relative_to(root)} already exists, pass --force to overwrite"
        )
    path.write_text(
        render_artifact(args.title, args.kind, date, args.source), encoding="utf-8"
    )
    print(f"created {path.relative_to(root)}")
    write_index(root)


def cmd_check() -> int:
    root = resolve_root()
    artifacts, errors = read_artifacts(root)
    errors.extend(root_html_errors(root))
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print(f"ok: {len(artifacts)} human HTML artifact(s) validated")
    return 0


def cmd_index() -> None:
    write_index(resolve_root())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init", help="initialise docs/human-html/ in current dir"
    )
    init_parser.add_argument("--root", help="workspace root (default: CWD)")
    init_parser.add_argument("--force", action="store_true")

    new_parser = subparsers.add_parser("new", help="create a new artifact scaffold")
    new_parser.add_argument("kind", choices=KINDS)
    new_parser.add_argument("title")
    new_parser.add_argument("--slug")
    new_parser.add_argument("--date")
    new_parser.add_argument("--source", default="local")
    new_parser.add_argument("--force", action="store_true")
    new_parser.add_argument(
        "--index",
        action="store_true",
        help="deprecated compatibility flag; new always refreshes index.html",
    )

    subparsers.add_parser("index", help="refresh docs/human-html/index.html")
    subparsers.add_parser(
        "check", help="validate artifact names, metadata, and local links"
    )

    args = parser.parse_args(argv)
    if args.command == "init":
        cmd_init(args)
        return 0
    if args.command == "new":
        cmd_new(args)
        return 0
    if args.command == "index":
        cmd_index()
        return 0
    if args.command == "check":
        return cmd_check()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
