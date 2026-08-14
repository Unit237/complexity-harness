from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED = {"id", "concept", "status", "summary", "evidence", "decision", "next_trigger"}


def load_architectural_memory(
    root: Path,
    *,
    path: str | Path | None = None,
) -> list[dict[str, Any]]:
    path = Path(path).resolve() if path else root / ".complexity" / "architectural-memory.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "architectural-memory-v1":
        raise ValueError(f"{path}: unsupported architectural memory schema")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"{path}: entries must be a list")
    seen: set[str] = set()
    for entry in entries:
        missing = REQUIRED - set(entry)
        if missing:
            raise ValueError(f"{path}: memory entry is missing {sorted(missing)}")
        if entry["id"] in seen:
            raise ValueError(f"{path}: duplicate memory id {entry['id']}")
        seen.add(entry["id"])
    return entries


def memory_for_repository(
    entries: list[dict[str, Any]],
    repository_path: str,
) -> list[dict[str, Any]]:
    """Return entries with evidence inside a canonical repository path."""
    normalized = Path(repository_path).as_posix().strip("/")
    return memory_for_paths(entries, [normalized])


def _paths_overlap(changed: str, evidence: str) -> bool:
    return (
        changed == evidence
        or changed.startswith(evidence + "/")
        or evidence.startswith(changed + "/")
    )


def _entry_matches_paths(entry: dict[str, Any], paths: set[str]) -> bool:
    for row in entry.get("evidence") or []:
        evidence = str(row.get("path") or "")
        if evidence and any(_paths_overlap(changed, evidence) for changed in paths):
            return True
    return False


def memory_for_paths(entries: list[dict[str, Any]], paths: list[str]) -> list[dict[str, Any]]:
    normalized = {Path(value).as_posix().lstrip("./") for value in paths}
    if not normalized:
        return entries
    return [entry for entry in entries if _entry_matches_paths(entry, normalized)]
