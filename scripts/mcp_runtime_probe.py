"""MCP runtime layer-3 probe (per ADR-0036 v0.8 extension).

doctor-verify through v0.7 confirmed that an MCP server entry existed
in the agent's native config file (~/.claude.json, ~/.cursor/mcp.json,
~/.codex/config.toml, <target>/.windsurf/mcp.json). It did not confirm
that the server *process* actually starts and speaks the MCP protocol.
This module closes that half of layer-3 for MCP.

The probe:
  1. Reads the MCP entry from the agent's native config.
  2. Resolves the configured `command` + `args` + `env`.
  3. Skips if the command path does not exist (the venv has not been
     bootstrapped on this machine; the probe is conservative and does
     NOT treat that as a verify failure -- it is a layer-2 gap, not a
     runtime one).
  4. Spawns the server with the configured env and a bounded total
     timeout (default 10s).
  5. Sends one JSON-RPC `initialize` request over stdin.
  6. Reads one JSON-RPC response from stdout; checks for the expected
     `result.serverInfo` shape.
  7. Terminates the process (SIGTERM, then SIGKILL fallback at 2s).

The probe returns a `ProbeResult` so cmd_verify can render the per-
server outcome and count failures into the overall exit code.

Design notes:

  * The probe does NOT verify tool catalogs or call any tools. It is
    purely a "the server can stand up and complete the MCP handshake"
    check. Anything beyond that should be a separate probe (a `tools/
    list` round-trip is a natural next step; deliberately deferred so
    this v0.8 probe stays bounded).
  * Per-server timeout is 10 seconds by default. Servers that take
    longer than 10s to initialize (cold venv builds, network-bound
    handshakes) get marked as TIMEOUT rather than FAIL so the user
    can tell "server is slow" apart from "server is broken."
  * The probe spawns the server with HOME redirected to the current
    HOME and never overrides cwd; the configured `cwd` in the MCP
    entry is honored if present (anchored-fs uses this to find its
    own .venv).
"""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class _ProbeRedirectRefused(urllib.error.HTTPError):
    """Subclass HTTPError so the probe can distinguish our own redirect
    rejection from server-emitted 3xx with structural type-checking,
    not a string-prefix match on server-controlled `reason` text.

    v0.9 round-15 adversarial HIGH fix: the round-12 carve-out checked
    `reason.startswith("redirect refused by probe")` to allow our
    rejection message through the credential-redaction path. But
    `reason` is server-controlled for ordinary 4xx/5xx responses, so a
    malicious or buggy endpoint could spoof the prefix to leak echoed
    credentials. Using a private subclass closes the spoof:
    isinstance(exc, _ProbeRedirectRefused) is a TRUSTED signal.
    """


