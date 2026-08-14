from __future__ import annotations

import hashlib

from .models import FileMetric, Finding


def cyclomatic_findings(files: list[FileMetric], *, threshold: int) -> list[Finding]:
    findings: list[Finding] = []
    for file in files:
        for function in file.functions:
            if function.cyclomatic < threshold:
                continue
            finding_id = "CYC-" + hashlib.sha256(
                f"{file.path}:{function.symbol}:cyclomatic-v1".encode()
            ).hexdigest()[:12].upper()
            severity = "high" if function.cyclomatic >= max(25, threshold * 2) else "medium"
            findings.append(Finding(
                id=finding_id,
                kind="cyclomatic-hotspot",
                severity=severity,
                path=file.path,
                symbol=function.symbol,
                message=(
                    f"{function.symbol} has cyclomatic complexity {function.cyclomatic} "
                    f"against threshold {threshold}."
                ),
                factors={
                    "cyclomatic": function.cyclomatic,
                    "threshold": threshold,
                    "excess": function.cyclomatic - threshold,
                },
                evidence=tuple({
                    "kind": branch.kind,
                    "line": branch.line,
                    "contribution": branch.contribution,
                } for branch in function.branches),
            ))
    return sorted(findings, key=lambda row: (-int(row.factors["cyclomatic"]), row.path, row.symbol))
