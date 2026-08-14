from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .invariants import load_invariants, invariants_for_repository
from .memory import load_architectural_memory, memory_for_repository
from .scanner import scan_repository


def _default_inventory(root: Path) -> Path:
    candidates = (
        root / ".complexity" / "repositories.json",
        root / "architecture" / "repositories.json",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ValueError(
        "repository inventory not found; pass --inventory or create "
        ".complexity/repositories.json"
    )


def _default_memory(root: Path) -> Path | None:
    candidates = (
        root / ".complexity" / "architectural-memory.json",
        root / "architecture" / "architectural-memory.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def _default_invariants(root: Path) -> Path | None:
    candidates = (
        root / ".complexity" / "invariants.json",
        root / "architecture" / "invariants.json",
    )
    return next((path for path in candidates if path.is_file()), None)


def _within(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _workspace_finding_id(repository_id: str, local_id: str) -> str:
    digest = hashlib.sha256(
        f"{repository_id}:{local_id}:workspace-v1".encode()
    ).hexdigest()[:12].upper()
    return f"CYC-{digest}"


def scan_workspace(
    root: str | Path,
    *,
    inventory_path: str | Path | None = None,
    architectural_memory_path: str | Path | None = None,
    invariants_path: str | Path | None = None,
) -> dict[str, Any]:
    workspace_root = Path(root).resolve()
    inventory_file = (
        Path(inventory_path).resolve()
        if inventory_path
        else _default_inventory(workspace_root)
    )
    inventory = json.loads(inventory_file.read_text(encoding="utf-8"))
    repositories = inventory.get("repositories")
    if not isinstance(repositories, list):
        raise ValueError(f"{inventory_file}: repositories must be a list")

    memory_file = (
        Path(architectural_memory_path).resolve()
        if architectural_memory_path
        else _default_memory(workspace_root)
    )
    architectural_memory = (
        load_architectural_memory(workspace_root, path=memory_file)
        if memory_file
        else []
    )
    invariants_file = (
        Path(invariants_path).resolve()
        if invariants_path
        else _default_invariants(workspace_root)
    )
    invariants = load_invariants(invariants_file)
    exclude_patterns = [str(value) for value in inventory.get("excluded_paths") or []]
    repository_rows: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []

    canonical = [
        row for row in repositories
        if isinstance(row, dict) and row.get("status", "canonical") == "canonical"
    ]
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()
    for definition in canonical:
        repository_id = str(definition.get("id") or "").strip()
        repository_path = Path(str(definition.get("path") or "")).as_posix().strip("/")
        if not repository_id or not repository_path:
            raise ValueError("every canonical repository needs an id and path")
        if repository_id in seen_ids:
            raise ValueError(f"duplicate repository id: {repository_id}")
        if repository_path in seen_paths:
            raise ValueError(f"duplicate canonical repository path: {repository_path}")
        seen_ids.add(repository_id)
        seen_paths.add(repository_path)

        repository_root = (workspace_root / repository_path).resolve()
        if not _within(workspace_root, repository_root):
            raise ValueError(f"repository escapes workspace root: {repository_path}")
        if not repository_root.is_dir():
            raise ValueError(f"canonical repository is missing: {repository_path}")

        snapshot = scan_repository(
            repository_root,
            exclude_patterns=exclude_patterns,
            workspace_path=repository_path,
        ).as_dict()
        scoped_memory = memory_for_repository(architectural_memory, repository_path)
        scoped_invariants = invariants_for_repository(invariants, repository_path)
        repository_summary = dict(snapshot["summary"])
        repository_summary["architectural_memory_entries"] = len(scoped_memory)
        repository_summary["registered_invariants"] = len(scoped_invariants)
        repository_rows.append({
            "id": repository_id,
            "name": str(definition.get("name") or repository_id),
            "path": repository_path,
            "kind": definition.get("kind"),
            "remote": definition.get("remote"),
            "commit": snapshot["repository"].get("commit"),
            "configuration": snapshot["repository"].get("configuration", {}),
            "summary": repository_summary,
        })
        for row in snapshot["files"]:
            files.append({
                **row,
                "repository_id": repository_id,
                "path": f"{repository_path}/{row['path']}",
            })
        for row in snapshot["findings"]:
            local_id = row["id"]
            findings.append({
                **row,
                "id": _workspace_finding_id(repository_id, local_id),
                "local_id": local_id,
                "repository_id": repository_id,
                "path": f"{repository_path}/{row['path']}",
            })

    findings.sort(
        key=lambda row: (
            -int(row["factors"]["cyclomatic"]),
            row["repository_id"],
            row["path"],
            row["symbol"],
        )
    )
    return {
        "schema_version": "complexity-workspace-snapshot-v1",
        "workspace": {
            "name": workspace_root.name,
            "root": str(workspace_root),
            "inventory": str(inventory_file),
            "architectural_memory": str(memory_file) if memory_file else None,
            "invariants": str(invariants_file) if invariants_file else None,
            "excluded_paths": exclude_patterns,
            "aliases": inventory.get("aliases") or [],
        },
        "summary": {
            "repositories": len(repository_rows),
            "files": len(files),
            "functions": sum(len(row["functions"]) for row in files),
            "findings": len(findings),
            "architectural_memory_entries": len(architectural_memory),
            "registered_invariants": len(invariants),
        },
        "repositories": repository_rows,
        "files": files,
        "findings": findings,
        "architectural_memory": architectural_memory,
        "invariants": invariants,
    }
