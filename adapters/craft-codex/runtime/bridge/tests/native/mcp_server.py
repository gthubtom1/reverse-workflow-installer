from __future__ import annotations

import json
import sys

TOOLS = [
    "build_files_list",
    "build_file_read",
    "build_file_write",
    "build_file_edit",
    "build_command_run",
    "build_checklist",
]


def reply(message_id: int, result: object) -> None:
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": message_id, "result": result}) + "\n")
    sys.stdout.flush()


def main() -> None:
    for line in sys.stdin:
        message = json.loads(line)
        method = message.get("method")
        if method == "initialize":
            reply(message["id"], {"protocolVersion": "2024-11-05", "capabilities": {}, "serverInfo": {"name": "native-driver-mcp", "version": "1"}})
        elif method == "tools/list":
            reply(message["id"], {"tools": [{"name": name, "description": "fixture bounded tool", "inputSchema": {"type": "object", "properties": {"value": {"type": "string"}}, "additionalProperties": False}} for name in TOOLS]})
        elif method == "tools/call":
            name = message.get("params", {}).get("name")
            if name == "build_files_list":
                reply(message["id"], {"content": [{"type": "text", "text": "fixture files list"}], "isError": False})
            else:
                reply(message["id"], {"content": [{"type": "text", "text": "fixture rejected tool"}], "isError": True})
        elif "id" in message:
            reply(message["id"], {"error": {"code": -32601, "message": "fixture method unavailable"}})


if __name__ == "__main__":
    main()
