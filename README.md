# Complexity Harness

Complexity Harness produces evidence-backed snapshots of software complexity
and turns selected findings into bounded, approval-required refactor jobs.

The first release deliberately separates two kinds of knowledge:

- **Cyclomatic complexity** is a local control-flow measurement. Python
  findings point to the exact function and branch lines that produced them.
- **Architectural memory** records recurring semantic pressure, prior
  decisions, and the next trigger future work should recognize.

Neither is a universal maintainability score. A high-complexity parser may be
healthy and well tested; three simple authentication helpers may represent a
serious duplicated invariant. The harness keeps those facts inspectable.
These boundaries are machine-readable in
`contracts/harness-policy-v1.json` and protected by a conformance test.

## Commands

```bash
complexity-harness scan . --output snapshot.json
complexity-harness validate snapshot.json
complexity-harness health snapshot.json
complexity-harness diff before.json after.json
complexity-harness impact snapshot.json --changed src/service.py
complexity-harness context snapshot.json src/service.py
complexity-harness refactor-job snapshot.json <finding-id> --output job.json
```

Configuration is optional at `.complexity/config.json`:

```json
{
  "cyclomatic_threshold": 12,
  "required_checks": ["python -m pytest"],
  "exclude": ["vendor", "generated"]
}
```

Architectural memory is optional at
`.complexity/architectural-memory.json`. Entries contain an ID, concept,
status, summary, evidence, decision, and next trigger. The format is included
in `contracts/architectural-memory-v1.schema.json`.

## Refactor executors

The core never imports or calls an agent vendor. A generated `refactor-job-v1`
envelope has permitted paths, a file ceiling, required checks, prohibited
actions, and required human approval. An adapter may later submit that envelope
to Compress Cloud, Codex, or another executor. The initial policy is always:

- draft changes only;
- no automatic merge;
- no production deployment;
- stop on scope expansion;
- preserve an inspectable before/after snapshot.

This keeps the harness useful as deterministic infrastructure while agent
execution evolves independently.

## Current language support

Python cyclomatic analysis is exact and AST-based. Other languages can be
registered behind the analyzer interface once their evidence model and gold
fixtures exist; the CLI does not guess trusted dependencies from identifier
names.
