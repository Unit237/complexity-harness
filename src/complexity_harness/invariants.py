from __future__ import annotations

import json
from pathlib import Path
from typing import Any


REQUIRED = {
    "id",
    "name",
    "owner",
    "version",
    "contract",
    "status",
    "manifestations",
    "exceptions",
    "conformance_tests",
}


def load_invariants(path: str | Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    registry_path = Path(path).resolve()
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    entries = payload.get("invariants")
    if not isinstance(entries, list):
        raise ValueError(f"{registry_path}: invariants must be a list")
    seen: set[str] = set()
    for entry in entries:
        missing = REQUIRED - set(entry)
        if missing:
            raise ValueError(f"{registry_path}: invariant is missing {sorted(missing)}")
        invariant_id = str(entry["id"])
        if invariant_id in seen:
            raise ValueError(f"{registry_path}: duplicate invariant id {invariant_id}")
        seen.add(invariant_id)
    return entries


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _invariant_paths(entry: dict[str, Any]) -> list[str]:
    paths = [
        str(row.get("path") or "").strip("/")
        for row in entry.get("manifestations") or []
        if isinstance(row, dict)
    ]
    paths.extend(str(value).strip("/") for value in entry.get("conformance_tests") or [])
    contract = str(entry.get("contract") or "").strip("/")
    if contract:
        paths.append(contract)
    return [path for path in paths if path]


def invariants_for_paths(
    entries: list[dict[str, Any]],
    paths: list[str],
) -> list[dict[str, Any]]:
    normalized = {Path(value).as_posix().lstrip("./") for value in paths}
    return [
        entry for entry in entries
        if any(
            _paths_overlap(path, evidence)
            for path in normalized
            for evidence in _invariant_paths(entry)
        )
    ]


def invariants_for_repository(
    entries: list[dict[str, Any]],
    repository_path: str,
) -> list[dict[str, Any]]:
    return invariants_for_paths(entries, [repository_path])
