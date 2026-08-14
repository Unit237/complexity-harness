from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from functools import cache
import hashlib
from pathlib import Path
from typing import Iterable

from tree_sitter import Language, Node, Parser

from .models import BranchEvidence, FileMetric, FunctionMetric


@dataclass(frozen=True)
class _Profile:
    language: str
    grammar: str
    branch_types: dict[str, str]
    boolean_types: frozenset[str] = frozenset()
    boolean_operators: frozenset[str] = frozenset({"&&", "||"})
    function_types: frozenset[str] = frozenset()


_JAVASCRIPT_FUNCTIONS = frozenset({
    "arrow_function",
    "function_declaration",
    "function_expression",
    "generator_function",
    "generator_function_declaration",
    "method_definition",
})

_JAVASCRIPT_BRANCHES = {
    "catch_clause": "catch",
    "do_statement": "do-while",
    "for_in_statement": "for-in",
    "for_statement": "for",
    "if_statement": "if",
    "switch_case": "switch-case",
    "switch_default": "switch-default",
    "ternary_expression": "conditional-expression",
    "while_statement": "while",
}

_PROFILES = {
    ".js": _Profile(
        "javascript",
        "javascript",
        _JAVASCRIPT_BRANCHES,
        frozenset({"binary_expression"}),
        frozenset({"&&", "||", "??"}),
        _JAVASCRIPT_FUNCTIONS,
    ),
    ".jsx": _Profile(
        "jsx",
        "javascript",
        _JAVASCRIPT_BRANCHES,
        frozenset({"binary_expression"}),
        frozenset({"&&", "||", "??"}),
        _JAVASCRIPT_FUNCTIONS,
    ),
    ".ts": _Profile(
        "typescript",
        "typescript",
        _JAVASCRIPT_BRANCHES,
        frozenset({"binary_expression"}),
        frozenset({"&&", "||", "??"}),
        _JAVASCRIPT_FUNCTIONS,
    ),
    ".tsx": _Profile(
        "tsx",
        "tsx",
        _JAVASCRIPT_BRANCHES,
        frozenset({"binary_expression"}),
        frozenset({"&&", "||", "??"}),
        _JAVASCRIPT_FUNCTIONS,
    ),
    ".dart": _Profile(
        "dart",
        "dart",
        {
            "catch_clause": "catch",
            "conditional_expression": "conditional-expression",
            "do_statement": "do-while",
            "for_statement": "for",
            "if_statement": "if",
            "switch_expression_case": "switch-case",
            "switch_statement_case": "switch-case",
            "switch_statement_default": "switch-default",
            "while_statement": "while",
        },
        frozenset({"logical_and_expression", "logical_or_expression"}),
        frozenset({"logical_and_operator", "logical_or_operator"}),
        frozenset({"function_body", "function_expression"}),
    ),
    ".tf": _Profile(
        "terraform",
        "hcl",
        {
            "conditional": "conditional-expression",
            "for_cond": "comprehension-filter",
            "for_expr": "comprehension-loop",
        },
        frozenset({"binary_operation"}),
    ),
    ".hcl": _Profile(
        "hcl",
        "hcl",
        {
            "conditional": "conditional-expression",
            "for_cond": "comprehension-filter",
            "for_expr": "comprehension-loop",
        },
        frozenset({"binary_operation"}),
    ),
    ".sh": _Profile(
        "shell",
        "bash",
        {
            "case_item": "case-item",
            "elif_clause": "elif",
            "for_statement": "for",
            "if_statement": "if",
            "while_statement": "while",
        },
        frozenset({"binary_expression", "list"}),
        frozenset({"&&", "||"}),
        frozenset({"function_definition"}),
    ),
}

SUPPORTED_SUFFIXES = frozenset(_PROFILES)


@cache
def _language(grammar: str) -> Language:
    if grammar == "javascript":
        import tree_sitter_javascript

        capsule = tree_sitter_javascript.language()
    elif grammar == "typescript":
        import tree_sitter_typescript

        capsule = tree_sitter_typescript.language_typescript()
    elif grammar == "tsx":
        import tree_sitter_typescript

        capsule = tree_sitter_typescript.language_tsx()
    elif grammar == "dart":
        import tree_sitter_dart

        capsule = tree_sitter_dart.language()
    elif grammar == "hcl":
        import tree_sitter_hcl

        capsule = tree_sitter_hcl.language()
    elif grammar == "bash":
        import tree_sitter_bash

        capsule = tree_sitter_bash.language()
    else:  # pragma: no cover - profiles are defined above
        raise ValueError(f"unsupported grammar: {grammar}")
    return Language(capsule)


