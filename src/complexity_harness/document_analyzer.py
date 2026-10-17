"""Syntax-aware diagnostics for CSS and OpenStep project documents."""
from importlib.metadata import version

from .models import BranchEvidence, FileMetric, FunctionMetric


def analyze_document(data, base, language):
    try:
        text = data.decode("utf-8-sig")
        if language == "css":
            import tinycss2
            if version("tinycss2") != "1.5.1":
                raise ValueError("CSS parser differs from the analysis contract")
            roots = tinycss2.parse_component_value_list(text, skip_comments=True)
            stack = [(node, 0) for node in reversed(roots)]
        else:
            from openstep_parser import OpenStepDecoder
            if version("openstep-parser") != "2.0.3":
                raise ValueError("OpenStep parser differs from the analysis contract")
            stack = [(OpenStepDecoder.ParseFromString(text), 0)]
        branches, containers, max_depth = [], 0, 0
        while stack:
            node, depth = stack.pop()
            if language == "css":
                if node.type == "error":
                    raise ValueError("Invalid CSS token")
                children = getattr(node, "content", None) or getattr(node, "arguments", None) or []
                container = node.type == "{} block"
                child_count = sum(child.type == "{} block" for child in children)
                line = node.source_line
            else:
                children = list(node.values()) if isinstance(node, dict) else node if isinstance(node, list) else []
                container = isinstance(node, (dict, list))
                child_count = sum(isinstance(child, (dict, list)) for child in children)
                line = 1  # OpenStep exposes document structure, not token locations.
            if container:
                depth += 1
                containers += 1
                max_depth = max(max_depth, depth)
                if depth > 3:
                    branches.append(BranchEvidence("nesting-excess", line, depth-3))
                if child_count > 8:
                    branches.append(BranchEvidence("fanout-excess", line, child_count-8))
            stack.extend((child, depth) for child in reversed(children))
        unit = FunctionMetric("<document>", 1, 1, max(1, base["lines"]),
            1+sum(b.contribution for b in branches), tuple(branches))
        return FileMetric(**base, functions=(unit,), structural={"containers":containers,"max_depth":max_depth,
            "nesting_points":sum(b.contribution for b in branches if b.kind=="nesting-excess"),
            "fanout_points":sum(b.contribution for b in branches if b.kind=="fanout-excess")})
    except Exception as exc:
        return FileMetric(**base, parse_error=f"Document analysis unavailable: {type(exc).__name__}")
