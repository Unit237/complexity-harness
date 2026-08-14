# Coding agents

Before changing a local hotspot, inspect analogous findings and architectural
memory. Cyclomatic complexity is evidence about control flow, not proof that a
refactor is valuable. Preserve behavior, keep job scope bounded, and never let
an executor adapter merge or deploy automatically.

When executing a generated refactor job:

1. Require `readiness.status` to be `ready`.
2. Read every applicable repository instruction plus attached memory and
   invariants.
3. Characterize behavior before editing.
4. Stay inside `scope.allowed_paths`; stop on scope expansion.
5. Run every required check and produce an after snapshot and diff.
6. Return a draft only. Never merge or deploy.

Do not lower a finding by moving branches into an unmeasured helper or by
replacing explicit behavior with flags. If several branches reveal one missing
system invariant, stop the bounded refactor and propose that architectural
change separately.

Run `python -m pytest`, `complexity-harness scan . --output /tmp/snapshot.json`,
and `complexity-harness validate /tmp/snapshot.json` after changing analyzers
or contracts. See `docs/agent-refactor-playbook.md` for the end-to-end workflow.
