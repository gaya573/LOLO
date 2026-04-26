from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from .config import Worker


@dataclass(frozen=True)
class McpEntry:
    pc: str
    app: str
    name: str
    kind: str
    target: str
    source: str
    status: str = "found"


def inspect_local_mcp(pc_name: str = "this-pc") -> list[McpEntry]:
    entries: list[McpEntry] = []
    home = Path.home()
    entries.extend(_read_cursor_mcp(home / ".cursor" / "mcp.json", pc_name))
    entries.extend(_read_codex_mcp(home / ".codex" / "config.toml", pc_name))
    return entries


def inspect_workers_mcp(workers: list[Worker]) -> list[McpEntry]:
    entries: list[McpEntry] = []
    for worker in workers:
        if worker.type == "local":
            entries.extend(inspect_local_mcp(worker.name))
            continue
        entries.extend(_inspect_ssh_worker(worker))
    return entries


def _read_cursor_mcp(path: Path, pc_name: str) -> list[McpEntry]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [_error_entry(pc_name, "Cursor", path, exc)]
    servers = data.get("mcpServers", {})
    if not isinstance(servers, dict):
        return []
    return [_entry_from_config(pc_name, "Cursor", name, config, path) for name, config in servers.items()]


def _read_codex_mcp(path: Path, pc_name: str) -> list[McpEntry]:
    if not path.exists():
        return []
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [_error_entry(pc_name, "Codex", path, exc)]
    servers = data.get("mcp_servers", {})
    if not isinstance(servers, dict):
        return []
    return [_entry_from_config(pc_name, "Codex", name, config, path) for name, config in servers.items()]


def _entry_from_config(pc_name: str, app: str, name: str, config: object, path: Path) -> McpEntry:
    if not isinstance(config, dict):
        return McpEntry(pc=pc_name, app=app, name=str(name), kind="unknown", target="", source=str(path), status="invalid")
    if "url" in config:
        return McpEntry(pc=pc_name, app=app, name=str(name), kind="url", target=str(config.get("url", "")), source=str(path))
    command = str(config.get("command", ""))
    args = config.get("args", [])
    if isinstance(args, list):
        target = " ".join([command, *[str(item) for item in args]]).strip()
    else:
        target = command
    return McpEntry(pc=pc_name, app=app, name=str(name), kind="command", target=target, source=str(path))


def _inspect_ssh_worker(worker: Worker) -> list[McpEntry]:
    command = f"cd \"{worker.workdir}\" && python -m local_compute_mcp.mcp_registry --json --pc {worker.name}"
    argv = ["ssh", "-p", str(worker.port)]
    for option in worker.ssh_options:
        argv.extend(["-o", option])
    argv.extend([worker.target, command])
    completed = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
    if completed.returncode != 0:
        return [
            McpEntry(
                pc=worker.name,
                app="Remote",
                name="SSH connection",
                kind="error",
                target=worker.host,
                source=worker.workdir,
                status=completed.stderr.strip() or f"exit {completed.returncode}",
            )
        ]
    try:
        rows = json.loads(completed.stdout)
        return [McpEntry(**row) for row in rows]
    except Exception as exc:
        return [McpEntry(pc=worker.name, app="Remote", name="MCP read", kind="error", target="", source=worker.workdir, status=str(exc))]


def _error_entry(pc_name: str, app: str, path: Path, exc: Exception) -> McpEntry:
    return McpEntry(pc=pc_name, app=app, name="config read", kind="error", target="", source=str(path), status=str(exc))


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect local Codex/Cursor MCP registrations")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--pc", default="this-pc")
    args = parser.parse_args()
    entries = inspect_local_mcp(args.pc)
    if args.json:
        print(json.dumps([asdict(entry) for entry in entries], ensure_ascii=False))
    else:
        for entry in entries:
            print(f"{entry.pc}\t{entry.app}\t{entry.name}\t{entry.kind}\t{entry.target}\t{entry.status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
