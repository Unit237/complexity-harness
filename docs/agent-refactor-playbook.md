# Agent refactor playbook

This playbook turns a complexity finding into a bounded, evidence-backed
refactor. It works with Compress Cloud, Codex, or another coding agent because
the job envelope is vendor-neutral.

## 1. Create the baseline

Run from the canonical workspace root:

```bash
complexity-harness workspace-scan . --output /tmp/complexity-before.json
complexity-harness validate /tmp/complexity-before.json
complexity-harness report /tmp/complexity-before.json \
  --top 25 \
  --output /tmp/complexity-before.md
```

Commit or otherwise record the exact source revision before delegating work.
The snapshot stores each repository commit when it is available.

## 2. Select an investigation, not merely a number

A strong first refactor candidate has most of these properties:

- the behavior is exercised by deterministic tests;
- the function changes often or regularly causes defects;
- its branches represent multiple real responsibilities;
- the expected blast radius fits within five files;
- related architectural memory or invariants are understood;
- an owner can review whether behavior was preserved.

Avoid selecting a function solely because it has the highest cyclomatic value.
Generated parsers, protocol adapters, and decision tables can be complex yet
stable. Conversely, several simple authorization helpers can encode a serious
missing invariant.

Load the path context before creating a job:

```bash
complexity-harness context /tmp/complexity-before.json path/to/hotspot.py
```

Read the function, its callers, analogous implementations, tests, attached
memory, and registered invariants.

## 3. Define a real verification boundary

Identify the smallest deterministic checks that characterize the behavior.
Prefer focused tests plus one relevant integration or package check.

Do not delegate a refactor with no verification command. The harness marks
such a job as blocked.

## 4. Generate the bounded job

```bash
complexity-harness refactor-job \
  /tmp/complexity-before.json \
  <finding-id> \
  --executor agent-neutral \
  --allow path/to/test_hotspot.py \
  --check "python -m pytest path/to/test_hotspot.py" \
  --output /tmp/refactor-job.json
```

Review these fields before continuing:

```bash
jq '{readiness, source, scope, verification, architectural_memory_ids, registered_invariant_ids}' \
  /tmp/refactor-job.json
```

Proceed only when `readiness.status` is `ready`, the allowed paths are exact,
and the checks would catch observable regressions.

## 5. Instruct the next agent

Render the complete prompt:

```bash
complexity-harness agent-prompt /tmp/refactor-job.json \
  > /tmp/refactor-agent-prompt.txt
```

Paste that prompt into the coding agent and add this repository-specific
instruction if the environment does not automatically load agent guidance:

> Execute the attached refactor job as a bounded investigation. Read every applicable AGENTS.md and the attached architectural memory and invariants before editing. Characterize current behavior first. Search for analogous cases and identify whether the branches represent one missing invariant or genuinely distinct responsibilities. Change only allowed paths. Do not lower complexity by moving conditionals into unmeasured helpers. Run every required check, produce an after snapshot and diff, and return a draft only. Stop if broader scope, an invariant change, secrets, migration, merge, or deployment access is required.

The agent should return:

1. the behavior it characterized;
2. the concept or responsibilities it found;
3. files changed and why each was allowed;
4. exact check results;
5. before/after complexity and snapshot diff;
6. architectural-memory or invariant implications;
7. any reason the refactor should not be merged.

## 6. Verify independently

After the agent finishes, rerun the declared checks yourself. Then create the
after snapshot:

```bash
complexity-harness workspace-scan . --output /tmp/complexity-after.json
complexity-harness diff \
  /tmp/complexity-before.json \
  /tmp/complexity-after.json \
  > /tmp/complexity-delta.json
```

Review all changed paths, introduced findings, resolved findings, and changed
cyclomatic values. Confirm that complexity was removed through clearer domain
boundaries—not displaced into new helpers, flags, or parallel sources of
truth.

## 7. Merge remains a separate human decision

The job intentionally cannot merge or deploy. Approval should consider:

- behavior and API compatibility;
- test quality;
- architectural fit;
- whether the change actually reduced conceptual burden;
- whether new architectural memory should be recorded.

If the investigation reveals a broader missing invariant, stop the local
refactor. Register the architectural pressure and create a separately reviewed
system-level change.
