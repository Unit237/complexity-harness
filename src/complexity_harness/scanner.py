from __future__ import annotations

from fnmatch import fnmatch
import json
from pathlib import Path
import subprocess
from typing import Any

from .health import cyclomatic_findings
from .memory import load_architectural_memory
from .models import Snapshot
from .python_analyzer import analyze_python


DEFAULT_EXCLUDE = {
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    ".build", ".spec", "coverage", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".tox",
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


def scan_repository(
    root: str | Path,
    *,
    exclude_patterns: list[str] | set[str] | None = None,
    workspace_path: str | None = None,
    architectural_memory_path: str | Path | None = None,
) -> Snapshot:
    repository_root = Path(root).resolve()
    config = _config(repository_root)
    configured_exclude = {str(value) for value in config.get("exclude") or []}
    exclude_names = DEFAULT_EXCLUDE | {
        value for value in configured_exclude if "/" not in value and "*" not in value
    }
    patterns = {
        value for value in configured_exclude if value not in exclude_names
    } | {str(value) for value in exclude_patterns or []}
    files = []
    for path in sorted(repository_root.rglob("*.py")):
        relative = path.relative_to(repository_root)
        if _is_excluded(
            relative,
            directory_names=exclude_names,
            patterns=patterns,
            workspace_path=workspace_path,
        ):
            continue
        files.append(analyze_python(path, relative_path=relative.as_posix()))
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
