"""Long-lived Unix-socket server. Loads core/ once; serves hook RPCs in ~5ms."""

from __future__ import annotations
import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

# AF_UNIX sun_path is limited to 103 bytes on macOS / 107 on Linux.
_UNIX_SOCK_MAX = 103

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

_HOME = Path(os.environ.get("HOME", str(Path.home())))
_DEFAULT_STATE_DIR = _HOME / ".config" / "agent-shared" / "state"


_GRADUATION_INTERVAL_SECS = 6 * 3600  # 6 hours


async def _maybe_run_graduation(state_dir: Path) -> None:
    """Lazily evaluate graduation policies; runs at most once per 6 hours. Fail-soft."""
    try:
        from core.state_store import StateStore
        from core.graduation import evaluate_edit_anchor

        grad_state_path = state_dir / "graduation-state.json"
        store = StateStore(grad_state_path)
        state = store.read(
            default={
                "last_check": 0,
                "edit_anchor_mode": "auto_rescue",
                "stale_read_guard_mode": "warn",
            }
        )
        now = time.time()
        if now - state.get("last_check", 0) < _GRADUATION_INTERVAL_SECS:
            return  # too soon

        adoption_path = state_dir / "adoption.jsonl"
        if adoption_path.exists():
            raw = adoption_path.read_text().strip()
            records = [json.loads(line) for line in raw.splitlines() if line.strip()]
            decision = evaluate_edit_anchor(
                records,
                current_mode=state["edit_anchor_mode"],
                threshold_pct=30,
                min_sample=100,
                window_days=28,
                oversize_threshold=25,
            )
            if decision.new_mode != state["edit_anchor_mode"]:
                print(
                    f"[graduation] edit_anchor: {state['edit_anchor_mode']} -> "
                    f"{decision.new_mode} ({decision.reason})",
                    file=sys.stderr,
                )
                state["edit_anchor_mode"] = decision.new_mode

        state["last_check"] = now
        store.write(state)
    except Exception as exc:
        print(f"[graduation] error (ignored): {exc}", file=sys.stderr)


async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        line = await reader.readline()
        if not line:
            return
        request = json.loads(line.decode())
        response = await _dispatch(request)
        writer.write((json.dumps(response) + "\n").encode())
        await writer.drain()
    except Exception as exc:
        writer.write((json.dumps({"ok": False, "error": str(exc)}) + "\n").encode())
        await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def _dispatch(request: dict) -> dict:
    # Lazy graduation check: runs at most once per 6h, fail-soft
    state_dir_for_grad = Path(request.get("state_dir", str(_DEFAULT_STATE_DIR)))
    await _maybe_run_graduation(state_dir_for_grad)

    action = request.get("action")
    if action == "ping":
        return {"ok": True, "pong": True}
    if action == "resolve_upto":
        from core.upto_resolver import resolve, ResolvedSpan

        path = request["path"]
        pattern = request["pattern"]
        content = Path(path).read_text()
        result = resolve(content, pattern)
        if isinstance(result, ResolvedSpan):
            return {
                "ok": True,
                "span_text": result.text,
                "start_line": result.start_line,
                "end_line": result.end_line,
            }
        return {
            "ok": False,
            "kind": result.kind,
            "message": result.message,
            "candidates": result.candidates,
        }
    if action == "fuzzy_path":
        from core.path_resolver import find_candidates

        target = request["target"]
        root = Path(request["workspace_root"])
        candidates = find_candidates(target, root)
        return {
            "ok": True,
            "candidates": [
                {"path": str(c.path), "similarity": c.similarity} for c in candidates
            ],
        }
    if action == "check_stale":
        from core.stale_read import is_stale
        from core.state_store import StateStore

        store = StateStore(Path(request["state_dir"]) / "read-history.json")
        history = store.read(default={})
        path = Path(request["path"])
        stale = is_stale(
            path,
            history=history,
            allow_edit_without_prior_read=request.get("allow_no_prior", True),
        )
        return {"ok": True, "stale": stale}
    if action == "record_read":
        import time
        from core.state_store import StateStore

        path = Path(request["path"])
        if not path.exists():
            return {"ok": True, "skipped": "file_not_found"}
        try:
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            mtime = path.stat().st_mtime
        except OSError as exc:
            return {"ok": False, "error": str(exc)}
        store = StateStore(Path(request["state_dir"]) / "read-history.json")
        store.update(
            lambda d: {
                **d,
                str(path.resolve()): {
                    "mtime_at_read": mtime,
                    "sha256_at_read": digest,
                    "read_at": time.time(),
                },
            }
        )
        return {"ok": True}
    if action == "path_resolver_candidates":
        from core.path_resolver import find_candidates
        from core.allowed_root import resolve_root

        target = request["target"]
        root = resolve_root(Path(request.get("workspace_root", ".")))
        candidates = find_candidates(target, root, limit=3)
        return {
            "ok": True,
            "candidates": [
                {"path": str(c.path), "similarity": c.similarity} for c in candidates
            ],
        }
    if action == "record_adoption":
        from core.adoption_tracker import AdoptionRecord, log_edit

        state_dir = Path(
            request.get(
                "state_dir",
                str(
                    Path(os.environ.get("HOME", str(Path.home())))
                    / ".config"
                    / "agent-shared"
                    / "state"
                ),
            )
        )
        log_path = state_dir / "adoption.jsonl"
        record = AdoptionRecord(
            agent=request.get("agent", "unknown"),
            session=request.get("session", "unknown"),
            used_upto=bool(request.get("used_upto", False)),
            old_lines=int(request.get("old_lines", 0)),
            rescued=bool(request.get("rescued", False)),
            file_extension=request.get("file_extension", ""),
        )
        log_edit(log_path, record)
        return {"ok": True}
    return {"ok": False, "error": f"unknown action: {action}"}


async def main_async(socket_path: str) -> None:
    if os.path.exists(socket_path):
        os.unlink(socket_path)

    # AF_UNIX sun_path has an OS-level byte limit (~103 on macOS).  When the
    # requested path is too long (e.g. pytest tmp_path on macOS), create the
    # real socket at a short hash-derived path in /tmp and symlink the
    # requested path to it so callers can still connect via either path.
    actual_path = socket_path
    if len(socket_path.encode()) > _UNIX_SOCK_MAX:
        digest = hashlib.sha1(socket_path.encode()).hexdigest()[:16]
        actual_path = f"/tmp/anchfs-{digest}.sock"
        if os.path.exists(actual_path):
            os.unlink(actual_path)

    server = await asyncio.start_unix_server(handle, path=actual_path)

    if actual_path != socket_path:
        os.symlink(actual_path, socket_path)

    async with server:
        await server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--socket", required=True)
    args = parser.parse_args()
    asyncio.run(main_async(args.socket))
    return 0


if __name__ == "__main__":
    sys.exit(main())
