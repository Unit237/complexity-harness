from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_snapshot(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_snapshot(payload)
    return payload


def validate_snapshot(payload: dict[str, Any]) -> None:
    schema = payload.get("schema_version")
    if schema not in {
        "complexity-snapshot-v1",
        "complexity-workspace-snapshot-v1",
    }:
        raise ValueError("unsupported complexity snapshot schema")
    required = (
        ("workspace", "repositories", "files", "findings", "architectural_memory")
        if schema == "complexity-workspace-snapshot-v1"
        else ("repository", "files", "findings", "architectural_memory")
    )
    for key in required:
        if key not in payload:
            raise ValueError(f"snapshot is missing {key}")
    finding_ids = [row.get("id") for row in payload["findings"]]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("finding ids must be unique")
    file_paths = [row.get("path") for row in payload["files"]]
    if len(file_paths) != len(set(file_paths)):
        raise ValueError("file paths must be unique")
    summary = payload.get("summary")
    if isinstance(summary, dict):
        expected = {
            "files": len(payload["files"]),
            "functions": sum(len(row.get("functions") or []) for row in payload["files"]),
            "findings": len(payload["findings"]),
            "architectural_memory_entries": len(payload["architectural_memory"]),
        }
        for key, value in expected.items():
            if summary.get(key) != value:
                raise ValueError(
                    f"snapshot summary {key} is {summary.get(key)!r}; expected {value}"
                )


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
