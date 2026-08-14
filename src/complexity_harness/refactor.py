from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from .invariants import invariants_for_paths
from .memory import memory_for_paths


def _normalize_scope_path(value: str) -> str:
    raw = str(value).replace("\\", "/")
    while raw.startswith("./"):
        raw = raw[2:]
    path = PurePosixPath(raw)
    if not raw or raw == "." or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"scope paths must be safe relative file paths: {value!r}")
    return path.as_posix()


def build_refactor_job(
    snapshot: dict[str, Any],
    finding_id: str,
    *,
    executor: str | None = None,
    allowed_paths: list[str] | None = None,
    required_checks: list[str] | None = None,
) -> dict[str, Any]:
    finding = next((row for row in snapshot["findings"] if row["id"] == finding_id), None)
    if finding is None:
        raise ValueError(f"unknown finding: {finding_id}")
    related_memory = memory_for_paths(snapshot["architectural_memory"], [finding["path"]])
    related_invariants = invariants_for_paths(
        snapshot.get("invariants") or [],
        [finding["path"]],
    )
    if snapshot.get("schema_version") == "complexity-workspace-snapshot-v1":
        repository = next(
            (
                row for row in snapshot["repositories"]
                if row["id"] == finding.get("repository_id")
            ),
            None,
        )
        if repository is None:
            raise ValueError("workspace finding has no repository definition")
        source = {
            "snapshot_schema": snapshot["schema_version"],
            "workspace": snapshot["workspace"]["name"],
            "repository_id": repository["id"],
            "repository_path": repository["path"],
            "commit": repository.get("commit"),
        }
    else:
        repository = snapshot["repository"]
        source = {
            "snapshot_schema": snapshot.get("schema_version", "complexity-snapshot-v1"),
            "repository": repository.get("name"),
            "repository_path": ".",
            "commit": repository.get("commit"),
        }
    checks = list(
        required_checks
        if required_checks is not None
        else repository.get("configuration", {}).get("required_checks") or []
    )
    paths = list(dict.fromkeys(
        _normalize_scope_path(value)
        for value in [finding["path"], *(allowed_paths or [])]
    ))
    repository_prefix = str(source["repository_path"]).strip("/")
    if snapshot.get("schema_version") == "complexity-workspace-snapshot-v1" and repository_prefix != ".":
        outside_repository = [
            path for path in paths
            if not path.startswith(repository_prefix + "/")
        ]
        if outside_repository:
            raise ValueError(
                "workspace refactor jobs cannot cross canonical repositories: "
                + ", ".join(outside_repository)
            )
    if len(paths) > 5:
        raise ValueError("refactor jobs allow at most five explicit paths")
    blockers = [] if checks else [
        "No required verification command is registered. Add --check before execution."
    ]
    instructions = [
        "Read repository agent instructions and the attached architectural memory before editing.",
        "Characterize the current behavior with tests before changing control flow.",
        "Investigate analogous hotspots and shared invariants; do not move branches into a new helper merely to lower the number.",
        "Change only explicit allowed paths. Stop and request review if the correct fix needs broader scope.",
        "Run every required check, create an after snapshot, and report the evidence-based diff.",
        "Produce a draft change or draft PR only; do not merge or deploy.",
    ]
    job = {
        "schema_version": "refactor-job-v1",
        "finding_id": finding_id,
        "executor": executor,
        "objective": (
            f"Reduce the control-flow complexity of {finding['symbol']} while preserving "
            "observable behavior and registered architectural invariants."
        ),
        "source": source,
        "evidence": finding,
        "architectural_memory_ids": [row["id"] for row in related_memory],
        "architectural_memory": related_memory,
        "registered_invariant_ids": [row["id"] for row in related_invariants],
        "registered_invariants": related_invariants,
        "scope": {
            "allowed_paths": paths,
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
        "readiness": {
            "status": "ready" if not blockers else "blocked",
            "blockers": blockers,
        },
        "agent_instructions": instructions,
        "stop_conditions": [
            "Required behavior cannot be characterized.",
            "A registered invariant would need to change.",
            "The necessary edit leaves the allowed path set.",
            "A required check fails for reasons not caused by the bounded change.",
            "Secrets, destructive migrations, merge, or deployment access would be required.",
        ],
    }
    job["agent_prompt"] = _agent_prompt(job)
    return job


def _agent_prompt(job: dict[str, Any]) -> str:
    finding = job["evidence"]
    checks = job["verification"]["required_checks"]
    lines = [
        f"Execute bounded complexity refactor job {job['finding_id']}.",
        "",
        f"Objective: {job['objective']}",
        f"Finding: {finding['path']}::{finding['symbol']} "
        f"(cyclomatic {finding['factors']['cyclomatic']}, "
        f"threshold {finding['factors']['threshold']}).",
        f"Allowed paths: {', '.join(job['scope']['allowed_paths'])}",
        "",
        "Required workflow:",
        *[f"{index}. {value}" for index, value in enumerate(job["agent_instructions"], 1)],
        "",
        "Required checks:",
        *([f"- {value}" for value in checks] or ["- BLOCKED: define a verification command before editing."]),
        "",
        "Stop conditions:",
        *[f"- {value}" for value in job["stop_conditions"]],
        "",
        "Return the behavior characterization, files changed, check results, before/after complexity delta, and any architectural-memory implications.",
    ]
    return "\n".join(lines)
