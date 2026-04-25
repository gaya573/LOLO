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
