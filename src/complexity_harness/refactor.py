from __future__ import annotations

from typing import Any

from .memory import memory_for_paths


def build_refactor_job(
    snapshot: dict[str, Any],
    finding_id: str,
    *,
    executor: str | None = None,
) -> dict[str, Any]:
    finding = next((row for row in snapshot["findings"] if row["id"] == finding_id), None)
    if finding is None:
        raise ValueError(f"unknown finding: {finding_id}")
    related_memory = memory_for_paths(snapshot["architectural_memory"], [finding["path"]])
    checks = snapshot["repository"].get("configuration", {}).get("required_checks") or []
    return {
        "schema_version": "refactor-job-v1",
        "finding_id": finding_id,
        "executor": executor,
        "objective": (
            f"Reduce the control-flow complexity of {finding['symbol']} while preserving "
            "observable behavior and registered architectural invariants."
        ),
        "evidence": finding,
        "architectural_memory_ids": [row["id"] for row in related_memory],
        "scope": {
            "allowed_paths": [finding["path"]],
            "max_changed_files": 5,
            "scope_expansion": "stop-and-request-review",
        },
        "verification": {
            "required_checks": checks,
            "before_after_snapshot": True,
            "behavior_characterization_required": True,
        },
        "policy": {
            "approval": "human-required",
            "output": "draft-change-or-draft-pr",
            "automatic_merge": False,
            "production_deploy": False,
            "secrets_access": False,
            "destructive_migrations": False,
        },
    }