class _RejectRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Block every HTTP redirect during MCP probing.

    v0.9 round-6 adversarial HIGH fix: the default urllib opener follows
    3xx redirects on POST and carries Authorization (along with any
    other env-substituted headers) to the redirect target.

    v0.9 round-8 adversarial HIGH fix: the rejection MUST NOT echo the
    Location URL into the exception reason. A redirect Location can
    itself contain credentials (canonical redirects that preserve a
    query-string API key, for example), and HTTPError.reason flows
    into ProbeResult.detail which cmd_verify prints. Use a generic
    message + record the new host (not the full URL) for debugging.

    Round-15 adversarial HIGH fix: raise the typed _ProbeRedirectRefused
    subclass so the probe can identify our own rejection structurally
    instead of by string prefix on server-controlled reason text.
    """

    def redirect_request(
        self, req, fp, code, msg, headers, newurl
    ):  # type: ignore[override]
        try:
            new_host = urllib.parse.urlsplit(newurl).hostname or "<unknown>"
        except (ValueError, AttributeError):
            new_host = "<unknown>"
        raise _ProbeRedirectRefused(
            req.full_url,
            code,
            f"redirect refused by probe (host={new_host!r}); "
            "auth headers would leak",
            headers,
            fp,
        )


_HTTP_OPENER = urllib.request.build_opener(_RejectRedirectHandler())


_LOOPBACK_HOSTS = frozenset(
    {"localhost", "127.0.0.1", "::1", "[::1]", "0.0.0.0"}
)


def _redact_url_for_logs(url: str, *, was_substituted: bool = False) -> str:
    """Return a URL with userinfo and query string stripped, suitable
    for inclusion in ProbeResult.detail without leaking secrets.

    Always strips userinfo + query string. When `was_substituted=True`
    (the URL was modified by env-var substitution before reaching this
    point), ALSO elides the path: round-8 regular review P2 finding
    proved a URL template like `http://host/${env:TOKEN}/mcp` would
    otherwise print the token via the preserved path segment.

    The redactor is TOTAL (never raises). parts.port raises ValueError
    for non-numeric ports (e.g., `https://example.com:bad/mcp`), and
    InvalidURL handlers call this redactor, so a raise here would
    escape probe_one_server.
    """
    try:
        parts = urllib.parse.urlsplit(url)
    except (ValueError, TypeError):
        return "<unparseable-url>"
    try:
        if was_substituted:
            # Round-8 regular review P2: substituted PATH leaks (`/${TOKEN}/`).
            # Round-16 regular review P2: substituted HOST also leaks
            # (`${TOKEN}.example.com`). Without component-level tracking
            # of which span was substituted, the only safe move is to
            # elide BOTH host and path when substitution happened.
            rebuilt = f"{parts.scheme}://<redacted-host>/<redacted-path>"
        else:
            host = parts.hostname or ""
            try:
                port = parts.port
            except ValueError:
                port = None  # non-numeric port; drop from rebuild
            if port is not None:
                host = f"{host}:{port}"
            rebuilt = f"{parts.scheme}://{host}{parts.path or ''}"
        if parts.query:
            rebuilt += "?<redacted-query>"
        return rebuilt
    except (ValueError, TypeError, AttributeError):
        return "<unparseable-url>"


def _is_loopback_host(parsed_url: urllib.parse.SplitResult) -> bool:
    """Round-7 adversarial HIGH fix: bearer tokens / substituted auth
    headers MUST NOT be transmitted in cleartext over remote HTTP.
    Loopback hosts (localhost, 127.0.0.1, ::1) get an exemption for
    local dev fixtures.
    """
    host = (parsed_url.hostname or "").lower()
    if host in _LOOPBACK_HOSTS:
        return True
    # IPv6 loopback can appear with or without brackets in netloc; the
    # hostname accessor strips brackets so [::1] -> "::1".
    return host == "::1"


ProbeStatus = Literal["ok", "fail", "timeout", "skipped"]


# v0.9 (ADR-0039): HTTP header substitution syntaxes across MCP clients.
#   ${env:VAR_NAME}    Cursor convention.
#   {{VAR_NAME}}       Generic gateway convention.
#   bearer_token_env_var: <VAR>  Codex convention (rendered as
#                              `Authorization: Bearer <env value>`).
# Variables follow uppercase + underscore identifier convention.
_DOLLAR_ENV_RE = re.compile(r"\$\{env:([A-Z_][A-Z0-9_]*)\}")
_DOUBLE_BRACE_RE = re.compile(r"\{\{([A-Z_][A-Z0-9_]*)\}\}")


@dataclass(frozen=True)
class ProbeResult:
    server_name: str
    config_path: Path
    status: ProbeStatus
    detail: str  # one-line human reason; empty for "ok"


# v0.8 Cursor review C3-cleanup: MCP entry loading lives in
# scripts/mcp_native_config.py so the verify pass and the runtime probe
# share one implementation. The local alias preserves call-site API.

from mcp_native_config import load_mcp_entry as _load_mcp_entry  # noqa: E402


def _resolve_command(entry: dict) -> tuple[str, list[str], dict[str, str], Path | None]:
    """Pull command + args + env + cwd out of an MCP config entry."""
    command = entry.get("command", "")
    args = [str(a) for a in (entry.get("args") or [])]
    env: dict[str, str] = {}
    for k, v in (entry.get("env") or {}).items():
        env[str(k)] = str(v)
    cwd_raw = entry.get("cwd")
    cwd = Path(cwd_raw) if cwd_raw else None
    return command, args, env, cwd


# v0.9 round-5 fix: the HTTP probe must match the response id back to
# the request id (jsonrpc 2.0 contract). Single shared constant so
# both _initialize_request and the response validator agree.
_INITIALIZE_REQUEST_ID = 1


def _initialize_request(probe_id: int = _INITIALIZE_REQUEST_ID) -> str:
    """Build a JSON-RPC 2.0 initialize request for an MCP server.

    protocolVersion follows the MCP spec stable date (2024-11-05). The
    clientInfo is identifiable as the playbook probe so server logs can
    attribute the spawn.
    """
    return (
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": probe_id,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "coding-agents-playbook-probe",
                        "version": "0.9.0",
                    },
                },
            }
        )
        + "\n"
    )


def _terminate(proc: subprocess.Popen, grace_sec: float = 2.0) -> None:
    """Politely terminate the server; SIGKILL after the grace window."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=grace_sec)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        if hasattr(signal, "SIGKILL"):
            proc.kill()
        else:
            proc.terminate()
    except (ProcessLookupError, OSError):
        return
    try:
        proc.wait(timeout=1.0)
    except subprocess.TimeoutExpired:
        pass


