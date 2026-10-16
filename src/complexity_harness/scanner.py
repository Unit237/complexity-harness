from __future__ import annotations

import json
from pathlib import Path
import subprocess
import os
from typing import Any

from .health import cyclomatic_findings
from .memory import load_architectural_memory
from .models import Snapshot
from .polyglot_analyzer import analyze_bytes
from .burden import CONTROL_LANGUAGES, STRUCTURAL_LANGUAGES
from .complexity_languages import classify_path
from .burden import ANALYZER
from .source_scope import _is_excluded, source_policy, content_fingerprint


def _config(root: Path) -> dict[str, Any]:
    path = root / ".complexity" / "config.json"
    if not path.is_file() or path.is_symlink():
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
    files, unsupported, unsupported_hashes, entries = [], [], {}, []
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
        if not path.is_file() and not path.is_symlink():
            continue
        relative = path.relative_to(repository_root)
        name = relative.as_posix()
        data = os.readlink(path).encode() if path.is_symlink() else path.read_bytes()
        entry = {"path":name, "sha256":content_fingerprint(data), **classify_path(name)}
        if _is_excluded(relative,directory_names=exclude_names,patterns=patterns,workspace_path=workspace_path):
            entry.update(kind="excluded",reason="Repository exclusion policy")
        eligible = entry["kind"] in {"source","unknown","opaque"}
        if eligible and not path.is_symlink() and len(data)<=512*1024 and entry["language"] in CONTROL_LANGUAGES | STRUCTURAL_LANGUAGES:
            try:
                metric = analyze_bytes(data,relative_path=name,language=entry["language"])
                files.append(metric)
                entry["status"] = "parse_error" if metric.parse_error else "measured"
                if metric.parse_error:
                    entry["reason"] = metric.parse_error
            except UnicodeDecodeError:
                entry.update(status="unsupported",reason="Source encoding is not UTF-8")
        elif eligible:
            entry.update(status="unsupported",reason="Symlink, oversized source or no validated adapter")
        else:
            entry["status"] = entry["kind"]
        if entry["status"] == "unsupported":
            unsupported.append(name);unsupported_hashes[name]=entry["sha256"]
        entries.append(entry)
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
            "scope_hash": scope_hash, "inventory_complete": True, "inventory": entries,
            "eligible_files": len(files)+len(unsupported), "inventory_policy": "all-files-v2"},
        findings=findings,
        architectural_memory=load_architectural_memory(
            repository_root,
            path=architectural_memory_path,
        ),
    )
