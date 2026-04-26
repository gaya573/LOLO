from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import load_workers
from .mcp_registry import inspect_workers_mcp
from .runner import discover_jobs, retry_failed, run_jobs, test_worker


class McpServer:
    def __init__(self, config_path: str):
        self.config_path = config_path

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        request_id = message.get("id")
        try:
            if method == "initialize":
                return self._result(request_id, {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "local-compute-mcp", "version": "0.1.0"},
                })
            if method == "notifications/initialized":
                return None
            if method == "tools/list":
                return self._result(request_id, {"tools": self._tools()})
            if method == "tools/call":
                params = message.get("params", {})
                return self._result(request_id, self._call_tool(params.get("name"), params.get("arguments", {})))
            if request_id is not None:
                return self._error(request_id, -32601, f"Unknown method: {method}")
            return None
        except Exception as exc:
            return self._error(request_id, -32000, str(exc))

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        workers = load_workers(arguments.get("config_path", self.config_path))

        if name == "list_workers":
            data = [worker.__dict__ for worker in workers]
        elif name == "test_workers":
            data = [test_worker(worker).__dict__ for worker in workers]
        elif name == "submit_jobs":
            jobs = discover_jobs(arguments["input_dir"], arguments.get("pattern", "*"))
            data = run_jobs(
                workers,
                jobs,
                arguments["command"],
                arguments.get("output_dir", "outputs"),
                arguments.get("logs_dir", "logs"),
            )
        elif name == "retry_failed":
            data = retry_failed(
                workers,
                arguments["command"],
                arguments.get("output_dir", "outputs"),
                arguments.get("logs_dir", "logs"),
            )
        elif name == "inspect_mcp":
            data = [entry.__dict__ for entry in inspect_workers_mcp(workers)]
        else:
            raise ValueError(f"Unknown tool: {name}")

        return {"content": [{"type": "text", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}

    def _tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "list_workers",
                "description": "List enabled local and SSH workers from workers.yaml.",
                "inputSchema": {"type": "object", "properties": {"config_path": {"type": "string"}}},
            },
            {
                "name": "test_workers",
                "description": "Run a small echo command on every enabled worker.",
                "inputSchema": {"type": "object", "properties": {"config_path": {"type": "string"}}},
            },
            {
                "name": "submit_jobs",
                "description": "Split files from an input directory across workers and run a command template for each file.",
                "inputSchema": {
                    "type": "object",
                    "required": ["input_dir", "command"],
                    "properties": {
                        "input_dir": {"type": "string"},
                        "pattern": {"type": "string", "default": "*"},
                        "command": {"type": "string"},
                        "output_dir": {"type": "string", "default": "outputs"},
                        "logs_dir": {"type": "string", "default": "logs"},
                        "config_path": {"type": "string"},
                    },
                },
            },
            {
                "name": "retry_failed",
                "description": "Retry failed jobs recorded in logs/joblog.tsv.",
                "inputSchema": {
                    "type": "object",
                    "required": ["command"],
                    "properties": {
                        "command": {"type": "string"},
                        "output_dir": {"type": "string", "default": "outputs"},
                        "logs_dir": {"type": "string", "default": "logs"},
                        "config_path": {"type": "string"},
                    },
                },
            },
            {
                "name": "inspect_mcp",
                "description": "Inspect Codex/Cursor MCP registrations on enabled PCs.",
                "inputSchema": {"type": "object", "properties": {"config_path": {"type": "string"}}},
            },
        ]

    @staticmethod
    def _result(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def read_message() -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in {b"\r\n", b"\n"}:
            break
        key, value = line.decode("ascii").split(":", 1)
        headers[key.lower()] = value.strip()
    length = int(headers.get("content-length", "0"))
    if length <= 0:
        return None
    body = sys.stdin.buffer.read(length)
    return json.loads(body.decode("utf-8"))


def write_message(message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    sys.stdout.buffer.write(body)
    sys.stdout.buffer.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="Local Compute MCP server")
    parser.add_argument("--config", default=str(Path.cwd() / "workers.yaml"))
    args = parser.parse_args()

    server = McpServer(args.config)
    while True:
        message = read_message()
        if message is None:
            return 0
        response = server.handle(message)
        if response is not None:
            write_message(response)


if __name__ == "__main__":
    raise SystemExit(main())
