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


def _require_finding(snapshot: dict[str, Any], finding_id: str) -> dict[str, Any]:
    finding = next(
        (row for row in snapshot["findings"] if row["id"] == finding_id),
        None,
    )
    if finding is None:
        raise ValueError(f"unknown finding: {finding_id}")
    return finding


def _job_source(
    snapshot: dict[str, Any],
    finding: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
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
        return repository, source

    repository = snapshot["repository"]
    source = {
        "snapshot_schema": snapshot.get("schema_version", "complexity-snapshot-v1"),
        "repository": repository.get("name"),
        "repository_path": ".",
        "commit": repository.get("commit"),
    }
    return repository, source


def _required_checks(
    repository: dict[str, Any],
    required_checks: list[str] | None,
) -> list[str]:
    return list(
        required_checks
        if required_checks is not None
        else repository.get("configuration", {}).get("required_checks") or []
    )


def _scope_paths(
    finding: dict[str, Any],
    allowed_paths: list[str] | None,
) -> list[str]:
    paths = list(dict.fromkeys(
        _normalize_scope_path(value)
        for value in [finding["path"], *(allowed_paths or [])]
    ))
    if len(paths) > 5:
        raise ValueError("refactor jobs allow at most five explicit paths")
    return paths


def _validate_workspace_scope(
    snapshot: dict[str, Any],
    source: dict[str, Any],
    paths: list[str],
) -> None:
    repository_prefix = str(source["repository_path"]).strip("/")
    if (
        snapshot.get("schema_version") == "complexity-workspace-snapshot-v1"
        and repository_prefix != "."
    ):
        outside_repository = [
            path for path in paths
            if not path.startswith(repository_prefix + "/")
        ]
        if outside_repository:
            raise ValueError(
                "workspace refactor jobs cannot cross canonical repositories: "
                + ", ".join(outside_repository)
            )


def _readiness(checks: list[str]) -> dict[str, Any]:
    blockers = [] if checks else [
        "No required verification command is registered. Add --check before execution."
    ]
    return {
        "status": "ready" if not blockers else "blocked",
        "blockers": blockers,
    }


def build_refactor_job(
    snapshot: dict[str, Any],
    finding_id: str,
    *,
    executor: str | None = None,
    allowed_paths: list[str] | None = None,
    required_checks: list[str] | None = None,
) -> dict[str, Any]:
    finding = _require_finding(snapshot, finding_id)
    related_memory = memory_for_paths(snapshot["architectural_memory"], [finding["path"]])
    related_invariants = invariants_for_paths(
        snapshot.get("invariants") or [],
        [finding["path"]],
    )
    repository, source = _job_source(snapshot, finding)
    checks = _required_checks(repository, required_checks)
    paths = _scope_paths(finding, allowed_paths)
    _validate_workspace_scope(snapshot, source, paths)
    readiness = _readiness(checks)
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
        "readiness": readiness,
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