def _node_text(node: Node, data: bytes) -> str:
    return data[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _name_field(node: Node | None, data: bytes) -> str | None:
    if node is None:
        return None
    name = node.child_by_field_name("name")
    if name is not None:
        return _node_text(name, data)
    for child in node.named_children:
        nested = _name_field(child, data)
        if nested:
            return nested
    return None


def _direct_name(node: Node, data: bytes) -> str | None:
    name = node.child_by_field_name("name")
    return _node_text(name, data) if name is not None else None


def _name_before(node: Node, parent: Node, data: bytes) -> str | None:
    for field in ("name", "key", "left"):
        candidate = parent.child_by_field_name(field)
        if candidate is not None and candidate.end_byte <= node.start_byte:
            return _node_text(candidate, data)
    identifiers = [
        child for child in _walk(parent)
        if child.type in {"identifier", "property_identifier"}
        and child.end_byte <= node.start_byte
    ]
    return _node_text(identifiers[-1], data) if identifiers else None


def _assigned_name(node: Node, data: bytes) -> str | None:
    parent = node.parent
    while parent is not None and parent.type not in {
        "class_body", "program", "statement_block", "function_body",
    }:
        if parent.type in {
            "assignment_expression", "pair", "public_field_definition",
            "static_final_declaration", "variable_declarator",
        }:
            name = _name_before(node, parent, data)
            if name:
                return name
        parent = parent.parent
    return None


def _walk(node: Node) -> Iterable[Node]:
    yield node
    for child in node.named_children:
        yield from _walk(child)


def _branch_contribution(node: Node, profile: _Profile) -> tuple[str, int] | None:
    kind = profile.branch_types.get(node.type)
    if kind:
        return kind, 1
    if node.type not in profile.boolean_types:
        return None
    contribution = sum(
        child.type in profile.boolean_operators
        for child in node.children
    )
    if contribution:
        return "boolean-chain", contribution
    return None


def _branches(
    roots: Iterable[Node],
    profile: _Profile,
    *,
    skip_types: frozenset[str] = frozenset(),
) -> tuple[BranchEvidence, ...]:
    evidence: list[BranchEvidence] = []

    def visit(node: Node, *, root: bool = False) -> None:
        if not root and node.type in skip_types:
            return
        contribution = _branch_contribution(node, profile)
        if contribution:
            kind, amount = contribution
            evidence.append(BranchEvidence(kind, node.start_point[0] + 1, amount))
        for child in node.named_children:
            visit(child)

    for node in roots:
        visit(node, root=True)
    return tuple(evidence)


def _metric(
    symbol: str,
    node: Node,
    evidence: tuple[BranchEvidence, ...],
    occurrences: Counter[str],
    *,
    start_node: Node | None = None,
) -> FunctionMetric:
    occurrences[symbol] += 1
    definition = start_node or node
    return FunctionMetric(
        symbol=symbol,
        occurrence=occurrences[symbol],
        line=definition.start_point[0] + 1,
        end_line=node.end_point[0] + 1,
        cyclomatic=1 + sum(row.contribution for row in evidence),
        branches=evidence,
    )


def _javascript_metrics(
    root: Node,
    data: bytes,
    profile: _Profile,
) -> tuple[FunctionMetric, ...]:
    metrics: list[FunctionMetric] = []
    occurrences: Counter[str] = Counter()

    def collect(node: Node, scope: tuple[str, ...]) -> None:
        if node.type in {"class_declaration", "class_expression"}:
            local = _direct_name(node, data) or f"anonymous-class@{node.start_point[0] + 1}"
            for child in node.named_children:
                collect(child, (*scope, local))
            return
        if node.type in profile.function_types:
            local = (
                _direct_name(node, data)
                or _assigned_name(node, data)
                or f"anonymous@{node.start_point[0] + 1}"
            )
            symbol = ".".join((*scope, local))
            evidence = _branches(
                (node,), profile, skip_types=profile.function_types
            )
            metrics.append(_metric(symbol, node, evidence, occurrences))
            for child in node.named_children:
                collect(child, (*scope, local))
            return
        for child in node.named_children:
            collect(child, scope)

    collect(root, ())
    return tuple(sorted(metrics, key=lambda row: (row.line, row.symbol)))


def _dart_signature(body: Node) -> Node | None:
    signature = body.prev_named_sibling
    if signature is not None and signature.type in {"function_signature", "method_signature"}:
        return signature
    return None


def _dart_local_name(node: Node, data: bytes) -> str:
    if node.type == "function_body":
        signature = _dart_signature(node)
        name = _name_field(signature, data)
        if name:
            return name
        if signature is not None:
            identifiers = [
                child for child in _walk(signature)
                if child.type == "identifier"
            ]
            if identifiers:
                return _node_text(identifiers[-1], data)
    return _assigned_name(node, data) or f"anonymous@{node.start_point[0] + 1}"


def _dart_scope(node: Node, data: bytes) -> tuple[str, ...]:
    names: list[str] = []
    parent = node.parent
    while parent is not None:
        if parent.type == "class_definition":
            names.append(_name_field(parent, data) or "anonymous-class")
        elif parent.type in {"function_body", "function_expression"}:
            names.append(_dart_local_name(parent, data))
        parent = parent.parent
    return tuple(reversed(names))


def _dart_metrics(
    root: Node,
    data: bytes,
    profile: _Profile,
) -> tuple[FunctionMetric, ...]:
    metrics: list[FunctionMetric] = []
    occurrences: Counter[str] = Counter()
    for node in _walk(root):
        if node.type == "function_body" and _dart_signature(node) is None:
            continue
        if node.type not in profile.function_types:
            continue
        local = _dart_local_name(node, data)
        symbol = ".".join((*_dart_scope(node, data), local))
        evidence = _branches((node,), profile, skip_types=profile.function_types)
        metrics.append(_metric(
            symbol,
            node,
            evidence,
            occurrences,
            start_node=_dart_signature(node),
        ))
    return tuple(sorted(metrics, key=lambda row: (row.line, row.symbol)))


def _hcl_block_symbol(block: Node, data: bytes) -> str:
    parts: list[str] = []
    for child in block.named_children:
        if child.type == "identifier":
            parts.append(_node_text(child, data))
        elif child.type == "string_lit":
            parts.append(_node_text(child, data).strip('"'))
        elif child.type in {"block_start", "body"}:
            break
    return ".".join(parts) or f"block@{block.start_point[0] + 1}"


def _hcl_metrics(
    root: Node,
    data: bytes,
    profile: _Profile,
) -> tuple[FunctionMetric, ...]:
    body = next((child for child in root.named_children if child.type == "body"), None)
    if body is None:
        return ()
    metrics: list[FunctionMetric] = []
    occurrences: Counter[str] = Counter()
    attributes: list[Node] = []
    for node in body.named_children:
        if node.type == "block":
            evidence = _branches((node,), profile)
            metrics.append(_metric(
                _hcl_block_symbol(node, data), node, evidence, occurrences
            ))
        elif node.type == "attribute":
            attributes.append(node)
    if attributes:
        evidence = _branches(attributes, profile)
        metrics.append(_metric(
            "<module>", attributes[-1], evidence, occurrences,
            start_node=attributes[0],
        ))
    return tuple(sorted(metrics, key=lambda row: (row.line, row.symbol)))


def _shell_metrics(
    root: Node,
    data: bytes,
    profile: _Profile,
) -> tuple[FunctionMetric, ...]:
    metrics: list[FunctionMetric] = []
    occurrences: Counter[str] = Counter()
    script_evidence = _branches(
        (root,), profile, skip_types=profile.function_types
    )
    metrics.append(_metric("<script>", root, script_evidence, occurrences))
    for node in _walk(root):
        if node.type != "function_definition":
            continue
        symbol = _direct_name(node, data) or f"anonymous@{node.start_point[0] + 1}"
        evidence = _branches(
            (node,), profile, skip_types=profile.function_types
        )
        metrics.append(_metric(symbol, node, evidence, occurrences))
    return tuple(sorted(metrics, key=lambda row: (row.line, row.symbol)))


def _parse_error(root: Node) -> str | None:
    if not root.has_error:
        return None
    for node in _walk(root):
        if node.is_error or node.is_missing:
            return f"syntax error at line {node.start_point[0] + 1}"
    return "syntax error"


def analyze_tree_sitter(path: Path, *, relative_path: str) -> FileMetric:
    suffix = path.suffix.lower()
    try:
        profile = _PROFILES[suffix]
    except KeyError as exc:
        raise ValueError(f"unsupported source extension: {suffix}") from exc
    data = path.read_bytes()
    source = data.decode("utf-8", errors="replace")
    tree = Parser(_language(profile.grammar)).parse(data)
    root = tree.root_node
    if suffix in {".js", ".jsx", ".ts", ".tsx"}:
        functions = _javascript_metrics(root, data, profile)
    elif suffix == ".dart":
        functions = _dart_metrics(root, data, profile)
    elif suffix in {".tf", ".hcl"}:
        functions = _hcl_metrics(root, data, profile)
    else:
        functions = _shell_metrics(root, data, profile)
    return FileMetric(
        path=relative_path,
        language=profile.language,
        sha256=hashlib.sha256(data).hexdigest(),
        lines=len(source.splitlines()),
        functions=functions,
        parse_error=_parse_error(root),
    )
