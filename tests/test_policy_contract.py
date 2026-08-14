from __future__ import annotations

import json
from pathlib import Path

from complexity_harness.refactor import build_refactor_job


ROOT = Path(__file__).resolve().parents[1]


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

    assert policy["measurements"]["cyclomatic"]["meaning"] == "local-control-flow-path-count"
    assert policy["architectural_memory"]["separate_from_numeric_findings"] is True
    assert job["scope"] == {
        "allowed_paths": ["service.py"],
        **policy["refactor_jobs"]["required_scope_controls"],
    }
    assert job["verification"] | policy["refactor_jobs"]["required_verification"] == job["verification"]
    assert job["policy"] == policy["refactor_jobs"]["required_policy"]
