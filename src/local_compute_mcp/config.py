from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Worker:
    name: str
    type: str
    enabled: bool = True
    max_jobs: int = 1
    workdir: str = "."
    host: str = ""
    user: str = ""
    port: int = 22
    ssh_options: list[str] = field(default_factory=list)

    @property
    def target(self) -> str:
        return f"{self.user}@{self.host}" if self.user else self.host


def load_workers(config_path: str | Path) -> list[Worker]:
    path = Path(config_path)
    data = _load_yaml_subset(path.read_text(encoding="utf-8"))
    workers = data.get("workers", [])
    return [Worker(**item) for item in workers if item.get("enabled", True)]


def load_all_workers(config_path: str | Path) -> list[Worker]:
    path = Path(config_path)
    data = _load_yaml_subset(path.read_text(encoding="utf-8"))
    workers = data.get("workers", [])
    return [Worker(**item) for item in workers]


def save_workers(config_path: str | Path, workers: list[Worker]) -> None:
    path = Path(config_path)
    lines = ["# Edit in the app or by hand. Same Wi-Fi, Tailscale, and ZeroTier all use host/IP here.", "workers:"]
    for worker in workers:
        lines.extend(
            [
                f"  - name: {_yaml_scalar(worker.name)}",
                f"    type: {_yaml_scalar(worker.type)}",
                f"    enabled: {_yaml_bool(worker.enabled)}",
                f"    max_jobs: {worker.max_jobs}",
                f"    workdir: {_yaml_scalar(worker.workdir)}",
            ]
        )
        if worker.type == "ssh":
            lines.extend(
                [
                    f"    host: {_yaml_scalar(worker.host)}",
                    f"    user: {_yaml_scalar(worker.user)}",
                    f"    port: {worker.port}",
                    "    ssh_options:",
                ]
            )
            options = worker.ssh_options or ["BatchMode=yes", "ConnectTimeout=8"]
            for option in options:
                lines.append(f"      - {_yaml_scalar(option)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "None", "~"}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _yaml_bool(value: bool) -> str:
    return "true" if value else "false"


def _yaml_scalar(value: str) -> str:
    if value == "":
        return '""'
    safe = all(ch.isalnum() or ch in "._-/:\\" for ch in value)
    if safe:
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _load_yaml_subset(text: str) -> dict[str, Any]:
    """Parse the small YAML shape used by workers.yaml without external deps."""
    result: dict[str, Any] = {}
    current_list_name: str | None = None
    current_item: dict[str, Any] | None = None
    current_nested_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()

        if indent == 0 and stripped.endswith(":"):
            current_list_name = stripped[:-1]
            result[current_list_name] = []
            current_item = None
            current_nested_key = None
            continue

        if current_list_name is None:
            continue

        if indent == 2 and stripped.startswith("- "):
            current_item = {}
            result[current_list_name].append(current_item)
            current_nested_key = None
            rest = stripped[2:]
            if ":" in rest:
                key, value = rest.split(":", 1)
                current_item[key.strip()] = _parse_scalar(value)
            continue

        if current_item is None:
            continue

        if indent == 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            if value.strip():
                current_item[key] = _parse_scalar(value)
                current_nested_key = None
            else:
                current_item[key] = []
                current_nested_key = key
            continue

        if indent == 6 and stripped.startswith("- ") and current_nested_key:
            current_item[current_nested_key].append(_parse_scalar(stripped[2:]))

    return result
