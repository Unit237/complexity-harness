from __future__ import annotations

from pathlib import Path

import pytest

from complexity_harness.tree_sitter_analyzer import analyze_tree_sitter


def _analyze(tmp_path: Path, name: str, source: str):
    path = tmp_path / name
    path.write_text(source)
    return analyze_tree_sitter(path, relative_path=name)


@pytest.mark.parametrize(
    ("name", "language"),
    [
        ("source.js", "javascript"),
        ("source.jsx", "jsx"),
        ("source.ts", "typescript"),
        ("source.tsx", "tsx"),
    ],
)
def test_javascript_family_reports_function_complexity(tmp_path, name, language):
    metric = _analyze(
        tmp_path,
        name,
        "function route(x, y, z) {\n"
        "  if (x && y || z) {\n"
        "    for (const item of y) console.log(item)\n"
        "  }\n"
        "  try { work() } catch (error) { recover(error) }\n"
        "  switch (x) { case 1: work(); break; case 2: break; default: break }\n"
        "  return x ? y : z\n"
        "}\n",
    )

    function = metric.functions[0]
    assert metric.language == language
    assert metric.parse_error is None
    assert function.symbol == "route"
    assert function.cyclomatic == 10
    assert {branch.kind for branch in function.branches} >= {
        "boolean-chain", "catch", "conditional-expression", "for-in", "if",
        "switch-case", "switch-default",
    }


def test_tsx_arrow_function_uses_assigned_symbol(tmp_path):
    metric = _analyze(
        tmp_path,
        "view.tsx",
        "const View = ({ok}: Props) => <main>{ok ? <Ready /> : <Wait />}</main>\n",
    )

    assert metric.functions[0].symbol == "View"
    assert metric.functions[0].cyclomatic == 2


def test_dart_reports_methods_and_exact_branch_evidence(tmp_path):
    metric = _analyze(
        tmp_path,
        "service.dart",
        "class Service {\n"
        "  int route(bool a, bool b) {\n"
        "    if (a && b) return 1;\n"
        "    try { return a ? 2 : 3; } catch (error) { return 0; }\n"
        "  }\n"
        "}\n"
        "int choose(int value) => switch (value) { 1 => 10, _ => 0 };\n",
    )

    function = metric.functions[0]
    assert metric.language == "dart"
    assert metric.parse_error is None
    assert function.symbol == "Service.route"
    assert function.cyclomatic == 5
    assert {branch.kind for branch in function.branches} == {
        "boolean-chain", "catch", "conditional-expression", "if",
    }
    assert metric.functions[1].symbol == "choose"
    assert metric.functions[1].cyclomatic == 3


@pytest.mark.parametrize(("name", "language"), [("main.tf", "terraform"), ("main.hcl", "hcl")])
def test_hcl_reports_top_level_blocks_as_complexity_scopes(tmp_path, name, language):
    metric = _analyze(
        tmp_path,
        name,
        'resource "service" "api" {\n'
        "  count = var.enabled ? 1 : 0\n"
        "  values = [for value in var.values : value if value.enabled]\n"
        "}\n",
    )

    scope = metric.functions[0]
    assert metric.language == language
    assert metric.parse_error is None
    assert scope.symbol == "resource.service.api"
    assert scope.cyclomatic == 4
    assert {branch.kind for branch in scope.branches} == {
        "comprehension-filter", "comprehension-loop", "conditional-expression",
    }


def test_shell_reports_script_and_function_complexity_separately(tmp_path):
    metric = _analyze(
        tmp_path,
        "release.sh",
        "deploy() {\n"
        "  if [[ -n a && -n b ]]; then\n"
        "    for item in a b; do while test x; do break; done; done\n"
        "  elif test c; then echo c; fi\n"
        "}\n"
        "if test top; then echo yes; fi\n",
    )

    functions = {row.symbol: row for row in metric.functions}
    assert metric.language == "shell"
    assert metric.parse_error is None
    assert functions["<script>"].cyclomatic == 2
    assert functions["deploy"].cyclomatic == 6
    assert {branch.kind for branch in functions["deploy"].branches} >= {
        "boolean-chain", "elif", "for", "if", "while",
    }
