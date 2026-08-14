from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from complexity_harness.refactor import build_refactor_job


ROOT = Path(__file__).resolve().parents[1]


def test_public_json_schemas_are_well_formed():
    for path in sorted((ROOT / "contracts").glob("*.schema.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text()))


def test_refactor_job_conforms_to_public_harness_policy():
    policy = json.loads((ROOT / "contracts/harness-policy-v1.json").read_text())
    finding = {
        "id": "CYC-TEST",
        "kind": "cyclomatic-hotspot",
        "severity": "medium",
        "path": "service.py",
        "symbol": "choose",
        "message": "test finding",
        "factors": {"cyclomatic": 12, "threshold": 10, "excess": 2},
        "evidence": [{"kind": "if", "line": 2, "contribution": 1}],
    }
    snapshot = {
        "repository": {"configuration": {"required_checks": ["pytest -q"]}},
        "findings": [finding],
        "architectural_memory": [],
    }

    job = build_refactor_job(snapshot, finding["id"], executor="example-adapter")
    schema = json.loads((ROOT / "contracts/refactor-job-v1.schema.json").read_text())
    Draft202012Validator(schema).validate(job)

    assert policy["measurements"]["cyclomatic"]["meaning"] == "local-control-flow-path-count"
    assert policy["architectural_memory"]["separate_from_numeric_findings"] is True
    assert job["scope"] == {
        "allowed_paths": ["service.py"],
        **policy["refactor_jobs"]["required_scope_controls"],
    }
    assert job["verification"] | policy["refactor_jobs"]["required_verification"] == job["verification"]
    assert job["policy"] == policy["refactor_jobs"]["required_policy"]


def test_refactor_job_blocks_execution_without_verification():
    snapshot = {
        "repository": {"name": "example", "configuration": {"required_checks": []}},
        "findings": [{
            "id": "CYC-BLOCKED",
            "kind": "cyclomatic-hotspot",
            "severity": "medium",
            "path": "service.py",
            "symbol": "choose",
            "message": "test finding",
            "factors": {"cyclomatic": 12, "threshold": 10, "excess": 2},
            "evidence": [],
        }],
        "architectural_memory": [],
    }

    job = build_refactor_job(snapshot, "CYC-BLOCKED")

    assert job["readiness"]["status"] == "blocked"
    assert job["readiness"]["blockers"]
    assert "BLOCKED" in job["agent_prompt"]


def test_refactor_job_rejects_unsafe_scope_paths():
    snapshot = {
        "repository": {"name": "example", "configuration": {"required_checks": ["pytest -q"]}},
        "findings": [{
            "id": "CYC-SCOPED",
            "path": "service.py",
            "symbol": "choose",
            "factors": {"cyclomatic": 12, "threshold": 10},
        }],
        "architectural_memory": [],
    }

    with pytest.raises(ValueError, match="safe relative file paths"):
        build_refactor_job(snapshot, "CYC-SCOPED", allowed_paths=["../outside.py"])
