from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from . import __version__
from .delta import diff_snapshots
from .invariants import invariants_for_paths
from .memory import memory_for_paths
from .refactor import build_refactor_job
from .report import markdown_report
from .scanner import scan_repository
from .snapshot import read_snapshot, validate_snapshot, write_json
from .workspace import scan_workspace


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _scan_command(args: argparse.Namespace) -> int:
    payload = scan_repository(
        args.path,
        architectural_memory_path=args.memory,
    ).as_dict()
    if args.output:
        write_json(args.output, payload)
    else:
        _print(payload)
    return 0


def _workspace_scan_command(args: argparse.Namespace) -> int:
    payload = scan_workspace(
        args.path,
        inventory_path=args.inventory,
        architectural_memory_path=args.memory,
        invariants_path=args.invariants,
    )
    if args.output:
        write_json(args.output, payload)
    else:
        _print(payload)
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    validate_snapshot(read_snapshot(args.snapshot))
    print("complexity snapshot is valid")
    return 0


def _health_command(args: argparse.Namespace) -> int:
    payload = read_snapshot(args.snapshot)
    _print({"summary": payload["summary"], "findings": payload["findings"]})
    return 0


def _diff_command(args: argparse.Namespace) -> int:
    _print(diff_snapshots(read_snapshot(args.before), read_snapshot(args.after)))
    return 0


def _context_command(args: argparse.Namespace) -> int:
    payload = read_snapshot(args.snapshot)
    paths = args.changed if args.command == "impact" else args.paths
    normalized = {Path(value).as_posix().lstrip("./") for value in paths}
    files = [row for row in payload["files"] if row["path"] in normalized]
    findings = [row for row in payload["findings"] if row["path"] in normalized]
    memory = memory_for_paths(payload["architectural_memory"], list(normalized))
    invariants = invariants_for_paths(payload.get("invariants") or [], list(normalized))
    _print({
        "paths": sorted(normalized),
        "files": files,
        "findings": findings,
        "architectural_memory": memory,
        "registered_invariants": invariants,
    })
    return 0


def _refactor_job_command(args: argparse.Namespace) -> int:
    payload = build_refactor_job(
        read_snapshot(args.snapshot),
        args.finding_id,
        executor=args.executor,
        allowed_paths=args.allow,
        required_checks=args.check,
    )
    if args.output:
        write_json(args.output, payload)
    else:
        _print(payload)
    return 0


def _report_command(args: argparse.Namespace) -> int:
    report = markdown_report(read_snapshot(args.snapshot), top=args.top)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
    else:
        print(report, end="")
    return 0


def _agent_prompt_command(args: argparse.Namespace) -> int:
    payload = json.loads(Path(args.job).read_text(encoding="utf-8"))
    prompt = payload.get("agent_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("refactor job has no agent_prompt")
    print(prompt)
    return 0


COMMANDS = {
    "scan": _scan_command,
    "workspace-scan": _workspace_scan_command,
    "validate": _validate_command,
    "health": _health_command,
    "diff": _diff_command,
    "impact": _context_command,
    "context": _context_command,
    "refactor-job": _refactor_job_command,
    "report": _report_command,
    "agent-prompt": _agent_prompt_command,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="complexity-harness",
        description=(
            "Create evidence-backed complexity snapshots and bounded, "
            "approval-required refactor jobs."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("path", nargs="?", default=".")
    scan.add_argument("--output")
    scan.add_argument("--memory")

    workspace_scan = sub.add_parser("workspace-scan")
    workspace_scan.add_argument("path", nargs="?", default=".")
    workspace_scan.add_argument("--inventory")
    workspace_scan.add_argument("--memory")
    workspace_scan.add_argument("--invariants")
    workspace_scan.add_argument("--output")

    validate = sub.add_parser("validate")
    validate.add_argument("snapshot")

    health = sub.add_parser("health")
    health.add_argument("snapshot")

    delta = sub.add_parser("diff")
    delta.add_argument("before")
    delta.add_argument("after")

    impact = sub.add_parser("impact")
    impact.add_argument("snapshot")
    impact.add_argument("--changed", action="append", required=True)

    context = sub.add_parser("context")
    context.add_argument("snapshot")
    context.add_argument("paths", nargs="+")

    job = sub.add_parser("refactor-job")
    job.add_argument("snapshot")
    job.add_argument("finding_id")
    job.add_argument("--executor")
    job.add_argument("--output")
    job.add_argument("--allow", action="append", default=[])
    job.add_argument("--check", action="append")

    report = sub.add_parser("report")
    report.add_argument("snapshot")
    report.add_argument("--top", type=int, default=15)
    report.add_argument("--output")

    prompt = sub.add_parser("agent-prompt")
    prompt.add_argument("job")

    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
