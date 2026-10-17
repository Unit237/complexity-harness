# Complexity Harness

[![CI](https://github.com/Unit237/complexity-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/Unit237/complexity-harness/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB.svg)](https://www.python.org/)
[![MIT License](https://img.shields.io/badge/license-MIT-0A7B83.svg)](LICENSE)

**Find complexity with evidence. Preserve architectural intent. Give coding agents bounded work.**

Complexity Harness is a Python CLI with bundled, pinned syntax parsers that combines exact
cyclomatic evidence, a canonical repository inventory, architectural memory,
registered invariants, and approval-required refactor jobs.

It was built around one observation:

> AI makes local code generation cheap. It does not automatically make conceptual consolidation cheap.

The expensive failure mode is often not duplicate code. It is **accidental
semantic duplication**: several authorization rules, lifecycle transitions,
session bootstrap behaviors, or recovery policies that independently encode
the same underlying concept.

Cyclomatic complexity can reveal a function worth investigating. Architectural
memory explains why a seemingly simple path may be more dangerous. The harness
keeps those signals separate and inspectable.

## What it does

- Inventories any repository, with branch evidence for 17 programming-language adapters and structural evidence for 11 declarative formats.
- Scans a multi-repository workspace from a canonical inventory.
- Excludes aliases, duplicate checkouts, generated packages, and build outputs.
- Gives duplicate symbols deterministic, collision-free finding IDs.
- Attaches path-relevant architectural memory and registered invariants.
- Produces JSON snapshots and concise Markdown reports.
- Generates bounded, executor-neutral refactor jobs.
- Blocks agent execution when no verification command is registered.
- Compares before and after snapshots without merging or deploying anything.

```mermaid
flowchart LR
    Inventory["Canonical repository inventory"] --> Scan["Repository scans"]
    Code["Customer repository source"] --> Scan
    Memory["Architectural memory"] --> Snapshot["Workspace snapshot"]
    Invariants["Registered invariants"] --> Snapshot
    Scan --> Snapshot
    Snapshot --> Report["Human-readable report"]
    Report --> Select["Human selects a finding"]
    Select --> Job["Bounded refactor job"]
    Job --> Agent["Compress Cloud, Codex, or another agent"]
    Agent --> Verify["Checks + after snapshot + diff"]
    Verify --> Review["Human review"]
```

## Quick start

```bash
git clone https://github.com/Unit237/complexity-harness.git
cd complexity-harness
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

Or install directly from GitHub:

```bash
python -m pip install "complexity-harness @ git+https://github.com/Unit237/complexity-harness.git"
```

### Scan one repository

```bash
complexity-harness scan . --output /tmp/before.json
complexity-harness validate /tmp/before.json
complexity-harness report /tmp/before.json --top 15
```

Configuration is optional at `.complexity/config.json`:

```json
{
  "cyclomatic_threshold": 12,
  "required_checks": ["python -m pytest"],
  "exclude": ["vendor", "generated"]
}
```

### Measure a fixed burden index

```bash
complexity-harness burden /tmp/before.json
```

`complexity-burden-v3` maps explicit control-flow decisions onto 0–100;
higher is worse. A unit with 0 / 5 / 14 / 24 decisions has a fixed load of
0 / 20.83 / 58.33 / 100. The repository combines 60% mean load with 40% mean
highest-decile load; the highest repository sets the product score. These are
investigation thresholds, not defect probabilities or an empirical measure of
engineering time. Raw counts remain visible above the 24-decision saturation
point. Nesting, domain necessity, coupling and semantic duplication need review.

Declarative adapters retain nesting/fan-out diagnostics without a numeric score.
The 20-repository calibration found ordinary document structure dominating 18
of the first 19 v2 scores. Comparing those points with cyclomatic decisions was
misleading; document-only repositories are now unmeasured on the main map.
This version change establishes a baseline and earns no Work credit.

See [benchmarks/README.md](benchmarks/README.md) for the pinned public corpus,
180 construct oracles, independent comparison, results and limitations. Public
repositories are customer stand-ins, not actual customer outcome validation.

The scan inventories every Git-visible file, including `.mjs`, `.cc`, shell,
Terraform, SQL, configuration and unknown customer extensions. Documentation,
assets, recorded report/fixture data, generated/lock files and exclusions are counted separately. Unknown
languages, unsupported dialects, parse errors, mixed embedded templates,
symlinks and oversized files remain unmeasured with content fingerprints.
Customer source is never executed. The broker uses bundled parsers offline and
returns measurements, never source bodies. Python uses the stdlib AST; other
adapters pin tree-sitter-language-pack 0.13.0 and tree-sitter 0.25.2. Available
grammars are not automatically advertised as validated complexity adapters.

Completed Work cannot lower the accepted score by itself. A comparable scan
must remove load without increasing any factor, changing language coverage or
changing unknown/generated/excluded source or recorded data. The product also requires approved
source scope, merged delivery, passing CI, and durable behavior-test receipts on
the exact measured revision. A parser/analysis upgrade creates a labeled new
baseline, retains old receipts, and awards no reduction or Work credit.

See `tests/test_polyglot.py` for the adapter corpus and customer inventory cases.
Bump both the measurement generation and analyzer identity when releasing a
changed parser/runtime, adapter registry, classification or scoring policy.

## Read a finding in context

```bash
complexity-harness context /tmp/workspace-before.json \
  services/api/src/routing.py
```

The result contains matching file metrics, findings, architectural-memory
entries, and registered invariants. This is where a number becomes an
engineering investigation instead of an automatic refactor order.

## Generate a safe refactor job

First choose a finding from the report. Do not automatically choose the
largest number; prefer a hotspot with clear behavior, relevant tests, recent
change pressure, and bounded blast radius.

```bash
complexity-harness refactor-job \
  /tmp/workspace-before.json \
  CYC-EXAMPLE1234 \
  --executor agent-neutral \
  --allow services/api/tests/test_routing.py \
  --check "cd services/api && python -m pytest tests/test_routing.py" \
  --output /tmp/refactor-job.json
```

If no `--check` is supplied and the repository has no configured checks, the
job is generated with `readiness.status: blocked`. That is intentional.

Inspect the envelope, then render the exact prompt for the next agent:

```bash
jq '.readiness, .scope, .registered_invariant_ids, .architectural_memory_ids' \
  /tmp/refactor-job.json

complexity-harness agent-prompt /tmp/refactor-job.json
```

The generated prompt requires the agent to:

1. Read repository instructions, architectural memory, and invariants.
2. Characterize current behavior before editing.
3. Search for analogous hotspots and shared concepts.
4. Stay inside explicit allowed paths.
5. Run every required check and create an after snapshot.
6. Return a draft only—never merge or deploy.

The complete workflow is in the
[agent refactor playbook](docs/agent-refactor-playbook.md).

## Verify the outcome

After the bounded change:

```bash
complexity-harness workspace-scan . --output /tmp/workspace-after.json
complexity-harness diff \
  /tmp/workspace-before.json \
  /tmp/workspace-after.json
```

The delta reports added, removed, and changed files; introduced and resolved
findings; and complexity changes for stable finding IDs. A lower number is not
enough—the required behavioral checks and invariant review must also pass.

## Commands

| Command | Purpose |
|---|---|
| `scan` | Scan one repository. |
| `workspace-scan` | Scan canonical repositories and aggregate their evidence. |
| `validate` | Validate snapshot structure, counts, paths, and unique IDs. |
| `report` | Render a concise Markdown report. |
| `health` | Print machine-readable summary and findings. |
| `context` | Load metrics, memory, and invariants for paths. |
| `impact` | Show snapshot evidence for repeated `--changed` paths. |
| `diff` | Compare files and stable findings before and after. |
| `refactor-job` | Create an approval-required bounded job. |
| `agent-prompt` | Render the job as a prompt for a coding agent. |

Use `complexity-harness <command> --help` for arguments.

## Architectural memory is not a score

Architectural-memory entries record recurring semantic pressure, prior
decisions, evidence paths, and the trigger future work should recognize:

```json
{
  "id": "MEM-AUTH-001",
  "concept": "workspace-authorization",
  "status": "active",
  "summary": "Several routes independently decide the same access rule.",
  "evidence": [
    {"path": "services/api/src/auth.py", "note": "Canonical policy boundary."}
  ],
  "decision": "Route authorization through one policy boundary.",
  "next_trigger": "Any new workspace resource route."
}
```

Cyclomatic findings remain local control-flow evidence. Memory and invariants
remain semantic context. The harness does not collapse them into a universal
maintainability score.

## Registered invariants are executable architecture

The invariant registry is intentionally small. Each entry names an owner and
versioned contract, shows where the rule manifests, records evidence-backed
exceptions, and points to conformance tests:

```json
{
  "id": "INV-AUTH-001",
  "name": "Workspace resource operations require canonical authorization",
  "owner": "shared-platform",
  "version": "workspace-authorization-v1",
  "contract": "architecture/contracts/workspace-authorization-v1.json",
  "status": "enforced",
  "manifestations": [
    {
      "system": "api",
      "path": "services/api/src/workspace_access.py",
      "role": "canonical-policy"
    }
  ],
  "exceptions": [],
  "conformance_tests": ["services/api/tests/test_workspace_access.py"]
}
```

The registry is not a graph database. It is portable JSON that makes an
architectural rule visible to humans, CI, and the next coding agent.

## Safety model

Every generated job is executor-neutral and human-approved:

- explicit allowed paths and a five-file ceiling;
- scope expansion means stop and request review;
- behavior characterization is required;
- before/after snapshots are required;
- missing checks block readiness;
- secrets and destructive migrations are prohibited;
- automatic merge and production deployment are prohibited.

An adapter may submit the envelope to Compress Cloud, Codex, or another agent.
The core never imports an agent SDK or gives the executor broader authority.

## Current support and honest limits

Python analysis uses the stdlib AST. The validated adapter list is declared in
`burden.py`, with independent corpus cases in `test_polyglot.py`. Unrecognized
source stays in coverage as unknown. Coupling, semantic duplication and business
necessity still require source investigation; this index does not certify them.

The harness also deliberately does **not**:

- infer that the highest CC finding is the best refactor;
- detect semantic duplication from identifiers alone;
- authorize a refactor because a threshold was crossed;
- merge or deploy an agent's work.

## Dogfood result

Across 14 canonical repositories in the Light Reach workspace, the
inventory-aware scan currently analyzes 1,533 Python files and 14,623
functions, attaches eight architectural
memory entries and eleven invariants, and produces 1,096 investigation
candidates at repository-specific thresholds—with zero duplicate IDs and zero
generated or duplicate-checkout leakage.

Those 1,096 findings are **not 1,096 refactor tickets**. They are evidence from
which a human can select a small, testable, architecturally informed job.

## Project docs

- [Agent refactor playbook](docs/agent-refactor-playbook.md)
- [LinkedIn launch kit](docs/linkedin-launch-post.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

## License

MIT. Built by [Light Reach](https://lightreach.io).
