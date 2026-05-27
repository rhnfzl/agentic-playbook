#!/usr/bin/env python3
"""Local shared memory bridge for coding agents.

The bridge is intentionally local-first and agent-neutral. Agent-specific
systems can import from it through CLI, hooks, or the MCP wrapper in
agent_memory_mcp.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Iterable


def _resolve_workspace() -> Path:
    """Resolve the active workspace at import time.

    Resolution order:
    1. $AGENT_MEMORY_WORKSPACE (explicit override).
    2. $CLAUDE_PROJECT_DIR (Claude Code session signal).
    3. $CODEX_WORKSPACE (Codex session signal).
    4. cwd as a last resort.

    Per-workspace state lands under <workspace>/.agent-harness/memory/ unless
    DEFAULT_DB is overridden via env.
    """
    candidate = (
        os.environ.get("AGENT_MEMORY_WORKSPACE")
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or os.environ.get("CODEX_WORKSPACE")
        or str(Path.cwd())
    )
    return Path(candidate).expanduser().resolve()


def _discover_claude_memory_dirs() -> list[Path]:
    """Return every per-workspace Claude memory directory the bridge can see.

    Override with $AGENT_MEMORY_CLAUDE_DIRS (colon-separated absolute paths).
    Default: glob every ~/.claude/projects/*/memory that exists, so newly
    created workspaces are picked up without code changes.
    """
    explicit = os.environ.get("AGENT_MEMORY_CLAUDE_DIRS")
    if explicit:
        return [Path(p).expanduser() for p in explicit.split(":") if p.strip()]
    projects_root = Path.home() / ".claude" / "projects"
    if not projects_root.is_dir():
        return []
    return sorted(
        p / "memory" for p in projects_root.iterdir() if (p / "memory").is_dir()
    )


WORKSPACE = _resolve_workspace()
DEFAULT_DB = Path(
    os.environ.get(
        "AGENT_MEMORY_DB",
        str(WORKSPACE / ".agent-harness" / "memory" / "memory.sqlite"),
    )
).expanduser()
CLAUDE_DIGEST = Path(
    os.environ.get(
        "AGENT_MEMORY_CLAUDE_DIGEST",
        str(WORKSPACE / ".codex" / "memory" / "claude-memory-import.md"),
    )
).expanduser()
CLAUDE_MEMORY_DIRS = _discover_claude_memory_dirs()

SECRET_REDACTIONS = [
    (
        re.compile(
            r"(?i)([\"']?\b(?:api[_-]?key|token|secret|password|credential|private[_-]?key)\b[\"']?\s*[:=]\s*[\"']?)([^\"'\s,}]+)([\"']?)"
        ),
        r"\1[REDACTED]\3",
    ),
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"), "[REDACTED_OPENAI_KEY]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_-]*\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
        "[REDACTED_JWT]",
    ),
    (re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"), "[REDACTED_AWS_ACCESS_KEY]"),
    (
        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b"),
        "[REDACTED_GITHUB_TOKEN]",
    ),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED_GITHUB_TOKEN]"),
    (
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
            re.DOTALL,
        ),
        "[REDACTED_PRIVATE_KEY_BLOCK]",
    ),
    (
        re.compile(
            r"-----BEGIN PGP PRIVATE KEY BLOCK-----.*?-----END PGP PRIVATE KEY BLOCK-----",
            re.DOTALL,
        ),
        "[REDACTED_PGP_PRIVATE_KEY_BLOCK]",
    ),
]


@dataclass(frozen=True)
class MemoryRecord:
    title: str
    content: str
    kind: str = "learning"
    scope: str = "workspace"
    status: str = "active"
    source_path: str | None = None
    source_ref: str | None = None
    tags: tuple[str, ...] = ()
    confidence: str = "medium"
    writer: str = "agent-harness"
    trust: str = "advisory"


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def db_path_from_args(path: str | None) -> Path:
    return Path(path).expanduser().resolve() if path else DEFAULT_DB


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            kind TEXT NOT NULL,
            scope TEXT NOT NULL,
            status TEXT NOT NULL,
            content TEXT NOT NULL,
            source_path TEXT,
            source_ref TEXT,
            tags_json TEXT NOT NULL DEFAULT '[]',
            confidence TEXT NOT NULL DEFAULT 'medium',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_verified TEXT,
            review_after TEXT,
            expires_at TEXT
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
            memory_id UNINDEXED,
            title,
            content,
            tags,
            source
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event TEXT NOT NULL,
            memory_id TEXT,
            details_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """
    )
    ensure_columns(
        conn,
        "memories",
        {
            "writer": "TEXT NOT NULL DEFAULT 'unknown'",
            "trust": "TEXT NOT NULL DEFAULT 'advisory'",
            "content_hash": "TEXT",
            "source_hash": "TEXT",
        },
    )
    conn.commit()


def ensure_columns(
    conn: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    for name, ddl in columns.items():
        if name not in existing:
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")
            except sqlite3.OperationalError as exc:
                if "duplicate column" not in str(exc).lower():
                    raise


def normalize_tags(raw: str | Iterable[str] | None) -> tuple[str, ...]:
    if raw is None:
        return ()
    if isinstance(raw, str):
        parts = re.split(r"[, ]+", raw)
    else:
        parts = list(raw)
    normalized = []
    for part in parts:
        tag = re.sub(r"[^A-Za-z0-9_.-]+", "-", part.strip().lower()).strip("-")
        if tag and tag not in normalized:
            normalized.append(tag)
    return tuple(normalized)


def redact_secrets(text: str) -> str:
    redacted = text
    for pattern, replacement in SECRET_REDACTIONS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def memory_id(record: MemoryRecord) -> str:
    payload = "\n".join(
        [
            record.scope,
            record.kind,
            record.title,
            record.source_path or "",
            record.source_ref or "",
            record.content,
        ]
    )
    return "mem_" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists() or not candidate.is_file():
        return None
    digest = hashlib.sha256()
    with candidate.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def audit(
    conn: sqlite3.Connection, event: str, mem_id: str | None, details: dict[str, object]
) -> None:
    conn.execute(
        "INSERT INTO audit_log(event, memory_id, details_json, created_at) VALUES (?, ?, ?, ?)",
        (event, mem_id, json.dumps(details, sort_keys=True), utc_now()),
    )


def parse_since(value: str | None) -> str | None:
    if not value:
        return None
    match = re.fullmatch(r"(\d+)([mhdw])", value.strip().lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        multipliers = {
            "m": timedelta(minutes=amount),
            "h": timedelta(hours=amount),
            "d": timedelta(days=amount),
            "w": timedelta(weeks=amount),
        }
        return (
            (datetime.now(UTC) - multipliers[unit]).replace(microsecond=0).isoformat()
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--since must be an ISO timestamp or duration like 30m, 12h, 7d, 2w"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).replace(microsecond=0).isoformat()


def query_audit(
    conn: sqlite3.Connection,
    *,
    memory_id: str | None = None,
    writer: str | None = None,
    since: str | None = None,
    limit: int = 20,
) -> list[dict[str, object]]:
    clauses: list[str] = []
    params: list[object] = []
    if memory_id:
        clauses.append("memory_id = ?")
        params.append(memory_id)
    if writer:
        clauses.append("details_json LIKE ?")
        params.append(f'%"writer": "{writer}"%')
    if since:
        clauses.append("created_at >= ?")
        params.append(since)
    where = "WHERE " + " AND ".join(clauses) if clauses else ""
    rows = conn.execute(
        f"""
        SELECT id, event, memory_id, details_json, created_at
        FROM audit_log
        {where}
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    items: list[dict[str, object]] = []
    for row in rows:
        item = dict(row)
        try:
            item["details"] = json.loads(item.pop("details_json") or "{}")
        except json.JSONDecodeError:
            item["details"] = {"raw": item.pop("details_json")}
        items.append(item)
    return items


def format_audit_rows(rows: list[dict[str, object]]) -> str:
    if not rows:
        return "No audit events."
    lines: list[str] = []
    for row in rows:
        details = row.get("details") if isinstance(row.get("details"), dict) else {}
        detail_bits = []
        for key in ("status", "writer", "trust", "source_path"):
            value = details.get(key) if isinstance(details, dict) else None
            if value:
                detail_bits.append(f"{key}={value}")
        suffix = " " + " ".join(detail_bits) if detail_bits else ""
        lines.append(
            f"- {row['created_at']} event={row['event']} memory_id={row.get('memory_id')}{suffix}"
        )
    return "\n".join(lines)


def upsert_memory(conn: sqlite3.Connection, record: MemoryRecord) -> str:
    mem_id = memory_id(record)
    now = utc_now()
    tags_json = json.dumps(list(record.tags), sort_keys=True)
    existing = conn.execute(
        "SELECT id FROM memories WHERE id = ?", (mem_id,)
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE memories
            SET title = ?, kind = ?, scope = ?, status = ?, content = ?,
                source_path = ?, source_ref = ?, tags_json = ?, confidence = ?,
                writer = ?, trust = ?, content_hash = ?, source_hash = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                record.title,
                record.kind,
                record.scope,
                record.status,
                record.content,
                record.source_path,
                record.source_ref,
                tags_json,
                record.confidence,
                record.writer,
                record.trust,
                content_hash(record.content),
                file_hash(record.source_path),
                now,
                mem_id,
            ),
        )
        event = "updated"
    else:
        conn.execute(
            """
            INSERT INTO memories(
                id, title, kind, scope, status, content, source_path, source_ref,
                tags_json, confidence, writer, trust, content_hash, source_hash,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mem_id,
                record.title,
                record.kind,
                record.scope,
                record.status,
                record.content,
                record.source_path,
                record.source_ref,
                tags_json,
                record.confidence,
                record.writer,
                record.trust,
                content_hash(record.content),
                file_hash(record.source_path),
                now,
                now,
            ),
        )
        event = "created"
    sync_fts(conn, mem_id, record)
    audit(
        conn,
        event,
        mem_id,
        {
            "status": record.status,
            "source_path": record.source_path,
            "writer": record.writer,
            "trust": record.trust,
        },
    )
    conn.commit()
    return mem_id


def sync_fts(conn: sqlite3.Connection, mem_id: str, record: MemoryRecord) -> None:
    conn.execute("DELETE FROM memory_fts WHERE memory_id = ?", (mem_id,))
    conn.execute(
        "INSERT INTO memory_fts(memory_id, title, content, tags, source) VALUES (?, ?, ?, ?, ?)",
        (
            mem_id,
            record.title,
            record.content,
            " ".join(record.tags),
            " ".join(filter(None, [record.source_path, record.source_ref])),
        ),
    )


def fts_query(query: str) -> str:
    terms = re.findall(r"[A-Za-z0-9_./-]{2,}", query)
    cleaned = []
    for term in terms[:12]:
        token = term.replace('"', "")
        if token:
            cleaned.append(f'"{token}"')
    return " OR ".join(cleaned)


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    item = dict(row)
    item["tags"] = json.loads(item.pop("tags_json") or "[]")
    return item


def search_memories(
    conn: sqlite3.Connection,
    query: str,
    *,
    limit: int = 8,
    status: str = "active",
) -> list[dict[str, object]]:
    normalized = fts_query(query)
    if normalized:
        try:
            rows = conn.execute(
                """
                SELECT m.*, bm25(memory_fts) AS rank
                FROM memory_fts
                JOIN memories m ON m.id = memory_fts.memory_id
                WHERE memory_fts MATCH ? AND m.status = ?
                ORDER BY rank ASC, m.updated_at DESC
                LIMIT ?
                """,
                (normalized, status, limit),
            ).fetchall()
            return [row_to_dict(row) for row in rows]
        except sqlite3.OperationalError:
            pass

    like = f"%{query}%"
    rows = conn.execute(
        """
        SELECT *, 0 AS rank
        FROM memories
        WHERE status = ? AND (title LIKE ? OR content LIKE ? OR source_path LIKE ?)
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (status, like, like, like, limit),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def recent_memories(
    conn: sqlite3.Connection, *, limit: int = 8, status: str = "active"
) -> list[dict[str, object]]:
    rows = conn.execute(
        """
        SELECT *, 0 AS rank
        FROM memories
        WHERE status = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (status, limit),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def format_records(
    records: list[dict[str, object]], *, include_content: bool = True
) -> str:
    if not records:
        return "No matching memories."
    lines: list[str] = []
    for record in records:
        tags = ", ".join(record.get("tags", [])) or "none"
        lines.append(f"- {record['id']}: {record['title']}")
        lines.append(
            "  "
            f"kind={record['kind']} scope={record['scope']} status={record['status']} "
            f"trust={record.get('trust', 'advisory')} writer={record.get('writer', 'unknown')} "
            f"tags={tags}"
        )
        if record.get("source_path"):
            lines.append(f"  source={record['source_path']}")
        if include_content:
            content = str(record["content"]).strip()
            if len(content) > 1200:
                content = content[:1200].rstrip() + "..."
            for content_line in content.splitlines()[:18]:
                lines.append(f"  {content_line}")
    return "\n".join(lines)


def chunk_markdown(text: str, default_title: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_title = default_title
    current_lines: list[str] = []
    heading_re = re.compile(r"^(#{1,3})\s+(.+?)\s*$")
    for line in text.splitlines():
        match = heading_re.match(line)
        if match and current_lines:
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append((current_title, content))
            current_title = match.group(2).strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    content = "\n".join(current_lines).strip()
    if content:
        chunks.append((current_title, content))
    return chunks


def import_claude_memories(
    conn: sqlite3.Connection,
    *,
    include_source_claude: bool = False,
    promote_on_import: bool = False,
    dry_run: bool = False,
) -> list[tuple[str, str, str]]:
    sources = []
    if CLAUDE_DIGEST.exists():
        sources.append(CLAUDE_DIGEST)
    if include_source_claude:
        for memory_dir in CLAUDE_MEMORY_DIRS:
            if memory_dir.exists():
                sources.extend(sorted(memory_dir.glob("*.md")))

    imported: list[tuple[str, str, str]] = []
    status = "active" if promote_on_import else "pending"
    for source in sources:
        text = redact_secrets(source.read_text(encoding="utf-8", errors="replace"))
        for title, content in chunk_markdown(text, source.stem):
            record = MemoryRecord(
                title=f"Claude memory import: {title}",
                content=content,
                kind="imported-memory",
                scope="workspace",
                status=status,
                source_path=str(source),
                tags=("claude", "imported", "agent-memory"),
                confidence="medium",
                writer="claude-memory-import",
                trust="advisory" if promote_on_import else "pending-review",
            )
            mem_id = memory_id(record)
            imported.append((mem_id, record.title, record.status))
            if not dry_run:
                upsert_memory(conn, record)
    return imported


def set_status(conn: sqlite3.Connection, mem_id: str, status: str) -> bool:
    row = conn.execute("SELECT * FROM memories WHERE id = ?", (mem_id,)).fetchone()
    if not row:
        return False
    now = utc_now()
    conn.execute(
        "UPDATE memories SET status = ?, updated_at = ? WHERE id = ?",
        (status, now, mem_id),
    )
    record = MemoryRecord(
        title=row["title"],
        content=row["content"],
        kind=row["kind"],
        scope=row["scope"],
        status=status,
        source_path=row["source_path"],
        source_ref=row["source_ref"],
        tags=tuple(json.loads(row["tags_json"] or "[]")),
        confidence=row["confidence"],
        writer=row["writer"],
        trust=row["trust"],
    )
    sync_fts(conn, mem_id, record)
    audit(
        conn,
        status,
        mem_id,
        {"status": status, "writer": row["writer"], "trust": row["trust"]},
    )
    conn.commit()
    return True


def command_init(args: argparse.Namespace) -> int:
    db_path = db_path_from_args(args.db)
    conn = connect(db_path)
    count = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    print(f"memory_db: {db_path}")
    print(f"memories: {count}")
    return 0


def command_import_claude(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    imported = import_claude_memories(
        conn,
        include_source_claude=args.include_source_claude,
        promote_on_import=args.promote_on_import,
        dry_run=args.dry_run,
    )
    action = "would import" if args.dry_run else "imported"
    print(f"{action}: {len(imported)} memories")
    for mem_id, title, status in imported[: args.limit]:
        print(f"- {mem_id}: {title} status={status}")
    if len(imported) > args.limit:
        print(f"... {len(imported) - args.limit} more")
    return 0


def command_propose(args: argparse.Namespace) -> int:
    content = args.content
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8", errors="replace")
    if not content:
        print("error: --content or --content-file is required", file=sys.stderr)
        return 2
    conn = connect(db_path_from_args(args.db))
    record = MemoryRecord(
        title=args.title,
        content=redact_secrets(content),
        kind=args.kind,
        scope=args.scope,
        status="pending",
        source_path=args.source_path,
        source_ref=args.source_ref,
        tags=normalize_tags(args.tags),
        confidence=args.confidence,
        writer=args.writer,
        trust=args.trust,
    )
    mem_id = upsert_memory(conn, record)
    print(f"pending: {mem_id}")
    return 0


def command_add(args: argparse.Namespace) -> int:
    content = args.content
    if args.content_file:
        content = Path(args.content_file).read_text(encoding="utf-8", errors="replace")
    if not content:
        print("error: --content or --content-file is required", file=sys.stderr)
        return 2
    conn = connect(db_path_from_args(args.db))
    record = MemoryRecord(
        title=args.title,
        content=redact_secrets(content),
        kind=args.kind,
        scope=args.scope,
        status="active",
        source_path=args.source_path,
        source_ref=args.source_ref,
        tags=normalize_tags(args.tags),
        confidence=args.confidence,
        writer=args.writer,
        trust=args.trust,
    )
    mem_id = upsert_memory(conn, record)
    print(f"active: {mem_id}")
    return 0


def command_promote(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    if not set_status(conn, args.memory_id, "active"):
        print(f"not found: {args.memory_id}", file=sys.stderr)
        return 1
    print(f"promoted: {args.memory_id}")
    return 0


def command_reject(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    if not set_status(conn, args.memory_id, "rejected"):
        print(f"not found: {args.memory_id}", file=sys.stderr)
        return 1
    print(f"rejected: {args.memory_id}")
    return 0


def command_search(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    records = search_memories(conn, args.query, limit=args.limit, status=args.status)
    if args.json:
        print(json.dumps(records, indent=2, sort_keys=True))
    else:
        print(format_records(records, include_content=not args.no_content))
    return 0


def command_context(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    if args.query:
        records = search_memories(conn, args.query, limit=args.limit, status="active")
    else:
        records = recent_memories(conn, limit=args.limit, status="active")
    print("# Shared Agent Memory")
    print()
    print(format_records(records, include_content=True))
    return 0


def command_list(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    rows = conn.execute(
        """
        SELECT *, 0 AS rank
        FROM memories
        WHERE status = ?
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (args.status, args.limit),
    ).fetchall()
    print(format_records([row_to_dict(row) for row in rows], include_content=False))
    return 0


def command_status(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    rows = conn.execute(
        "SELECT status, COUNT(*) AS count FROM memories GROUP BY status ORDER BY status"
    ).fetchall()
    print(f"memory_db: {db_path_from_args(args.db)}")
    if not rows:
        print("memories: 0")
    for row in rows:
        print(f"{row['status']}: {row['count']}")
    pending = conn.execute(
        """
        SELECT id, title
        FROM memories
        WHERE status = 'pending'
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        (args.pending_limit,),
    ).fetchall()
    if pending:
        print("pending:")
        for row in pending:
            print(f"- {row['id']}: {row['title']}")
    return 0


def command_audit(args: argparse.Namespace) -> int:
    conn = connect(db_path_from_args(args.db))
    try:
        since = parse_since(args.since)
    except argparse.ArgumentTypeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rows = query_audit(
        conn,
        memory_id=args.memory_id,
        writer=args.writer,
        since=since,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    else:
        print(format_audit_rows(rows))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", help=f"memory database path, default {DEFAULT_DB}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init")
    init.set_defaults(func=command_init)

    import_claude = subparsers.add_parser("import-claude")
    import_claude.add_argument("--include-source-claude", action="store_true")
    import_claude.add_argument("--promote-on-import", action="store_true")
    import_claude.add_argument("--dry-run", action="store_true")
    import_claude.add_argument("--limit", type=int, default=20)
    import_claude.set_defaults(func=command_import_claude)

    for name, func in [("propose", command_propose), ("add", command_add)]:
        cmd = subparsers.add_parser(name)
        cmd.add_argument("--title", required=True)
        cmd.add_argument("--content")
        cmd.add_argument("--content-file")
        cmd.add_argument("--kind", default="learning")
        cmd.add_argument("--scope", default="workspace")
        cmd.add_argument("--source-path")
        cmd.add_argument("--source-ref")
        cmd.add_argument("--tags", default="")
        cmd.add_argument("--confidence", default="medium")
        cmd.add_argument("--writer", default="agent")
        cmd.add_argument("--trust", default="advisory")
        cmd.set_defaults(func=func)

    promote = subparsers.add_parser("promote")
    promote.add_argument("memory_id")
    promote.set_defaults(func=command_promote)

    reject = subparsers.add_parser("reject")
    reject.add_argument("memory_id")
    reject.set_defaults(func=command_reject)

    search = subparsers.add_parser("search")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=8)
    search.add_argument("--status", default="active")
    search.add_argument("--json", action="store_true")
    search.add_argument("--no-content", action="store_true")
    search.set_defaults(func=command_search)

    context = subparsers.add_parser("context")
    context.add_argument("--query")
    context.add_argument("--limit", type=int, default=6)
    context.set_defaults(func=command_context)

    list_cmd = subparsers.add_parser("list")
    list_cmd.add_argument("--status", default="pending")
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.set_defaults(func=command_list)

    status = subparsers.add_parser("status")
    status.add_argument("--pending-limit", type=int, default=10)
    status.set_defaults(func=command_status)

    audit_cmd = subparsers.add_parser("audit")
    audit_cmd.add_argument("--memory-id")
    audit_cmd.add_argument("--writer")
    audit_cmd.add_argument("--since")
    audit_cmd.add_argument("--limit", type=int, default=20)
    audit_cmd.add_argument("--json", action="store_true")
    audit_cmd.set_defaults(func=command_audit)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
