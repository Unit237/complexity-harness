"""Versioned, explainable code burden. Copied unchanged into consumers.

This index describes measured control flow, with declarative diagnostics, not
universal maintainability or semantic duplication. Missing languages never receive a zero complexity value.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import PurePosixPath
import re
from .complexity_languages import classify_path


VERSION = "complexity-burden-v3"
ANALYZER = "polyglot-ast-v2/pack-0.13.0/ts-0.25.2"
# This is the admission contract, not a claim that every available grammar has
# a validated complexity adapter. Native parser dependencies stay in producers.
CONTROL_LANGUAGES = {"python", "javascript", "typescript", "tsx", "c", "cpp", "csharp", "java", "go", "rust", "ruby", "php", "kotlin", "swift", "dart", "bash", "lua"}
STRUCTURAL_LANGUAGES = {"hcl", "sql", "css", "json", "yaml", "html", "dockerfile", "make", "toml", "xml", "graphql"}
POLICY = {
    "version": VERSION,
    "analyzer": ANALYZER,
    "python_grammar": "3.11 (pinned across producer runtimes; newer syntax remains unmeasured)",
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
    "meaning": "Measured control-flow burden, 0–100, higher is worse. This is an index of explicit decisions, not a probability of defects or total engineering difficulty. Declarative structure is diagnostic evidence only and never sets this score. Unsupported source stays unknown.",
    "calibration": "Fixed reference anchors, not population percentiles: a repository of functions with 0, 5, 14 or 24 decisions scores 0, 20.83, 58.33 or 100. Bands and the target are investigation thresholds, not empirically proven quality grades. Nesting and domain necessity require source review.",
    "anchors": [{"decisions": 0, "score": 0}, {"decisions": 5, "score": 20.83}, {"decisions": 14, "score": 58.33}, {"decisions": 24, "score": 100}],
    "reduction_audit": "Counts recognized decisions in every function, closure and module. A lower score alone is insufficient: total control-flow decisions must fall, structural diagnostic points cannot increase, and changed unknown, data or excluded source blocks credit.",
    "structural_formula": "Diagnostic only: record container count, maximum nesting, excess levels beyond 3 and child containers beyond 8. These are not control-flow decisions and have no calibrated 0–100 score. Document-only repositories remain unmeasured on the main complexity map.",
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
    inventory = coverage.get("inventory")
    if coverage.get("inventory_policy") != "all-files-v2" or not isinstance(inventory,list) or len(inventory)>50000:
        raise ValueError("A complete, versioned all-file inventory is required")
    inventory_by_path = {}
    for entry in inventory:
        path = _path(entry.get("path"))
        if path in inventory_by_path or not re.fullmatch(r"[0-9a-f]{64}",entry.get("sha256", "")):
            raise ValueError("Inventory paths must be unique and fingerprinted")
        classification = classify_path(path)
        if entry.get("kind") != "excluded" and (entry.get("kind") != classification["kind"] or entry.get("language") != classification["language"]):
            raise ValueError("File classification must match the versioned inventory policy")
        inventory_by_path[path] = entry
    expected = {p for p,e in inventory_by_path.items() if e["kind"] in {"source","unknown","opaque"}}
    if expected != seen | {row.get("path") for row in rows}:
        raise ValueError("Every eligible file must be accounted for in the full inventory")
    if any(inventory_by_path[p]["sha256"] != unknown_hashes[p] for p in unknown):
        raise ValueError("Unknown source fingerprints must match the inventory")
    files, values, findings = [], [], []
    factors, language_counts = {}, {}
    for entry in inventory:
        if entry["path"] in expected:
            language_counts.setdefault(entry["language"], {"language":entry["language"],"eligible_files":0,"analyzed_files":0,"support":"unsupported", "metric_family":"control_flow" if entry["language"] in CONTROL_LANGUAGES else "structure" if entry["language"] in STRUCTURAL_LANGUAGES else "unknown"})["eligible_files"] += 1
    errors, error_reasons = [], {}
    for row in rows:
        path = _path(row.get("path"))
        if path in seen or row.get("language") not in CONTROL_LANGUAGES | STRUCTURAL_LANGUAGES or row.get("language") != inventory_by_path[path]["language"]:
            raise ValueError("Measured source paths must be unique and correctly typed")
        seen.add(path)
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256") or ""):
            raise ValueError("Every measured file needs a content hash")
        if row.get("parse_error"):
            errors.append(path)
            error_reasons[path] = str(row["parse_error"])[:300]
            continue
        family = "structure" if row["language"] in STRUCTURAL_LANGUAGES else "control_flow"
        if row.get("metric_family","control_flow") != family:
            raise ValueError("A language must use its declared metric family")
        language_counts[row["language"]]["analyzed_files"] += 1
        language_counts[row["language"]]["support"] = "measured"
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
                    or type(end) is not int or not 1 <= line <= end <= max(1,row["lines"]) or not isinstance(branches, (list, tuple))
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
                    "branches": branches[:100], "branch_count": len(branches), "language":row["language"],"metric_family":family,
                    "explanation": "Excess nesting or fan-out warrants structural investigation." if family=="structure" else "Independent control-flow decisions warrant investigation; this is not proof of a defect."})
        if outside_decisions:
            local.append(outside_decisions+1)
        if family == "control_flow":
            values.extend(local)
        factor = factors.setdefault(family,{"values":[],"decisions":0,"files":0})
        factor["values"].extend(local)
        factor["decisions"] += sum(v-1 for v in local)
        factor["files"] += 1
        if len(values) > 100000:
            raise ValueError("Function inventory exceeds the bounded snapshot limit")
        files.append({"path": path, "sha256": row["sha256"], "lines": row.get("lines", 0),
            "language":row["language"],"metric_family":family,"structural":row.get("structural",{}),
            "functions": len(local), "decisions": sum(v - 1 for v in local),
            "unattributed_decisions": outside_decisions,
            "max_cyclomatic": max(local, default=0), "score": score_values(local) if family == "control_flow" else None,
            "hotspots": sum(v >= 15 for v in local), "values": local})
    for family, factor in factors.items():
        local = factor.pop("values")
        factor["score"] = score_values(local) if family == "control_flow" else None
        factor["status"] = "scored" if family == "control_flow" else "diagnostic_only"
    score = factors.get("control_flow", {}).get("score")
    for language in language_counts.values():
        language["support"] = "measured" if language["analyzed_files"]==language["eligible_files"] else "partial" if language["analyzed_files"] else "unsupported"
    eligible = len(seen)
    scored_files = sum(file["metric_family"] == "control_flow" for file in files)
    diagnostic_files = len(files) - scored_files
    score_eligible_files = sum(row["eligible_files"] for row in language_counts.values() if row["metric_family"] != "structure")
    return {"version": VERSION, "analyzer": ANALYZER, "source_sha": source["commit"],
        "scope_hash": coverage["scope_hash"], "score": score, "level": level(score),
        "coverage": {"eligible_files": eligible, "analyzed_files": len(files),
            "scored_files":scored_files,"diagnostic_files":diagnostic_files,"score_eligible_files":score_eligible_files,
            "score_percent":round(100 * scored_files / score_eligible_files, 2) if score_eligible_files else None,
            "unsupported_paths": unknown, "unsupported_hashes": unknown_hashes, "parse_error_paths": errors,
            "percent": round(100 * len(files) / eligible, 2) if eligible else 0,
            "complete": bool(eligible) and not unknown and not errors,
            "measured_languages": sorted({row["language"] for row in files}),
            "languages":sorted(language_counts.values(),key=lambda row:row["language"]),
            "inventory_files":len(inventory),"inventory_counts":{kind:sum(e["kind"]==kind for e in inventory) for kind in sorted({e["kind"] for e in inventory})},
            "unmeasured": [{"path":p,"language":inventory_by_path[p]["language"],"reason":error_reasons.get(p) or inventory_by_path[p].get("reason") or "Parser or dialect unavailable"} for p in unknown+errors],
            "excluded_fingerprint":hashlib.sha256(json.dumps(sorted((p,e["sha256"]) for p,e in inventory_by_path.items() if e["kind"] in {"excluded","generated","data"})).encode()).hexdigest()},
        "factors":factors,
        "summary": {"functions": len(values), "decisions": sum(file["decisions"] for file in files if file["metric_family"] == "control_flow"),
            "hotspots": sum(v >= 15 for v in values), "very_high": sum(v >= 40 for v in values),
            "max_cyclomatic": max(values, default=0)},
        "files": files, "findings": sorted(findings, key=lambda f: (f["metric_family"] == "structure", -f["cyclomatic"], f["path"], f["line"])),
        "policy": POLICY}


def reduction_evidence(before, after):
    """Necessary numerical conditions; the consumer must also verify delivery."""
    reasons = []
    if before["version"] != after["version"] or before["analyzer"] != after["analyzer"] or before["scope_hash"] != after["scope_hash"]:
        reasons.append("The measurement policy or exclusions changed")
    if before["coverage"]["parse_error_paths"] or after["coverage"]["parse_error_paths"]:
        reasons.append("Source parse errors prevent a comparable reduction")
    if before["coverage"].get("excluded_fingerprint") != after["coverage"].get("excluded_fingerprint"):
        reasons.append("Changed excluded, generated or recorded data prevents a comparable reduction")
    if before["coverage"].get("measured_languages") != after["coverage"].get("measured_languages"):
        reasons.append("Language coverage changed; establish a comparable baseline before credit")
    if any(after.get("factors",{}).get(family,{}).get("decisions",0) > before.get("factors",{}).get(family,{}).get("decisions",0) for family in set(before.get("factors",{})) | set(after.get("factors",{}))):
        reasons.append("A measured factor increased; complexity may have moved between factors")
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
