# Contributing

Contributions are welcome, especially analyzers backed by real parsers and
gold fixtures.

## Development

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
complexity-harness scan . --output /tmp/harness.json
complexity-harness validate /tmp/harness.json
```

## Design rules

- Keep measurements explainable and evidence-backed.
- Do not turn one metric into a universal maintainability score.
- Preserve the separation between numeric findings, architectural memory, and
  registered invariants.
- New language analyzers need a real parser, exact branch evidence, and gold
  fixtures.
- Refactor jobs must remain executor-neutral, human-approved, and unable to
  merge or deploy.
- Add a regression test for every bug fix.

Please keep pull requests focused and explain the before/after contract.
