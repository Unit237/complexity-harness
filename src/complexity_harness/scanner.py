from __future__ import annotations

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
    "__pycache__", ".pytest_cache", ".mypy_cache", ".tox",
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


def scan_repository(root: str | Path) -> Snapshot:
    repository_root = Path(root).resolve()
    config = _config(repository_root)
    exclude = DEFAULT_EXCLUDE | {str(value) for value in config.get("exclude") or []}
    files = []
    for path in sorted(repository_root.rglob("*.py")):
        relative = path.relative_to(repository_root)
        if any(part in exclude for part in relative.parts):
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
        architectural_memory=load_architectural_memory(repository_root),
    )