def probe_one_server(
    server_name: str,
    config_path: Path,
    *,
    timeout_sec: float = 10.0,
) -> ProbeResult:
    """Run one MCP initialize round-trip and classify the outcome.

    Returns ProbeResult; never raises. The probe is read-only with
    respect to the playbook tree (it does not modify anything beyond
    the spawned process state).
    """
    entry = _load_mcp_entry(config_path, server_name)
    if entry is None:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="skipped",
            detail=f"no entry found in {config_path}",
        )

    # v0.9 adversarial-round-2 MEDIUM-2 fix: HTTP entries' {{VAR}}
    # patterns can be valid env-var templates (the supported substitution
    # syntax), so the generic placeholder skip must NOT pre-empt them.
    # The HTTP probe runs FIRST and does its own substitution; missing
    # env vars are surfaced via skipped:env-var-unset:<VAR> with the
    # specific names. The `enabled=false` check still applies to both
    # transports.
    if entry.get("enabled") is False:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="skipped",
            detail="entry has enabled=false; opt in by removing the flag",
        )

    # v0.9 (ADR-0039): Streamable HTTP transport (2025-03-26 MCP spec).
    # SSE was deprecated June 2025; SSE-only entries are skipped with an
    # explicit reason. URL-only entries (no `command`) default to
    # Streamable HTTP. The HTTP probe sends a POST with InitializeRequest
    # and expects HTTP 200 + JSON body containing result.serverInfo.
    # v0.9 round-14 regular review P2 fix: a user-edited MCP config can
    # carry a non-string truthy `type` or `transport` (e.g., `"type": 1`).
    # The earlier `(... or ... or "").lower()` short-circuited on
    # falsy-only, so `1.lower()` raised AttributeError and aborted
    # cmd_verify for the whole run. Coerce via str() before .lower().
    transport_raw = entry.get("type") or entry.get("transport") or ""
    transport = (
        transport_raw.lower()
        if isinstance(transport_raw, str)
        else str(transport_raw).lower()
    )
    if transport == "sse":
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="skipped",
            detail=(
                "sse-only transport not supported (deprecated 2025-06); "
                "use streamable-http"
            ),
        )
    if transport in {"http", "streamable-http"} or (
        entry.get("url") and not entry.get("command")
    ):
        return _probe_http_server(
            server_name=server_name,
            config_path=config_path,
            entry=entry,
            timeout_sec=timeout_sec,
        )

    # v0.8 Codex round-6 fix: skip stdio entries with unfilled placeholder
    # values like {{REPLACE_WITH_YOUR_API_KEY}} anywhere in env, args,
    # or command. atlassian, slack, error-tracking ship as stock profile members
    # with these placeholders so doctor-verify on a fresh install doesn't
    # spawn npx servers that immediately fail or spend 10s timing out.
    # Stdio-only: HTTP path handles its own placeholders via env-var
    # substitution above (round-2 MEDIUM-2 fix). _has_placeholder is at
    # module scope (round-3 Cursor #4).
    if _has_placeholder(entry):
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="skipped",
            detail=(
                "entry contains unfilled placeholder ({{...}}); fill in "
                "credentials/values before probing"
            ),
        )

    # v0.8 Codex review fix: honor `startup_timeout_sec` from the entry
    # when it exceeds the probe's default. Docker-launched servers like
    # code-quality declare 180s; the probe default of 10s would mis-classify
    # them as timeout. We CAP the override at 300s so a misconfigured
    # entry can't hang doctor-verify for an unbounded window.
    declared_timeout = entry.get("startup_timeout_sec")
    if isinstance(declared_timeout, (int, float)) and declared_timeout > 0:
        timeout_sec = min(max(timeout_sec, float(declared_timeout)), 300.0)

    command, args, env, cwd = _resolve_command(entry)
    if not command:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail="entry has no command",
        )

    # v0.8 (Codex review fix): MCP configs commonly use PATH-resolved
    # commands like `npx`, `docker`, `uvx`, `python3`. Path(command).is_file()
    # is False for those even when they're perfectly callable. Try
    # shutil.which first; only fall back to skipped when the command is
    # genuinely absent both as a file path and on PATH.
    #
    # Classification rule:
    #   * Absolute or relative path to a file that exists       -> probe.
    #   * Bare command resolvable via shutil.which               -> probe.
    #   * Bare command NOT on PATH AND configured via env that
    #     resolves to a missing absolute (e.g. anchored-fs venv) -> fail.
    #     A managed playbook MCP whose binary vanished is a real
    #     verification failure, not a skip.
    #   * Bare command NOT on PATH that is genuinely optional /
    #     user-bring-your-own (docker on a CI host without docker)
    #     -> skipped. We can't distinguish "user opted out" from
    #     "broken" without an explicit annotation; favour skipped to
    #     avoid false positives, but emit a clearly-distinct detail.
    # v0.8 Codex round-4 fix: relative commands like `.venv/bin/python`
    # plus an explicit cwd resolve against the cwd, not the verifier's
    # pwd. Path(command).is_file() against the verifier's cwd would
    # mis-classify those as missing. Probe order:
    #   1. Absolute command: check Path(command).
    #   2. Has cwd + contains '/': check (cwd / command).
    #   3. shutil.which() (bare PATH command).
    #   4. Neither: managed-path-missing fail OR bare-PATH-missing skip.
    command_path = Path(command)
    found_path: str | None = None
    if command_path.is_absolute():
        if command_path.is_file():
            found_path = str(command_path)
    elif cwd is not None and ("/" in command or "\\" in command):
        candidate = (cwd / command).resolve()
        if candidate.is_file():
            found_path = str(candidate)
    if found_path is None:
        # v0.8 Codex round-9 fix: pass entry.env.PATH (if set) into
        # shutil.which so an MCP entry that ships a curated PATH (for
        # example, prepending its venv) resolves bare commands the way
        # the real spawn would. Without this, the verifier's own PATH
        # is used and entries that depend on a curated env get
        # misclassified as missing.
        merged_path = env.get("PATH")
        if merged_path:
            resolved = shutil.which(command, path=merged_path)
            if resolved is None:
                # Fall back to the default PATH so a partial
                # entry.env that doesn't set PATH still works.
                resolved = shutil.which(command)
        else:
            resolved = shutil.which(command)
        if resolved is None:
            # Treat managed playbook MCP venvs (paths with `/` that the
            # playbook recorded itself) as fail; bare PATH commands that
            # nothing on this machine provides as skipped.
            if "/" in command or "\\" in command:
                return ProbeResult(
                    server_name=server_name,
                    config_path=config_path,
                    status="fail",
                    detail=(
                        f"command not found at {command}; "
                        "managed MCP runtime missing -- bootstrap the bundle "
                        "or re-run `make install`"
                    ),
                )
            return ProbeResult(
                server_name=server_name,
                config_path=config_path,
                status="skipped",
                detail=(
                    f"PATH command {command!r} not present on this host; "
                    "install it or remove the MCP entry"
                ),
            )
        found_path = resolved
    # Substitute the resolved absolute path so subprocess.Popen always
    # sees a concrete executable; the detail message gets useful info.
    command = found_path

    full_env = dict(os.environ)
    full_env.update(env)
    try:
        proc = subprocess.Popen(
            [command, *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=full_env,
            cwd=str(cwd) if cwd is not None else None,
            text=True,
            bufsize=1,
        )
    except (OSError, ValueError) as exc:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"spawn failed: {exc}",
        )

    try:
        proc.stdin.write(_initialize_request())  # type: ignore[union-attr]
        proc.stdin.flush()  # type: ignore[union-attr]
    except (BrokenPipeError, OSError) as exc:
        _terminate(proc)
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"server closed stdin: {exc}",
        )

    # v0.8 Codex review fix (P1): read ONE line of stdout with a bounded
    # timeout, validate it, then terminate. The previous implementation
    # used communicate() which waits for EOF / process exit -- but a
    # healthy stdio MCP server stays alive after initialize (the whole
    # point: it's ready to serve tool calls). communicate() therefore
    # mis-classified every real server as timeout. Now we use a reader
    # thread with a Queue + Event so the main thread can bail at
    # timeout_sec regardless of whether the server exits.
    import queue as _queue
    import threading

    line_queue: "_queue.Queue[str | None]" = _queue.Queue(maxsize=1)
    stop_flag = threading.Event()

    def _reader() -> None:
        try:
            line = proc.stdout.readline()  # type: ignore[union-attr]
        except (OSError, ValueError):
            line = ""
        if not stop_flag.is_set():
            line_queue.put(line)

    reader = threading.Thread(target=_reader, daemon=True)
    reader.start()

    # v0.8 Codex round-9 fix: bound the stderr read. A naive
    # proc.stderr.read() blocks until EOF even after terminate(); a
    # malfunctioning child that kept stderr open across termination
    # would hang doctor-verify indefinitely. We use communicate() with
    # a short timeout to bound the wait + fall back to whatever buffer
    # was already populated.
    def _bounded_stderr_tail(proc_handle: subprocess.Popen) -> str:
        try:
            _, stderr_bytes = proc_handle.communicate(timeout=1.0)
        except (subprocess.TimeoutExpired, ValueError):
            # Process still alive after _terminate; kill it harder and
            # try one more bounded communicate.
            try:
                if hasattr(signal, "SIGKILL"):
                    proc_handle.kill()
            except (OSError, ProcessLookupError):
                pass
            try:
                _, stderr_bytes = proc_handle.communicate(timeout=0.5)
            except (subprocess.TimeoutExpired, ValueError, OSError):
                return ""
        except OSError:
            return ""
        if stderr_bytes is None:
            return ""
        if isinstance(stderr_bytes, bytes):
            stderr_bytes = stderr_bytes.decode("utf-8", errors="replace")
        return stderr_bytes[-200:]

    try:
        first_line_raw = line_queue.get(timeout=timeout_sec)
    except _queue.Empty:
        stop_flag.set()
        # Capture whatever the server has emitted to stderr so a
        # malfunctioning server gives the user actionable diagnostics.
        _terminate(proc)
        stderr_tail = _bounded_stderr_tail(proc)
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="timeout",
            detail=(
                f"no initialize response within {timeout_sec}s; "
                f"stderr tail: {stderr_tail!r}"
            ),
        )

    # Terminate immediately once we have the response. A healthy stdio
    # MCP server will be sitting in its main loop waiting for the next
    # request; the probe is a stand-up check, not a tool exerciser.
    _terminate(proc)

    first_line = (first_line_raw or "").strip()
    if not first_line:
        stderr_tail = _bounded_stderr_tail(proc)
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                "no stdout produced; "
                f"stderr tail: {stderr_tail!r}"
            ),
        )

    try:
        msg = json.loads(first_line)
    except json.JSONDecodeError as exc:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"non-JSON response: {exc}: {first_line[:100]!r}",
        )

    if msg.get("jsonrpc") != "2.0":
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"missing jsonrpc=2.0 envelope: {first_line[:100]!r}",
        )
    if "error" in msg:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"server returned error: {msg['error']}",
        )

    # v0.8 Codex review fix (P2): require the MCP initialize result
    # shape -- specifically serverInfo with at least a name. The
    # previous implementation accepted {} as ok, so a wrapper that
    # answered "jsonrpc": "2.0", "result": {}" passed the probe
    # without actually completing the initialize contract.
    result = msg.get("result")
    if not isinstance(result, dict):
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                "missing or non-object initialize result; "
                "MCP servers must return result.serverInfo"
            ),
        )
    server_info = result.get("serverInfo")
    if not isinstance(server_info, dict) or not server_info.get("name"):
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                "initialize result missing serverInfo.name; "
                "not a conforming MCP server"
            ),
        )
    return ProbeResult(
        server_name=server_name,
        config_path=config_path,
        status="ok",
        detail=f"serverInfo.name={server_info['name']!r}",
    )


