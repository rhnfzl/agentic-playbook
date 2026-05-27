"""1-day spike: prove we can proxy @modelcontextprotocol/server-filesystem via stdio JSON-RPC."""

import json
import subprocess
import sys
import os


def send_rpc(proc, method, params, request_id):
    request = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
    line = json.dumps(request) + "\n"
    proc.stdin.write(line)
    proc.stdin.flush()
    response_line = proc.stdout.readline()
    return json.loads(response_line)


def main():
    home = os.path.expanduser("~")
    proc = subprocess.Popen(
        ["npx", "-y", "@modelcontextprotocol/server-filesystem", home],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )

    init_response = send_rpc(
        proc,
        "initialize",
        {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "spike", "version": "0.0.1"},
        },
        1,
    )
    print("INIT:", json.dumps(init_response, indent=2))

    assert proc.stdin is not None, "subprocess.PIPE produced a stdin handle"
    proc.stdin.write(
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"
    )
    proc.stdin.flush()

    tools_response = send_rpc(proc, "tools/list", {}, 2)
    print("TOOLS:", json.dumps(tools_response, indent=2))

    call_response = send_rpc(
        proc,
        "tools/call",
        {"name": "list_directory", "arguments": {"path": home}},
        3,
    )
    print("LIST_DIR:", json.dumps(call_response, indent=2)[:500])

    proc.terminate()
    proc.wait(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
