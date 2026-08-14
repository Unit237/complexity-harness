from __future__ import annotations

import json

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