_HTTP_MAX_READ_BYTES = 1_048_576  # 1 MiB cap; the probe only needs the
# initialize response, which is well under 100KB even with verbose
# capabilities. Cap exists so a misbehaving server can't make us read
# unbounded streams.


def _read_http_response_bounded(
    resp, content_type: str, deadline: float
) -> tuple[str, bool]:
    """Read a Streamable HTTP MCP response with a wall-clock deadline
    and byte cap. Returns (body_text, hit_deadline).

    v0.9 round-3 + round-4-r2 fix: SSE responses can stay open after
    the first event; resp.read() would block until the server closes
    the stream. Round-3 stopped at first `\\n\\n`, but that mistakenly
    stops on a comment/heartbeat event (which has no `data:`) or
    misses CRLF terminators. Round-4-r2 (regular review P2) tightens
    this: keep reading until we see a complete event that ACTUALLY
    contains a `data:` line, supporting both LF and CRLF terminators
    and skipping comment lines (per W3C SSE spec).

    For application/json responses, returns when a parseable JSON
    object is buffered or the body ends or the deadline fires.
    """
    import time as _time

    is_sse = "text/event-stream" in content_type
    buf = bytearray()
    hit_deadline = False
    chunk_size = 4096

    while True:
        remaining = deadline - _time.monotonic()
        if remaining <= 0:
            hit_deadline = True
            break
        if len(buf) >= _HTTP_MAX_READ_BYTES:
            break
        try:
            chunk = (
                resp.read1(chunk_size)
                if hasattr(resp, "read1")
                else resp.read(chunk_size)
            )
        except (OSError, TimeoutError):
            hit_deadline = True
            break
        except http.client.HTTPException:
            # v0.9 round-16 adversarial MEDIUM fix: http.client can raise
            # HTTPException subclasses (e.g., IncompleteRead on truncated
            # bodies, BadStatusLine on broken chunked encoding) from
            # resp.read*(). probe_one_server promises never to raise, so
            # catching here keeps verify bounded. Preserve whatever
            # partial buffer accumulated; treat as a normal end-of-read
            # so the caller's classifier reports a fail instead of
            # bubbling out.
            break
        if not chunk:
            break
        buf.extend(chunk)
        if is_sse:
            # SSE: stop only when a complete event has arrived whose
            # data: payload parses as the matching initialize response
            # (jsonrpc=="2.0" + id == request id). Pings, heartbeats,
            # and unrelated events fail this check, so the reader
            # keeps going until the actual response arrives or the
            # deadline fires.
            if _sse_buffer_has_matching_initialize_response(bytes(buf)):
                break
        else:
            # application/json: stop when the buffer parses as a
            # complete JSON object.
            try:
                json.loads(bytes(buf).decode("utf-8", errors="replace"))
                break
            except json.JSONDecodeError:
                pass
    return bytes(buf).decode("utf-8", errors="replace"), hit_deadline


