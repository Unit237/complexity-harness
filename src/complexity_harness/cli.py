from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .delta import diff_snapshots
from .memory import memory_for_paths
from .refactor import build_refactor_job
from .scanner import scan_repository
from .snapshot import read_snapshot, validate_snapshot, write_json


def _print(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))


def _scan_command(args: argparse.Namespace) -> int:
    payload = scan_repository(args.path).as_dict()
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
    _print({"paths": sorted(normalized), "files": files, "findings": findings, "architectural_memory": memory})
    return 0


def _refactor_job_command(args: argparse.Namespace) -> int:
    payload = build_refactor_job(
        read_snapshot(args.snapshot),
        args.finding_id,
        executor=args.executor,
    )
    if args.output:
        write_json(args.output, payload)
    else:
        _print(payload)
    return 0


COMMANDS = {
    "scan": _scan_command,
    "validate": _validate_command,
    "health": _health_command,
    "diff": _diff_command,
    "impact": _context_command,
    "context": _context_command,
    "refactor-job": _refactor_job_command,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="complexity-harness")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan")
    scan.add_argument("path", nargs="?", default=".")
    scan.add_argument("--output")

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

    args = parser.parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
