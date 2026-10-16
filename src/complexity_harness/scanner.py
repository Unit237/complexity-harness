from __future__ import annotations

import json
from pathlib import Path
import subprocess
import os
from typing import Any

from .health import cyclomatic_findings
from .memory import load_architectural_memory
from .models import Snapshot
from .python_analyzer import analyze_python
from .burden import ANALYZER
from .source_scope import SOURCE_SUFFIXES, _is_excluded, source_policy, content_fingerprint


def _config(root: Path) -> dict[str, Any]:
    path = root / ".complexity" / "config.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _commit(root: Path) -> str | None:
    completed = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() or None if completed.returncode == 0 else None


def scan_repository(
    root: str | Path,
    *,
    exclude_patterns: list[str] | set[str] | None = None,
    workspace_path: str | None = None,
    architectural_memory_path: str | Path | None = None,
) -> Snapshot:
    repository_root = Path(root).resolve()
    config = _config(repository_root)
    exclude_names, patterns, scope_hash = source_policy(config, exclude_patterns or ())
    files, unsupported, unsupported_hashes = [], [], {}
    inventory = subprocess.run(["git", "-C", str(repository_root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        capture_output=True, text=True, check=False)
    candidates = []
    if inventory.returncode == 0:
        # Ignored build or local files cannot be attributed to a clean commit.
        candidates = [repository_root / name for name in set(inventory.stdout.split("\0")) if name]
    else:
        for directory, names, filenames in os.walk(repository_root):
            relative_directory = Path(directory).relative_to(repository_root)
            names[:] = sorted(name for name in names if not _is_excluded(relative_directory / name,
                directory_names=exclude_names, patterns=patterns, workspace_path=workspace_path))
            candidates.extend(Path(directory) / name for name in filenames)
    for path in sorted(candidates):
        if (not path.is_file() and not path.is_symlink()) or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(repository_root)
        if _is_excluded(
            relative,
            directory_names=exclude_names,
            patterns=patterns,
            workspace_path=workspace_path,
        ):
            continue
        if path.suffix == ".py" and not path.is_symlink():
            files.append(analyze_python(path, relative_path=relative.as_posix()))
        else:
            unsupported.append(relative.as_posix())
            unsupported_hashes[relative.as_posix()] = content_fingerprint(os.readlink(path).encode() if path.is_symlink() else path.read_bytes())
    threshold = max(2, int(config.get("cyclomatic_threshold") or 15))
    findings = cyclomatic_findings(files, threshold=threshold)
    return Snapshot(
        repository={
            "name": repository_root.name,
            "root": str(repository_root),
            "commit": _commit(repository_root),
            "clean": subprocess.run(["git", "-C", str(repository_root), "status", "--porcelain", "--untracked-files=all"],
                capture_output=True, text=True, check=False).stdout.strip() == "",
            "configuration": {
                "cyclomatic_threshold": threshold,
                "required_checks": list(config.get("required_checks") or []),
            },
        },
        files=files,
        coverage={"analyzer": ANALYZER, "unsupported_paths": unsupported, "unsupported_hashes": unsupported_hashes,
            "scope_hash": scope_hash, "inventory_complete": True},
        findings=findings,
        architectural_memory=load_architectural_memory(
            repository_root,
            path=architectural_memory_path,
        ),
    )
