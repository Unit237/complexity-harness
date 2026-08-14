# Changelog

## Unreleased

- Added parser-backed complexity scans for JavaScript, JSX, TypeScript, TSX,
  Dart, Terraform/HCL, and shell source files.
- Added language-aware callable, script, and infrastructure-block scopes with
  exact branch evidence.
- Changed repository traversal to prune excluded directories consistently for
  every supported language.

## 0.2.0

- Added canonical multi-repository workspace scans.
- Added inventory exclusions for aliases, build products, and generated paths.
- Added deterministic collision-free IDs for duplicate symbols.
- Added root architectural-memory and invariant integration.
- Added Markdown reports and path context.
- Added readiness-gated, executor-neutral refactor jobs and agent prompts.
- Added changed-finding evidence to before/after diffs.
- Added CI, public contribution guidance, a security policy, and launch docs.

## 0.1.0

- Initial AST-based Python cyclomatic analyzer.
- Initial repository snapshots, architectural memory, diffs, and refactor jobs.
