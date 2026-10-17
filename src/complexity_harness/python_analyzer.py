"""Runtime-independent Python syntax; repository code is parsed, never imported."""
from __future__ import annotations

from collections import Counter
import hashlib
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path

from .models import BranchEvidence, FileMetric, FunctionMetric


def analyze_python(path: Path, *, relative_path: str) -> FileMetric:
    return analyze_python_bytes(path.read_bytes(), relative_path=relative_path)


def analyze_python_bytes(data: bytes, *, relative_path: str) -> FileMetric:
    source = data.decode("utf-8")
    base = dict(path=relative_path, language="python", sha256=hashlib.sha256(data).hexdigest(),
                lines=len(source.splitlines()))
    try:
        import libcst as cst
        from libcst.metadata import MetadataWrapper, PositionProvider
        if version("libcst") != "1.9.0":
            raise ValueError("Python parser version differs from the analysis contract")
    except (ImportError, PackageNotFoundError, ValueError) as exc:
        return FileMetric(**base, parse_error=f"Python parser unavailable: {type(exc).__name__}")

    class Decisions(cst.CSTVisitor):
        METADATA_DEPENDENCIES = (PositionProvider,)

        def __init__(self):
            self.scope, self.owners, self.units, self.outside = [], [None], [], []
            self.occurrences = Counter()

        def add(self, node, kind):
            evidence = BranchEvidence(kind, self.get_metadata(PositionProvider, node).start.line)
            (self.owners[-1]["branches"] if self.owners[-1] is not None else self.outside).append(evidence)

        def visit_ClassDef(self, node):
            self.scope.append(node.name.value)

        def leave_ClassDef(self, node):
            self.scope.pop()

        def visit_FunctionDef(self, node):
            symbol = ".".join([*self.scope, node.name.value])
            self.scope.append(node.name.value)
            self.occurrences[symbol] += 1
            position = self.get_metadata(PositionProvider, node)
            self.units.append({"symbol":symbol,"occurrence":self.occurrences[symbol],
                "line":position.start.line,"end_line":position.end.line,"branches":[]})
            # Defaults, annotations and decorators belong to the source audit,
            # not to the function body; lambdas retain the same audit convention.
            self.owners.append(None)

        def visit_FunctionDef_body(self, node):
            self.owners[-1] = self.units[-1]

        def leave_FunctionDef_body(self, node):
            self.owners[-1] = None

        def leave_FunctionDef(self, node):
            self.owners.pop(); self.scope.pop()

        def visit_Lambda(self, node):
            self.owners.append(None)

        def leave_Lambda(self, node):
            self.owners.pop()

        def visit_If(self, node): self.add(node,"if")
        def visit_IfExp(self, node): self.add(node,"conditional-expression")
        def visit_For(self, node): self.add(node,"for")
        def visit_While(self, node): self.add(node,"while")
        def visit_ExceptHandler(self, node): self.add(node,"except")
        def visit_ExceptStarHandler(self, node): self.add(node,"except")
        def visit_BooleanOperation(self, node): self.add(node,"boolean-chain")
        def visit_CompFor(self, node): self.add(node,"comprehension-loop")
        def visit_CompIf(self, node): self.add(node,"comprehension-filter")

        def visit_MatchCase(self, node):
            self.add(node,"match-case")
            if node.guard is not None: self.add(node.guard,"match-guard")

    try:
        visitor = Decisions()
        MetadataWrapper(cst.parse_module(source), unsafe_skip_copy=True).visit(visitor)
    except (cst.ParserSyntaxError, RecursionError) as exc:
        return FileMetric(**base, parse_error=f"Python syntax not recognized: {type(exc).__name__}")
    metrics = tuple(FunctionMetric(unit["symbol"],unit["occurrence"],unit["line"],unit["end_line"],
        1+sum(b.contribution for b in unit["branches"]),tuple(unit["branches"])) for unit in visitor.units)
    return FileMetric(**base, functions=metrics, unattributed_branches=tuple(visitor.outside))
