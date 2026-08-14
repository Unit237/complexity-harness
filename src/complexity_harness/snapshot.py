from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_snapshot(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_snapshot(payload)
    return payload


def validate_snapshot(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != "complexity-snapshot-v1":
        raise ValueError("unsupported complexity snapshot schema")
    for key in ("repository", "files", "findings", "architectural_memory"):
        if key not in payload:
            raise ValueError(f"snapshot is missing {key}")
    finding_ids = [row.get("id") for row in payload["findings"]]
    if len(finding_ids) != len(set(finding_ids)):
        raise ValueError("finding ids must be unique")


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    Path(path).write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
