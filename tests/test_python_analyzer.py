from pathlib import Path

from complexity_harness.python_analyzer import analyze_python


def test_python_analyzer_reports_exact_branch_evidence():
    fixture = Path(__file__).parent / "fixtures" / "hotspot.py"
    metric = analyze_python(fixture, relative_path="hotspot.py")
    function = metric.functions[0]

    assert function.symbol == "route_request"
    assert function.cyclomatic == 9
    assert {row.kind for row in function.branches} >= {
        "if", "boolean-chain", "for", "except"
    }


def test_duplicate_nested_symbols_receive_stable_occurrences(tmp_path):
    source = tmp_path / "duplicate.py"
    source.write_text(
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

    metric = analyze_python(source, relative_path="duplicate.py")
    duplicates = [row for row in metric.functions if row.symbol == "outer.event_gen"]

    assert [row.occurrence for row in duplicates] == [1, 2]




import json
import pytest
MODERN=json.loads((Path(__file__).parent/"fixtures/python-modern-v1.json").read_text())

@pytest.mark.parametrize("case",MODERN,ids=lambda case:case["id"])
def test_modern_python_syntax_keeps_decisions_and_source_locations(case):
    from complexity_harness.python_analyzer import analyze_python_bytes
    metric=analyze_python_bytes(case["source"].encode(),relative_path=case["id"]+".py")
    assert not metric.parse_error,metric.parse_error
    assert sum(f.cyclomatic-1 for f in metric.functions)+sum(b.contribution for b in metric.unattributed_branches)==case["decisions"]
    assert all(1<=b.line<=metric.lines for f in metric.functions for b in f.branches)


def test_malformed_modern_syntax_is_unmeasured():
    from complexity_harness.python_analyzer import analyze_python_bytes
    invalid=analyze_python_bytes(b"def choose[T = ](x):\n return x\n",relative_path="broken.py")
    assert invalid.parse_error and not invalid.functions
