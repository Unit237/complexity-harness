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
