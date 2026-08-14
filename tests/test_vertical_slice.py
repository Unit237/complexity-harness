from __future__ import annotations

import json
from pathlib import Path

from complexity_harness.delta import diff_snapshots
from complexity_harness.refactor import build_refactor_job
from complexity_harness.scanner import scan_repository
from complexity_harness.snapshot import validate_snapshot


def test_scan_health_memory_and_refactor_job_vertical_slice(tmp_path: Path):
    (tmp_path / ".complexity").mkdir()
    (tmp_path / ".complexity/config.json").write_text(json.dumps({
        "cyclomatic_threshold": 3,
        "required_checks": ["pytest -q"],
    }))
    (tmp_path / ".complexity/architectural-memory.json").write_text(json.dumps({
        "schema_version": "architectural-memory-v1",
        "entries": [{
            "id": "MEM-TEST-001",
            "concept": "routing-policy",
            "status": "active",
            "summary": "Routing branches have repeatedly diverged.",
            "evidence": [{"path": "service.py", "note": "Repeated local policy."}],
            "decision": "Characterize behavior before consolidation.",
            "next_trigger": "The next routing branch requires shared-policy review.",
        }],
    }))
    (tmp_path / "service.py").write_text(
        "def choose(a, b):\n"
        "    if a and b:\n"
        "        return 1\n"
        "    if a:\n"
        "        return 2\n"
        "    return 3\n"
    )

    payload = scan_repository(tmp_path).as_dict()
    validate_snapshot(payload)
    assert payload["summary"] == {
        "files": 1,
        "functions": 1,
        "findings": 1,
        "architectural_memory_entries": 1,
    }
    job = build_refactor_job(payload, payload["findings"][0]["id"], executor="compress-cloud")
    assert job["scope"]["allowed_paths"] == ["service.py"]
    assert job["architectural_memory_ids"] == ["MEM-TEST-001"]
    assert job["policy"]["automatic_merge"] is False
    assert job["policy"]["production_deploy"] is False


def test_snapshot_diff_is_evidence_based():
    before = {
        "files": [{"path": "a.py", "sha256": "before"}],
        "findings": [{"id": "old"}],
    }
    after = {
        "files": [{"path": "a.py", "sha256": "after"}, {"path": "b.py", "sha256": "new"}],
        "findings": [{"id": "new"}],
    }
    delta = diff_snapshots(before, after)
    assert delta["files"] == {"added": ["b.py"], "removed": [], "changed": ["a.py"]}
    assert delta["findings"]["introduced"] == [{"id": "new"}]
    assert delta["findings"]["resolved"] == [{"id": "old"}]
