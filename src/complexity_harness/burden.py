"""Versioned, explainable control-flow burden. Copied unchanged into consumers.

This index describes measured control flow, not universal maintainability or
semantic duplication. Missing languages never receive a zero complexity value.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import PurePosixPath
import re


VERSION = "complexity-burden-v1"
ANALYZER = "python-ast-cyclomatic-v2"
POLICY = {
    "version": VERSION,
    "analyzer": ANALYZER,
    "decision_ceiling": 24,
    "mean_weight": 0.6,
    "tail_weight": 0.4,
    "tail_fraction": 0.1,
    "target": 35,
    "bands": [
        {"minimum": 0, "label": "Low"},
        {"minimum": 20, "label": "Moderate"},
        {"minimum": 40, "label": "Elevated"},
        {"minimum": 60, "label": "High"},
        {"minimum": 80, "label": "Very high"},
    ],
    "formula": "100 × (0.6 × mean function load + 0.4 × mean highest-decile load); function load = min((cyclomatic − 1) / 24, 1)",
    "product_aggregation": "Highest measured repository burden; adding lower-burden code in another repository cannot dilute the product score.",
    "meaning": "Measured Python control-flow burden; not a product readiness percentage.",
    "reduction_audit": "Counts all recognized Python branch decisions, including lambdas and module-level control flow, so moving decisions outside named functions cannot earn credit.",
    "reduction_requires": ["comparable_complete_scan", "fewer_decisions", "exact_revision_behavior_checks", "merged_source"],
}


def level(score):
    if score is None:
        return "Unmeasured"
    return next(band["label"] for band in reversed(POLICY["bands"]) if score >= band["minimum"])


def score_values(values):
    if not values:
        return None
    loads = sorted((min((value - 1) / POLICY["decision_ceiling"], 1) for value in values), reverse=True)
    tail = loads[:max(1, math.ceil(len(loads) * POLICY["tail_fraction"]))]
    return round(100 * (POLICY["mean_weight"] * sum(loads) / len(loads)
                        + POLICY["tail_weight"] * sum(tail) / len(tail)), 2)


def score_repositories(scores):
    """A monotone product index: repository population shifts cannot earn credit."""
    measured = [score for score in scores if score is not None]
    return max(measured) if measured else None


def _path(value):
    if not isinstance(value, str) or not value or len(value) > 500 or "\\" in value:
        raise ValueError("Source paths must be safe relative paths")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or str(path) != value:
        raise ValueError("Source paths must be safe relative paths")
    return value


def measure_snapshot(snapshot):
    """Recompute from branch evidence; never trust producer-supplied scores."""
    if snapshot.get("schema_version") != "complexity-snapshot-v1":
        raise ValueError("A repository Complexity Harness snapshot is required")
    source = snapshot.get("repository") or {}
    coverage = snapshot.get("coverage") or {}
    if coverage.get("inventory_complete") is not True:
        raise ValueError("A complete eligible source inventory is required before publishing a baseline")
    if coverage.get("analyzer") != ANALYZER or not re.fullmatch(r"[0-9a-f]{64}", coverage.get("scope_hash", "")):
        raise ValueError("A versioned analyzer and exclusion policy are required")
    if source.get("clean") is not True or not re.fullmatch(r"[0-9a-f]{40}", source.get("commit") or ""):
        raise ValueError("Measurements require a clean, commit-bound source tree")
    rows = snapshot.get("files")
    unsupported = coverage.get("unsupported_paths")
    if not isinstance(rows, list) or not isinstance(unsupported, list) or len(rows) + len(unsupported) > 20000:
        raise ValueError("A bounded eligible source inventory is required")
    unknown = [_path(path) for path in unsupported]
    unknown_hashes = coverage.get("unsupported_hashes") or {}
    if any(not re.fullmatch(r"[0-9a-f]{64}", unknown_hashes.get(path, "")) for path in unknown):
        raise ValueError("Unmeasured source needs hashes to detect displaced complexity")
    seen = set(unknown)
    if len(seen) != len(unknown):
        raise ValueError("Eligible source paths must be unique")
    if "eligible_files" in coverage and coverage["eligible_files"] != len(rows) + len(unknown):
        raise ValueError("Every eligible source file must be accounted for")
    files, values, findings = [], [], []
    errors = []
    for row in rows:
        path = _path(row.get("path"))
        if path in seen or row.get("language") != "python" or not path.endswith(".py"):
            raise ValueError("Measured Python paths must be unique and typed")
        seen.add(path)
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256") or ""):
            raise ValueError("Every measured file needs a content hash")
        if row.get("parse_error"):
            errors.append(path)
            continue
        outside = row.get("unattributed_branches")
        if (not isinstance(outside, (list, tuple)) or len(outside) > 100000
                or type(row.get("lines")) is not int or row["lines"] < 0):
            raise ValueError("A complete audit of branches outside named functions is required")
        outside_decisions = 0
        for branch in outside:
            contribution = branch.get("contribution", 1)
            if (type(contribution) is not int or contribution < 1 or type(branch.get("line")) is not int
                    or not 1 <= branch["line"] <= row.get("lines", 0) or not isinstance(branch.get("kind"), str)):
                raise ValueError("Unattributed branch evidence must lie inside its source file")
            outside_decisions += contribution
        functions = row.get("functions")
        if not isinstance(functions, (list, tuple)) or len(functions) > 10000:
            raise ValueError("A bounded function inventory is required")
        local = []
        for function in functions:
            value = function.get("cyclomatic")
            line, end = function.get("line"), function.get("end_line")
            branches = function.get("branches")
            if (type(value) is not int or not 1 <= value <= 100000 or type(line) is not int
                    or type(end) is not int or not 1 <= line <= end or not isinstance(branches, (list, tuple))
                    or not isinstance(function.get("symbol"), str) or not function["symbol"]):
                raise ValueError("Function measurements need valid symbols, spans and complexity")
            total = 0
            for branch in branches:
                contribution = branch.get("contribution", 1)
                if (type(contribution) is not int or contribution < 1 or type(branch.get("line")) is not int
                        or not line <= branch["line"] <= end or not isinstance(branch.get("kind"), str)):
                    raise ValueError("Branch evidence must lie inside its function")
                total += contribution
            if total + 1 != value:
                raise ValueError("Cyclomatic complexity must reconstruct from branch evidence")
            local.append(value)
            if value >= 15:
                identity = hashlib.sha256(f"{path}:{function['symbol']}:{function.get('occurrence', 0)}".encode()).hexdigest()[:16]
                findings.append({"id": "CYC-" + identity, "path": path, "symbol": function["symbol"],
                    "line": line, "end_line": end, "cyclomatic": value,
                    "branches": branches[:100], "branch_count": len(branches),
                    "explanation": "Independent control-flow decisions warrant investigation; this is not proof of a defect."})
        values.extend(local)
        if len(values) > 100000:
            raise ValueError("Function inventory exceeds the bounded snapshot limit")
        files.append({"path": path, "sha256": row["sha256"], "lines": row.get("lines", 0),
            "functions": len(local), "decisions": sum(v - 1 for v in local) + outside_decisions,
            "unattributed_decisions": outside_decisions,
            "max_cyclomatic": max(local, default=0), "score": score_values(local),
            "hotspots": sum(v >= 15 for v in local), "values": local})
    score = score_values(values)
    eligible = len(seen)
    return {"version": VERSION, "analyzer": ANALYZER, "source_sha": source["commit"],
        "scope_hash": coverage["scope_hash"], "score": score, "level": level(score),
        "coverage": {"eligible_files": eligible, "analyzed_files": len(files),
            "unsupported_paths": unknown, "unsupported_hashes": unknown_hashes, "parse_error_paths": errors,
            "percent": round(100 * len(files) / eligible, 2) if eligible else 0,
            "complete": bool(eligible) and not unknown and not errors,
            "measured_languages": ["Python"] if files else []},
        "summary": {"functions": len(values), "decisions": sum(file["decisions"] for file in files),
            "hotspots": sum(v >= 15 for v in values), "very_high": sum(v >= 40 for v in values),
            "max_cyclomatic": max(values, default=0)},
        "files": files, "findings": sorted(findings, key=lambda f: (-f["cyclomatic"], f["path"], f["line"])),
        "policy": POLICY}


def reduction_evidence(before, after):
    """Necessary numerical conditions; the consumer must also verify delivery."""
    reasons = []
    if before["version"] != after["version"] or before["analyzer"] != after["analyzer"] or before["scope_hash"] != after["scope_hash"]:
        reasons.append("The measurement policy or exclusions changed")
    if before["coverage"]["parse_error_paths"] or after["coverage"]["parse_error_paths"]:
        reasons.append("Source parse errors prevent a comparable reduction")
    if set(before["coverage"]["unsupported_paths"]) != set(after["coverage"]["unsupported_paths"]):
        reasons.append("Unmeasured source scope changed")
    elif before["coverage"].get("unsupported_hashes", {}) != after["coverage"].get("unsupported_hashes", {}):
        reasons.append("Changed unmeasured source could conceal displaced complexity")
    old = {row["path"]: row for row in before["files"]}
    new = {row["path"]: row for row in after["files"]}
    changed = sorted(path for path in old.keys() | new.keys()
                     if path not in old or path not in new or old[path]["sha256"] != new[path]["sha256"])
    if not changed or before["source_sha"] == after["source_sha"]:
        reasons.append("A reduction needs changed source at a new revision")
    if after["summary"]["decisions"] >= before["summary"]["decisions"]:
        reasons.append("Control-flow decisions were not removed across the measured scope")
    return {"comparable": not reasons, "reasons": reasons, "changed_paths": changed,
        "decisions_removed": before["summary"]["decisions"] - after["summary"]["decisions"]}
