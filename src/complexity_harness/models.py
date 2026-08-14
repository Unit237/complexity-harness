from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class BranchEvidence:
    kind: str
    line: int
    contribution: int = 1


@dataclass(frozen=True)
class FunctionMetric:
    symbol: str
    line: int
    end_line: int
    cyclomatic: int
    branches: tuple[BranchEvidence, ...] = ()


@dataclass(frozen=True)
class FileMetric:
    path: str
    language: str
    sha256: str
    lines: int
    functions: tuple[FunctionMetric, ...] = ()
    parse_error: str | None = None

    @property
    def max_cyclomatic(self) -> int:
        return max((row.cyclomatic for row in self.functions), default=0)


@dataclass(frozen=True)
class Finding:
    id: str
    kind: str
    severity: str
    path: str
    symbol: str
    message: str
    factors: dict[str, Any]
    evidence: tuple[dict[str, Any], ...] = ()


@dataclass
class Snapshot:
    repository: dict[str, Any]
    files: list[FileMetric]
    findings: list[Finding]
    architectural_memory: list[dict[str, Any]] = field(default_factory=list)
    schema_version: str = "complexity-snapshot-v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "summary": {
                "files": len(self.files),
                "functions": sum(len(row.functions) for row in self.files),
                "findings": len(self.findings),
                "architectural_memory_entries": len(self.architectural_memory),
            },
            "files": [asdict(row) | {"max_cyclomatic": row.max_cyclomatic} for row in self.files],
            "findings": [asdict(row) for row in self.findings],
            "architectural_memory": self.architectural_memory,
        }
