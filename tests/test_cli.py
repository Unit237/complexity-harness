from __future__ import annotations

import json
import subprocess
import sys

from complexity_harness.cli import main


def test_cli_scan_validate_and_health(tmp_path, capsys):
    (tmp_path / "simple.py").write_text("def ok():\n    return True\n")
    snapshot = tmp_path / "snapshot.json"

    assert main(["scan", str(tmp_path), "--output", str(snapshot)]) == 0
    assert main(["validate", str(snapshot)]) == 0
    assert main(["health", str(snapshot)]) == 0
    output = capsys.readouterr().out
    assert "complexity snapshot is valid" in output
    assert json.loads(snapshot.read_text())["schema_version"] == "complexity-snapshot-v1"


def test_source_scan_exits_after_using_the_javascript_runtime(tmp_path):
    (tmp_path / "app.js").write_text("function choose(x) { return x ? 1 : 0; }\n")
    snapshot = tmp_path / "snapshot.json"

    result = subprocess.run(
        [sys.executable, "-m", "complexity_harness.cli", "scan", str(tmp_path),
         "--output", str(snapshot)],
        capture_output=True, text=True, timeout=20,
    )

    assert result.returncode == 0, result.stderr
    metric = json.loads(snapshot.read_text())["files"][0]
    assert metric["parse_error"] is None
    assert metric["functions"][0]["cyclomatic"] == 2
