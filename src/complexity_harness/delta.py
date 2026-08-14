from __future__ import annotations

from typing import Any


def diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_files = {row["path"]: row for row in before["files"]}
    after_files = {row["path"]: row for row in after["files"]}
    changed = sorted(
        path for path in before_files.keys() & after_files.keys()
        if before_files[path].get("sha256") != after_files[path].get("sha256")
    )
    before_findings = {row["id"]: row for row in before["findings"]}
    after_findings = {row["id"]: row for row in after["findings"]}
    changed_findings = []
    for key in sorted(before_findings.keys() & after_findings.keys()):
        old = before_findings[key]
        new = after_findings[key]
        old_value = int(old.get("factors", {}).get("cyclomatic", 0))
        new_value = int(new.get("factors", {}).get("cyclomatic", 0))
        if old_value != new_value:
            changed_findings.append({
                "id": key,
                "path": new.get("path"),
                "symbol": new.get("symbol"),
                "before": old_value,
                "after": new_value,
                "delta": new_value - old_value,
            })
    return {
        "schema_version": "complexity-delta-v1",
        "files": {
            "added": sorted(after_files.keys() - before_files.keys()),
            "removed": sorted(before_files.keys() - after_files.keys()),
            "changed": changed,
        },
        "findings": {
            "introduced": [after_findings[key] for key in sorted(after_findings.keys() - before_findings.keys())],
            "resolved": [before_findings[key] for key in sorted(before_findings.keys() - after_findings.keys())],
            "changed": changed_findings,
        },
    }
