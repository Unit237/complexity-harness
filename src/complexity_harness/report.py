from __future__ import annotations

from typing import Any


def _cell(value: object) -> str:
    return str(value if value is not None else "—").replace("|", "\\|")


def markdown_report(snapshot: dict[str, Any], *, top: int = 15) -> str:
    summary = snapshot["summary"]
    title = (
        snapshot["workspace"]["name"]
        if snapshot.get("schema_version") == "complexity-workspace-snapshot-v1"
        else snapshot["repository"]["name"]
    )
    lines = [
        f"# Complexity report: {title}",
        "",
        f"- **Files analyzed:** {summary['files']:,}",
        f"- **Functions analyzed:** {summary['functions']:,}",
        f"- **Hotspots:** {summary['findings']:,}",
        f"- **Architectural-memory entries:** {summary['architectural_memory_entries']:,}",
    ]
    if "registered_invariants" in summary:
        lines.append(f"- **Registered invariants:** {summary['registered_invariants']:,}")
    if snapshot.get("schema_version") == "complexity-workspace-snapshot-v1":
        lines.extend([
            "",
            "## Repositories",
            "",
            "| Repository | Files | Functions | Hotspots | Memory | Invariants |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for repository in snapshot["repositories"]:
            row = repository["summary"]
            lines.append(
                f"| {_cell(repository['name'])} | {row['files']:,} | "
                f"{row['functions']:,} | {row['findings']:,} | "
                f"{row['architectural_memory_entries']:,} | "
                f"{row.get('registered_invariants', 0):,} |"
            )
    lines.extend([
        "",
        f"## Top {min(top, len(snapshot['findings']))} investigation candidates",
        "",
        "| CC | Repository | Symbol | Path | Finding |",
        "|---:|---|---|---|---|",
    ])
    repository_names = {
        row["id"]: row["name"] for row in snapshot.get("repositories") or []
    }
    for finding in snapshot["findings"][:top]:
        lines.append(
            f"| {finding['factors']['cyclomatic']} | "
            f"{_cell(repository_names.get(finding.get('repository_id'), '—'))} | "
            f"`{_cell(finding['symbol'])}` | `{_cell(finding['path'])}` | "
            f"`{finding['id']}` |"
        )
    lines.extend([
        "",
        "> Cyclomatic complexity is local control-flow evidence, not an automatic refactor order. Read tests and architectural memory before selecting work.",
        "",
    ])
    return "\n".join(lines)
