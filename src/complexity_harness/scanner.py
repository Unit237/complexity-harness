from __future__ import annotations

from fnmatch import fnmatch
import json
import os
from pathlib import Path
import subprocess
from typing import Any, Iterable

from .health import cyclomatic_findings
from .memory import load_architectural_memory
from .models import FileMetric, Snapshot
from .python_analyzer import analyze_python
from .tree_sitter_analyzer import SUPPORTED_SUFFIXES, analyze_tree_sitter


DEFAULT_EXCLUDE = {
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    ".build", ".spec", "coverage", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".tox", ".dart_tool", ".next", ".nuxt",
    ".parcel-cache", ".prerender", ".svelte-kit", ".turbo", "generated",
    "out", "target",
}


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


def _matches_pattern(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/").lstrip("./")
    if not normalized:
        return False
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return fnmatch(path, normalized) or (
        normalized.startswith("**/") and fnmatch(path, normalized[3:])
    )


def _is_excluded(
    relative: Path,
    *,
    directory_names: set[str],
    patterns: set[str],
    workspace_path: str | None,
) -> bool:
    if any(part in directory_names for part in relative.parts):
        return True
    repository_relative = relative.as_posix()
    candidates = {repository_relative}
    if workspace_path:
        candidates.add(f"{workspace_path.rstrip('/')}/{repository_relative}")
    return any(
        _matches_pattern(candidate, pattern)
        for candidate in candidates
        for pattern in patterns
    )


def _is_directory_exclusion(value: str) -> bool:
    return "/" not in value and "*" not in value


def _exclusion_rules(
    config: dict[str, Any],
    exclude_patterns: list[str] | set[str] | None,
) -> tuple[set[str], set[str]]:
    configured = {str(value) for value in config.get("exclude") or []}
    directory_names = DEFAULT_EXCLUDE | set(filter(
        _is_directory_exclusion,
        configured,
    ))
    patterns = configured - directory_names
    patterns.update(str(value) for value in exclude_patterns or [])
    return directory_names, patterns


def _source_files(
    root: Path,
    *,
    directory_exclusions: set[str],
    pattern_exclusions: set[str],
    workspace_path: str | None,
) -> Iterable[Path]:
    supported_suffixes = SUPPORTED_SUFFIXES | {".py"}
    for directory, directory_names, file_names in os.walk(root):
        current = Path(directory)
        relative_directory = current.relative_to(root)
        directory_names[:] = sorted(
            name for name in directory_names
            if not _is_excluded(
                relative_directory / name,
                directory_names=directory_exclusions,
                patterns=pattern_exclusions,
                workspace_path=workspace_path,
            )
        )
        for name in sorted(file_names):
            path = current / name
            if path.suffix.lower() not in supported_suffixes:
                continue
            relative = path.relative_to(root)
            if not _is_excluded(
                relative,
                directory_names=directory_exclusions,
                patterns=pattern_exclusions,
                workspace_path=workspace_path,
            ):
                yield path


def _analyze_source(path: Path, root: Path) -> FileMetric:
    analyzer = analyze_python if path.suffix.lower() == ".py" else analyze_tree_sitter
    return analyzer(path, relative_path=path.relative_to(root).as_posix())


def scan_repository(
    root: str | Path,
    *,
    exclude_patterns: list[str] | set[str] | None = None,
    workspace_path: str | None = None,
    architectural_memory_path: str | Path | None = None,
) -> Snapshot:
    repository_root = Path(root).resolve()
    config = _config(repository_root)
    directory_exclusions, pattern_exclusions = _exclusion_rules(
        config, exclude_patterns
    )
    files = sorted((
        _analyze_source(path, repository_root)
        for path in _source_files(
            repository_root,
            directory_exclusions=directory_exclusions,
            pattern_exclusions=pattern_exclusions,
            workspace_path=workspace_path,
        )
    ), key=lambda row: row.path)
    threshold = max(2, int(config.get("cyclomatic_threshold") or 15))
    findings = cyclomatic_findings(files, threshold=threshold)
    return Snapshot(
        repository={
            "name": repository_root.name,
            "root": str(repository_root),
            "commit": _commit(repository_root),
            "configuration": {
                "cyclomatic_threshold": threshold,
                "required_checks": list(config.get("required_checks") or []),
            },
        },
        files=files,
        findings=findings,
        architectural_memory=load_architectural_memory(
            repository_root,
            path=architectural_memory_path,
        ),
    )
