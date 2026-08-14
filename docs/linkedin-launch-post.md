# LinkedIn launch kit

## Recommended post type

Use a **thesis-first engineering post**, not a generic “we launched an open
source tool” announcement. The interesting idea is that AI accelerates local
code production faster than it accelerates conceptual consolidation.

Pair the post with three images:

1. the Markdown report showing repositories and top investigation candidates;
2. the README workflow diagram from inventory to human review;
3. a cropped refactor-job snippet showing `readiness`, `allowed_paths`, required
   checks, and `automatic_merge: false`.

## Primary post

AI coding agents make code generation cheap.

They do not automatically make architectural consolidation cheap.

That creates a failure mode I keep seeing: **accidental semantic duplication**.
It is not necessarily duplicated code. It is five authorization checks, four
lifecycle interpretations, or three session-recovery paths that independently
encode what should have been one invariant.

Cyclomatic complexity helps locate dense control flow, but it cannot tell you
whether a complex parser is healthy or whether three simple helpers represent
a missing system boundary.

So we built and open-sourced **Complexity Harness**.

It combines:

- a canonical multi-repository inventory;
- exact Python branch evidence;
- architectural memory and registered invariants;
- before/after snapshots;
- bounded refactor jobs for Compress Cloud, Codex, or another agent.

The safety boundary matters most: a job has explicit allowed paths, required
tests, stop conditions, and human approval. It cannot automatically merge or
deploy. If verification is missing, the job is marked blocked.

Across 14 canonical repositories in our Light Reach workspace it analyzed
1,533 Python files and 14,623 functions while excluding generated artifacts
and duplicate checkouts.
It found 1,096 investigation candidates.

The point is not to create 1,096 refactor tickets. The point is to select one
real, testable problem with enough architectural context to improve the system
instead of merely moving branches around.

Repository: https://github.com/Unit237/complexity-harness

I would love feedback from teams using coding agents on large, evolving
codebases. How are you preventing local fixes from outpacing architectural
compression?

#OpenSource #SoftwareArchitecture #AICoding #DeveloperTools

## Short version

AI makes patches cheap. Architectural consolidation is still expensive.

We open-sourced Complexity Harness to connect exact Python complexity evidence
with canonical repository inventories, architectural memory, invariants, and
bounded agent refactor jobs.

It deliberately refuses to turn “high cyclomatic complexity” into “automatic
refactor.” Every job needs explicit paths, behavioral checks, stop conditions,
and human approval—and it can never merge or deploy by itself.

https://github.com/Unit237/complexity-harness

#OpenSource #SoftwareArchitecture #AICoding

## Carousel outline

1. **AI makes code generation cheap.**
2. **Complexity accumulates when architecture is not compressed at the same rate.**
3. **Duplicate meaning is often more dangerous than duplicate code.**
4. **Cyclomatic complexity is evidence—not a verdict.**
5. **Add architectural memory and registered invariants.**
6. **Give the agent a bounded job with tests and stop conditions.**
7. **Measure before/after; keep merge and deployment human.**
8. **Complexity Harness is open source.**