def _sse_buffer_has_matching_initialize_response(buf: bytes) -> bool:
    """Round-5 fix: scan the buffered SSE stream for a complete event
    whose data: payload parses as the matching JSON-RPC initialize
    response. Earlier rounds stopped at the first event with any
    `data:` line, which a server could spoil with a heartbeat ping
    (`event: ping\\ndata: {}`).
    """
    text = buf.decode("utf-8", errors="replace").replace("\r\n", "\n")
    events = text.split("\n\n")
    if len(events) < 2:
        # No complete event terminator yet.
        return False
    for event in events[:-1]:
        data_lines: list[str] = []
        for line in event.split("\n"):
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
        if not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            continue
        if (
            isinstance(payload, dict)
            and payload.get("jsonrpc") == "2.0"
            and payload.get("id") == _INITIALIZE_REQUEST_ID
        ):
            return True
    return False


def _iter_streamable_http_events(body: str, content_type: str) -> list[str]:
    """Return every event's data payload as a list of JSON-candidate
    strings, in arrival order.

    For text/event-stream responses, each event contributes one entry
    (the concatenation of its data: field lines). Events without
    data: lines (comment-only events, metadata-only pings) are
    omitted. CRLF terminators are normalized.

    For application/json responses, returns the body as the single
    candidate.

    Round-5 fix: earlier rounds returned only the FIRST candidate.
    The probe now iterates candidates so it can skip pings or other
    non-matching events and keep looking for the real initialize
    response.
    """
    if not body.strip():
        return []
    if "text/event-stream" in content_type:
        normalized = body.replace("\r\n", "\n")
        out: list[str] = []
        for event in normalized.split("\n\n"):
            data_lines: list[str] = []
            for line in event.split("\n"):
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
            if data_lines:
                out.append("\n".join(data_lines))
        return out
    return [body]


