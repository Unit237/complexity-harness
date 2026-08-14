from __future__ import annotations

import ast
import hashlib
from pathlib import Path

from .models import BranchEvidence, FileMetric, FunctionMetric


class _BranchVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.branches: list[BranchEvidence] = []

    def _add(self, node: ast.AST, kind: str, contribution: int = 1) -> None:
        if contribution > 0:
            self.branches.append(BranchEvidence(kind, int(getattr(node, "lineno", 0)), contribution))

    def visit_If(self, node: ast.If) -> None:
        self._add(node, "if")
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._add(node, "conditional-expression")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        self._add(node, "for")
        self.generic_visit(node)

    visit_AsyncFor = visit_For

    def visit_While(self, node: ast.While) -> None:
        self._add(node, "while")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        self._add(node, "except")
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        self._add(node, "boolean-chain", len(node.values) - 1)
        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        self._add(node, "match-case", len(node.cases))
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        self._add(node, "comprehension-loop")
        for condition in node.ifs:
            self._add(condition, "comprehension-filter")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return

    visit_AsyncFunctionDef = visit_FunctionDef
    visit_Lambda = visit_FunctionDef


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[str] = []
        self.metrics: list[FunctionMetric] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        symbol = ".".join([*self.scope, node.name])
        visitor = _BranchVisitor()
        for statement in node.body:
            visitor.visit(statement)
        self.metrics.append(FunctionMetric(
            symbol=symbol,
            line=node.lineno,
            end_line=int(getattr(node, "end_lineno", node.lineno)),
            cyclomatic=1 + sum(row.contribution for row in visitor.branches),
            branches=tuple(visitor.branches),
        ))
        self.scope.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self.scope.pop()

    visit_AsyncFunctionDef = visit_FunctionDef


def analyze_python(path: Path, *, relative_path: str) -> FileMetric:
    data = path.read_bytes()
    source = data.decode("utf-8")
    lines = len(source.splitlines())
    try:
        tree = ast.parse(source, filename=relative_path)
    except SyntaxError as exc:
        return FileMetric(
            path=relative_path,
            language="python",
            sha256=hashlib.sha256(data).hexdigest(),
            lines=lines,
            parse_error=f"{exc.msg} at line {exc.lineno}",
        )
    collector = _FunctionCollector()
    collector.visit(tree)
    return FileMetric(
        path=relative_path,
        language="python",
        sha256=hashlib.sha256(data).hexdigest(),
        lines=lines,
        functions=tuple(sorted(collector.metrics, key=lambda row: (row.line, row.symbol))),
    )
