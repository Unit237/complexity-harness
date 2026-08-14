from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from complexity_harness.cli import main
from complexity_harness.refactor import build_refactor_job
from complexity_harness.report import markdown_report
from complexity_harness.snapshot import validate_snapshot
from complexity_harness.workspace import scan_workspace


ROOT = Path(__file__).resolve().parents[1]


def _workspace(tmp_path: Path) -> Path:
    service = tmp_path / "service"
    service.mkdir()
    (service / ".complexity").mkdir()
    (service / ".complexity/config.json").write_text(json.dumps({
        "cyclomatic_threshold": 2,
        "required_checks": ["pytest -q"],
    }))
    (service / "service.py").write_text(
        "def outer():\n"
        "    def event_gen(value):\n"
        "        if value:\n"
        "            return 1\n"
        "        return 0\n"
        "    def event_gen(value):\n"
        "        if value:\n"
        "            return 2\n"
        "        return 0\n"
    )
    generated = service / ".build"
    generated.mkdir()
    (generated / "copied.py").write_text("def copied():\n    return True\n")

    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.ts").write_text("export const ok = true\n")

    architecture = tmp_path / "architecture"
    architecture.mkdir()
    (architecture / "repositories.json").write_text(json.dumps({
        "schema_version": "software-repositories-v1",
        "repositories": [
            {"id": "service", "name": "Service", "path": "service", "status": "canonical", "kind": "product"},
            {"id": "frontend", "name": "Frontend", "path": "frontend", "status": "canonical", "kind": "website"},
        ],
        "aliases": [{"path": "service-copy", "canonical_repository_id": "service"}],
        "excluded_paths": ["service/.build/**"],
    }))
    (architecture / "architectural-memory.json").write_text(json.dumps({
        "schema_version": "architectural-memory-v1",
        "entries": [{
            "id": "MEM-SERVICE-001",
            "concept": "service-routing",
            "status": "active",
            "summary": "Repeated routing branches need characterization.",
            "evidence": [{"path": "service/service.py", "note": "The hotspot."}],
            "decision": "Preserve behavior before simplifying.",
            "next_trigger": "The next routing change.",
        }],
    }))
    (architecture / "invariants.json").write_text(json.dumps({
        "schema_version": "software-invariants-v1",
        "invariants": [{
            "id": "INV-SERVICE-001",
            "name": "Service routing preserves observable behavior",
            "owner": "service",
            "version": "service-routing-v1",
            "contract": "service/contracts/routing.json",
            "status": "enforced",
            "manifestations": [{"system": "service", "path": "service/service.py", "role": "owner"}],
            "exceptions": [],
            "conformance_tests": ["service/tests/test_routing.py"],
        }],
    }))
    return tmp_path


def test_workspace_scan_uses_inventory_exclusions_memory_and_unique_ids(tmp_path):
    root = _workspace(tmp_path)

    payload = scan_workspace(root)
    validate_snapshot(payload)
    workspace_schema = json.loads(
        (ROOT / "contracts/complexity-workspace-snapshot-v1.schema.json").read_text()
    )
    inventory_schema = json.loads(
        (ROOT / "contracts/repository-inventory-v1.schema.json").read_text()
    )
    Draft202012Validator(workspace_schema).validate(payload)
    Draft202012Validator(inventory_schema).validate(
        json.loads((root / "architecture/repositories.json").read_text())
    )

    assert payload["summary"] == {
        "repositories": 2,
        "files": 1,
        "functions": 3,
        "findings": 2,
        "architectural_memory_entries": 1,
        "registered_invariants": 1,
    }
    assert [row["path"] for row in payload["files"]] == ["service/service.py"]
    assert len({row["id"] for row in payload["findings"]}) == 2
    assert len({row["local_id"] for row in payload["findings"]}) == 2
    assert {row["factors"]["definition_occurrence"] for row in payload["findings"]} == {1, 2}
    service = next(row for row in payload["repositories"] if row["id"] == "service")
    assert service["summary"]["architectural_memory_entries"] == 1
    assert service["summary"]["registered_invariants"] == 1

    job = build_refactor_job(payload, payload["findings"][0]["id"], executor="codex")
    assert job["readiness"] == {"status": "ready", "blockers": []}
    assert job["verification"]["required_checks"] == ["pytest -q"]
    assert job["architectural_memory_ids"] == ["MEM-SERVICE-001"]
    assert job["registered_invariant_ids"] == ["INV-SERVICE-001"]
    assert "do not merge or deploy" in job["agent_prompt"].lower()

    with pytest.raises(ValueError, match="cannot cross canonical repositories"):
        build_refactor_job(
            payload,
            payload["findings"][0]["id"],
            allowed_paths=["frontend/index.ts"],
        )

    report = markdown_report(payload, top=1)
    assert "# Complexity report" in report
    assert "| Service | 1 | 3 | 2 | 1 | 1 |" in report


def test_workspace_cli_report_and_agent_prompt(tmp_path, capsys):
    root = _workspace(tmp_path)
    snapshot = tmp_path / "workspace-snapshot.json"
    report = tmp_path / "report.md"

    assert main(["workspace-scan", str(root), "--output", str(snapshot)]) == 0
    assert main(["validate", str(snapshot)]) == 0
    assert main(["report", str(snapshot), "--top", "1", "--output", str(report)]) == 0
    payload = json.loads(snapshot.read_text())
    job_path = tmp_path / "job.json"
    assert main([
        "refactor-job",
        str(snapshot),
        payload["findings"][0]["id"],
        "--output",
        str(job_path),
    ]) == 0
    assert main(["agent-prompt", str(job_path)]) == 0

    output = capsys.readouterr().out
    assert "complexity snapshot is valid" in output
    assert "Execute bounded complexity refactor job" in output
    assert "Top 1 investigation candidates" in report.read_text()
