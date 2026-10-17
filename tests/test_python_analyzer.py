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


def test_python_grammar_is_pinned_across_supported_producer_runtimes():
    from complexity_harness.python_analyzer import analyze_python_bytes
    metric=analyze_python_bytes(b"type CustomerId = int\n",relative_path="newer_syntax.py")
    assert metric.parse_error and not metric.functions