# v0.9 round-3 (Cursor thermo #4): _has_placeholder lifted to module
# scope so it can be reused by the stdio path AND covered by direct
# unit tests. The nested-helper version inside probe_one_server made
# the function harder to scan.
def _has_placeholder(value: object) -> bool:
    if isinstance(value, str):
        return "{{" in value and "}}" in value
    if isinstance(value, dict):
        return any(_has_placeholder(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_placeholder(v) for v in value)
    return False


def _substitute_env_in_value(value: str) -> tuple[str, list[str]]:
    """Substitute ${env:VAR} and {{VAR}} patterns from os.environ.

    Returns (substituted_string, list_of_missing_var_names). Variables
    that don't exist in os.environ are recorded; the function never
    reads from anywhere other than os.environ (no secret-store probing).
    """
    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        var = match.group(1)
        val = os.environ.get(var)
        if val is None:
            missing.append(var)
            return match.group(0)
        return val

    result = _DOLLAR_ENV_RE.sub(replace, value)
    result = _DOUBLE_BRACE_RE.sub(replace, result)
    return result, missing


def _probe_http_server(
    server_name: str,
    config_path: Path,
    entry: dict,
    timeout_sec: float,
) -> ProbeResult:
    """Probe a Streamable HTTP MCP server (2025-03-26 MCP spec).

    Sends a POST with InitializeRequest to the URL, expects HTTP 200 + a
    JSON body containing `result.serverInfo`. The probe NEVER reads from
    secret stores or files to satisfy a header substitution; any unset
    referenced env var is reported as a skip with explicit reason.

    Header substitution syntaxes:
      ${env:VAR}      Cursor convention (in `headers` field).
      {{VAR}}         Generic gateway convention (in `headers` field).
      bearer_token_env_var: <VAR>  Codex convention; resolves to
                                   `Authorization: Bearer <env value>`.
    """
    raw_url = entry.get("url")
    if not isinstance(raw_url, str) or not raw_url:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail="HTTP entry has no url field",
        )
    # v0.9 round-7-r2 regular review P2 fix: substitute env vars in
    # raw_url BEFORE validating shape. A native MCP config can supply
    # the endpoint via the template (e.g., url: "${env:MCP_URL}/mcp"),
    # in which case urlsplit on the raw template would see scheme="".
    # The substitution can still fail (env-var-unset); we surface that
    # via the same skip path as headers below.

    # v0.9 adversarial-round-2 fix: URLs can also carry ${env:VAR} or
    # {{VAR}} templates. The earlier placeholder-guard pre-emption made
    # these unreachable; substituting here gives unfilled URL
    # placeholders the same env-var-unset skip path as headers.
    missing_env: list[str] = []
    url, url_missing = _substitute_env_in_value(raw_url)
    if url_missing:
        missing_env.extend(url_missing)

    # v0.9 round-7-r2 (regular review P2 fix): validate the SUBSTITUTED
    # URL, not the raw template. A url like "${env:MCP_URL}/mcp" gets
    # the env value spliced in; only then can urlsplit see a real
    # scheme + host. (Round-6 adversarial fix kept Request construction
    # exception-safe; round-7-r2 moves the explicit scheme/host check
    # to AFTER substitution to match advertised semantics.)
    # If url_missing is non-empty we'll skip below with env-var-unset;
    # otherwise the substituted URL is what reaches urlopen.
    if not url_missing:
        try:
            parsed_url = urllib.parse.urlsplit(url)
        except ValueError as exc:
            _ = exc
            return ProbeResult(
                server_name=server_name,
                config_path=config_path,
                status="fail",
                detail=(
                    f"malformed url {_redact_url_for_logs(url, was_substituted=True)!r}: "
                    f"{type(exc).__name__}"
                ),
            )
        if parsed_url.scheme not in ("http", "https"):
            # v0.9 round-17 regular review P2 (security): a URL template
            # like `${env:TOKEN}://host/mcp` substitutes the env value
            # INTO the scheme. If url != raw_url (substitution happened)
            # and the scheme isn't http(s), don't echo the substituted
            # scheme verbatim; the env value could be the secret.
            if url != raw_url:
                scheme_for_log = "<redacted; URL used env-var substitution>"
            else:
                scheme_for_log = repr(parsed_url.scheme)
            return ProbeResult(
                server_name=server_name,
                config_path=config_path,
                status="fail",
                detail=(
                    f"unsupported url scheme {scheme_for_log}; "
                    "MCP HTTP transport requires http or https"
                ),
            )
        if not parsed_url.netloc:
            return ProbeResult(
                server_name=server_name,
                config_path=config_path,
                status="fail",
                detail=(
                    f"url {_redact_url_for_logs(url, was_substituted=True)!r} is missing a host"
                ),
            )

    raw_headers = entry.get("headers") or {}
    headers: dict[str, str] = {}
    if isinstance(raw_headers, dict):
        for key, value in raw_headers.items():
            if not isinstance(value, str):
                continue
            substituted, missing = _substitute_env_in_value(value)
            if missing:
                missing_env.extend(missing)
            else:
                headers[str(key)] = substituted

    bearer_var = entry.get("bearer_token_env_var")
    if isinstance(bearer_var, str) and bearer_var:
        token = os.environ.get(bearer_var)
        if token is None:
            missing_env.append(bearer_var)
        else:
            headers["Authorization"] = f"Bearer {token}"

    if missing_env:
        unique_missing = sorted(set(missing_env))
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="skipped",
            detail=(
                "env-var-unset:"
                + ",".join(unique_missing)
                + " (set the env var before probing; the probe never reads "
                "user secret stores)"
            ),
        )

    # v0.9 round-7 adversarial HIGH fix: refuse to send substituted
    # auth headers (Authorization, anything from bearer_token_env_var,
    # any header that came from an env-var substitution) over plain
    # HTTP to a non-loopback host. Cleartext transit of bearer tokens
    # is a credential-exposure path.
    #
    # v0.9 round-8 adversarial HIGH fix: the gate ALSO has to catch
    # URL-carried credentials. A config like
    # url="http://mcp.example/?api_key=${env:TOKEN}" has empty headers
    # AND no bearer_token_env_var, but the substituted query string
    # carries the token. Detect URL-carried secrets via:
    #   - userinfo (user:pass@host) shape
    #   - non-empty query string (query params commonly carry tokens;
    #     refusing all query+http+non-loopback is the conservative cut)
    #   - the URL itself was modified by env substitution
    # Loopback exemption preserves local-dev fixtures.
    try:
        parsed_substituted = urllib.parse.urlsplit(url)
    except ValueError as exc:
        _ = exc
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                f"malformed url after substitution: "
                f"{type(exc).__name__}"
            ),
        )
    url_was_substituted = url != raw_url
    url_carries_credentials = bool(
        parsed_substituted.username
        or parsed_substituted.password
        or parsed_substituted.query
        or url_was_substituted
    )
    # v0.9 round-16 + round-17 fix: distinguish auth-bearing user
    # headers from static non-credential headers. The fixed-name set in
    # round-16 was too narrow -- vendor-prefixed headers like
    # X-Tavily-Api-Key, X-Client-Secret, Private-Token, X-GitHub-Token
    # weren't in the set, so the cleartext gate let those credentials
    # ride over plain HTTP (round-17 adversarial HIGH).
    #
    # Round-17 heuristic: a header is treated as auth-bearing when
    # its lowercased name CONTAINS any of {auth, token, key, secret,
    # cookie, credential, password} OR its value contains an env
    # substitution pattern. A short safelist exempts known harmless
    # headers (X-Client, X-Request-Id) that have "key"-like substrings
    # but aren't credentials.
    raw_user_headers = entry.get("headers") or {}
    _AUTH_KEYWORDS = (
        "auth",
        "token",
        "key",
        "secret",
        "cookie",
        "credential",
        "password",
    )
    _NON_AUTH_SAFELIST = frozenset({
        # Common diagnostic / static headers that may contain a
        # keyword by coincidence ("keep-alive" has "keep", etc.) but
        # carry no credential. Add to this list as real-world configs
        # surface false positives.
        "x-client",
        "x-client-id",
        "x-request-id",
        "x-correlation-id",
        "x-trace-id",
        "user-agent",
        "keep-alive",
    })
    user_has_auth_payload_headers = False
    if isinstance(raw_user_headers, dict):
        for hkey, hval in raw_user_headers.items():
            kname = str(hkey).lower()
            sval = str(hval) if hval is not None else ""
            # Env-substituted value -> always sensitive.
            if "${env:" in sval or "{{" in sval:
                user_has_auth_payload_headers = True
                break
            if kname in _NON_AUTH_SAFELIST:
                continue
            if any(kw in kname for kw in _AUTH_KEYWORDS):
                user_has_auth_payload_headers = True
                break
    has_auth_payload = (
        user_has_auth_payload_headers
        or bool(bearer_var)
        or url_carries_credentials
    )
    response_is_sensitive = (
        url_was_substituted
        or user_has_auth_payload_headers
        or bool(bearer_var)
        or url_carries_credentials
    )

    def _redact_response_snippet(snippet: object) -> str:
        if response_is_sensitive:
            return "<redacted; URL or headers used env-var substitution>"
        return repr(snippet)[:120]

    if (
        parsed_substituted.scheme == "http"
        and has_auth_payload
        and not _is_loopback_host(parsed_substituted)
    ):
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                f"refusing to send credentials in cleartext to "
                f"{_redact_url_for_logs(url, was_substituted=True)!r}; use https or a "
                f"loopback host"
            ),
        )

    headers.setdefault("Accept", "application/json, text/event-stream")
    headers.setdefault("Content-Type", "application/json")

    body = _initialize_request().encode("utf-8")

    try:
        req = urllib.request.Request(
            url,
            data=body,
            headers=headers,
            method="POST",
        )
    except ValueError as exc:
        # Round-7 adversarial HIGH: drop exc message (may include
        # substituted secret); show type only.
        _ = exc
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                f"could not construct HTTP request for "
                f"{_redact_url_for_logs(url, was_substituted=True)!r}: {type(exc).__name__}"
            ),
        )

    # v0.9 round-3 adversarial HIGH fix: bound the HTTP read with a
    # wall-clock deadline AND a max byte cap. urlopen's `timeout` only
    # bounds the socket idle interval, so a streaming SSE server that
    # keeps the connection open after the first event (or sends
    # heartbeats under the socket timeout) would hang the probe
    # indefinitely. _read_http_response_bounded returns as soon as the
    # body is "enough to classify" (first SSE event for event-stream,
    # full JSON object for application/json) or the deadline fires.
    #
    # v0.9 round-6 adversarial HIGH fix: route through _HTTP_OPENER
    # (no-redirect) so substituted auth headers cannot leak to a
    # redirect target.
    import time as _time

    deadline = _time.monotonic() + max(timeout_sec, 1.0)
    try:
        resp = _HTTP_OPENER.open(req, timeout=timeout_sec)
    except urllib.error.HTTPError as exc:
        # v0.9 round-9-r2 regular review P1 security fix: gateway 4xx/5xx
        # `reason` can echo back the substituted URL or the invalid
        # token. When the request used substituted credentials, redact
        # the reason; otherwise show it for debuggability.
        #
        # Round-15 adversarial HIGH fix: use isinstance(_ProbeRedirectRefused)
        # to identify our own redirect rejection structurally, not via
        # a string prefix on `reason`.
        #
        # Round-16 adversarial HIGH fix: even our typed redirect
        # exception embeds the server-controlled Location HOST in its
        # reason. A probed endpoint with auth could return a Location
        # whose host echoes the secret (e.g., subdomain). When
        # response_is_sensitive, drop the host detail and emit a
        # generic "redirect refused" message.
        #
        # Round-12 adversarial MEDIUM fix: use the SAME response_is_sensitive
        # predicate we use for response bodies, computed BEFORE the
        # Accept/Content-Type defaults were added.
        reason_str = str(exc.reason) if exc.reason is not None else ""
        if isinstance(exc, _ProbeRedirectRefused):
            if response_is_sensitive:
                # Drop server-controlled Location host; emit a fixed
                # generic message so the user still sees that a
                # redirect was refused.
                reason_for_log = (
                    "redirect refused by probe (host redacted; "
                    "URL or headers used env-var substitution)"
                )
            else:
                reason_for_log = reason_str
        elif response_is_sensitive:
            reason_for_log = "<redacted; URL or headers used env-var substitution>"
        else:
            reason_for_log = repr(reason_str)[:120]
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"HTTP {exc.code}: {reason_for_log}",
        )
    except (urllib.error.URLError, TimeoutError) as exc:
        # Round-7 adversarial HIGH: URLError can include the URL in its
        # __str__. Show type + reason only.
        #
        # Round-18 adversarial HIGH fix: when response_is_sensitive,
        # the `reason` field ITSELF can carry substituted secrets. TLS,
        # DNS, proxy, and custom-opener errors frequently include the
        # offending host or URL ("TLS failed for host <substituted>"),
        # and that lands in cmd_verify logs. Apply the same redaction
        # rule as HTTPError reason + response body.
        reason = getattr(exc, "reason", type(exc).__name__)
        if response_is_sensitive:
            reason_for_log = (
                "<redacted; URL or headers used env-var substitution>"
            )
        else:
            reason_for_log = repr(reason)[:120]
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                f"connection failed to "
                f"{_redact_url_for_logs(url, was_substituted=True)!r}: "
                f"{reason_for_log}"
            ),
        )
    except http.client.InvalidURL as exc:
        # v0.9 round-6-r2 regular review P2 fix: urlopen can raise
        # http.client.InvalidURL (e.g., space inside URL after env
        # substitution).
        # Round-7 adversarial HIGH: the InvalidURL exception's __str__
        # INCLUDES the raw URL, which carries the env-substituted
        # secret. We DROP the exception message and surface only the
        # exception type so cmd_verify's log output stays safe. The
        # redacted URL is the only URL-shaped string that reaches the
        # detail.
        _ = exc  # exc message intentionally not interpolated (secret-leak)
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                f"invalid url {_redact_url_for_logs(url, was_substituted=True)!r}: "
                "InvalidURL (probably contains forbidden characters; "
                "e.g., a space)"
            ),
        )
    except (http.client.HTTPException, ValueError) as exc:
        # Round-6-r2: belt-and-braces guard for any other urllib /
        # http.client surface that can raise on malformed input.
        # Round-7: don't interpolate exc (may contain the substituted
        # URL); show the exception type only.
        _ = exc
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=(
                f"HTTP probe error for "
                f"{_redact_url_for_logs(url, was_substituted=True)!r}: {type(exc).__name__}"
            ),
        )
    except OSError as exc:
        # OSError detail (errno-shaped) is safe to include verbatim;
        # it never carries URL-derived strings.
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"HTTP probe error: {exc}",
        )

    try:
        status_code = resp.status
        session_id = resp.headers.get("Mcp-Session-Id")
        content_type = (resp.headers.get("Content-Type") or "").lower()
        response_body, hit_deadline = _read_http_response_bounded(
            resp, content_type, deadline
        )
    finally:
        try:
            resp.close()
        except OSError:
            pass

    if hit_deadline and not response_body:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="timeout",
            detail=(
                f"HTTP read exceeded {timeout_sec}s deadline before any "
                f"response body was received"
            ),
        )

    if status_code != 200:
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="fail",
            detail=f"HTTP status {status_code}",
        )

    # v0.9 round-5 fix: walk every SSE event and pick the one that
    # validates as the JSON-RPC initialize response. Earlier rounds
    # stopped at the first event with any `data:` line, which a server
    # could spoil with a ping like `event: ping\ndata: {}`. The
    # validator below mirrors stdio: jsonrpc == "2.0", id matches the
    # request id, error absent, result.serverInfo.name present. The
    # first event that satisfies all four is accepted; others are
    # treated as keepalives and ignored.
    # response_is_sensitive + _redact_response_snippet are defined above
    # (round-12 fix moved them BEFORE urlopen so the HTTPError handler
    # can reuse the predicate).
    candidate_events = _iter_streamable_http_events(response_body, content_type)
    last_failure_detail = (
        f"no events parsed from {content_type or 'response'} body: "
        f"{_redact_response_snippet(response_body)}"
    )
    for parsed_body in candidate_events:
        try:
            msg = json.loads(parsed_body)
        except json.JSONDecodeError:
            last_failure_detail = (
                f"non-JSON response: {_redact_response_snippet(parsed_body)}"
            )
            continue
        # v0.9 round-6-r2 regular review P2 fix: a Streamable HTTP
        # proxy can return valid JSON that is NOT an object (e.g., a
        # bare list `[]`). msg.get() would crash with AttributeError
        # and abort the whole verify run. Treat non-object as a
        # failed probe for this entry and keep going.
        if not isinstance(msg, dict):
            last_failure_detail = (
                f"non-object JSON response: {type(msg).__name__} "
                f"payload, expected JSON-RPC object"
            )
            continue
        if msg.get("jsonrpc") != "2.0":
            last_failure_detail = (
                f"missing jsonrpc=2.0 envelope: "
                f"{_redact_response_snippet(parsed_body)}"
            )
            continue
        if msg.get("id") != _INITIALIZE_REQUEST_ID:
            # Probably a ping/notification; keep looking for the
            # response that matches OUR request id.
            #
            # Round-12 adversarial HIGH fix: when the request used
            # substituted credentials, the gateway can echo a token in
            # the JSON-RPC id field. Redact when sensitive; otherwise
            # show the id value for debuggability.
            if response_is_sensitive:
                last_failure_detail = (
                    "response id <redacted; URL or headers used env-var "
                    f"substitution> does not match request id "
                    f"{_INITIALIZE_REQUEST_ID!r}"
                )
            else:
                last_failure_detail = (
                    f"response id {msg.get('id')!r} does not match request id "
                    f"{_INITIALIZE_REQUEST_ID!r}"
                )
            continue
        if "error" in msg:
            return ProbeResult(
                server_name=server_name,
                config_path=config_path,
                status="fail",
                detail=(
                    f"server returned error: "
                    f"{_redact_response_snippet(msg['error'])}"
                ),
            )
        result = msg.get("result")
        if not isinstance(result, dict):
            last_failure_detail = (
                "missing or non-object initialize result; "
                "MCP servers must return result.serverInfo"
            )
            continue
        server_info = result.get("serverInfo")
        if not isinstance(server_info, dict) or not server_info.get("name"):
            last_failure_detail = (
                "initialize result missing serverInfo.name; "
                "not a conforming MCP server"
            )
            continue
        # v0.9 round-10 adversarial HIGH security fix: the success path
        # ALSO has to honor response_is_sensitive. A gateway / MCP server
        # can echo a substituted token in serverInfo.name; Mcp-Session-Id
        # may be a resumable session token. Earlier rounds only redacted
        # response-derived text on the failure path. For sensitive
        # requests, emit a sanitized status that proves the handshake
        # succeeded without printing server-controlled strings.
        if response_is_sensitive:
            return ProbeResult(
                server_name=server_name,
                config_path=config_path,
                status="ok",
                detail=(
                    "serverInfo.name=<redacted; URL or headers used env-var "
                    "substitution>"
                ),
            )
        suffix = f" session={session_id}" if session_id else ""
        return ProbeResult(
            server_name=server_name,
            config_path=config_path,
            status="ok",
            detail=f"serverInfo.name={server_info['name']!r}{suffix}",
        )

    return ProbeResult(
        server_name=server_name,
        config_path=config_path,
        status="fail",
        detail=last_failure_detail,
    )


def probe_all_servers(
    server_entries: list[tuple[str, Path]],
    *,
    timeout_sec: float = 10.0,
) -> list[ProbeResult]:
    """Run the probe against every (server_name, config_path) entry.

    `server_entries` is built by cmd_verify by walking the lockfile's
    managed_keys.mcp_servers per adapter and pairing each name with the
    config path that adapter writes to. Probing per-(name, config) pair
    rather than per-name means a server registered in three adapters
    gets three round-trips. That is intentional: the same server can be
    configured differently per adapter (different env, different cwd),
    and a regression in one adapter's config should not be masked by a
    healthy probe against another.
    """
    return [
        probe_one_server(name, path, timeout_sec=timeout_sec)
        for name, path in server_entries
    ]


def main() -> int:
    """Command-line entry for ad-hoc probing.

    Usage: python3 scripts/mcp_runtime_probe.py <server_name> <config_path>
    """
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    result = probe_one_server(sys.argv[1], Path(sys.argv[2]))
    print(f"[{result.status}] {result.server_name} -> {result.detail}")
    return 0 if result.status in {"ok", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
