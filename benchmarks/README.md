# Complexity calibration, 17 October 2026

Twenty pinned public repositories stand in for backend, frontend, mobile,
systems, testing, infrastructure and data customers. The runner reads immutable
archives without extracting, importing, building or executing customer code.
Commit and archive SHA-256 pins live in `repositories-v1.json`.

## Meaning and verification

`complexity-burden-v6` measures explicit source decisions, not engineering time,
defect probabilities or universal maintainability. A unit with 0, 5, 14 or 24
decisions has load 0, 20.83, 58.33 or 100. A repository combines 60% mean load
and 40% highest-decile mean load. The product uses its highest repository score.
Nesting, domain necessity, coupling and duplication still require source review.
Raw counts remain visible above the display's 24-decision saturation point.

Declarative nesting and fan-out remain diagnostics without a calibrated score.
Document-only repositories do not receive a healthy zero. Embedded control flow,
including scripts, build recipes, template conditions and CI expressions,
contributes to the programming index. Macro definitions are measured once as
source, not expanded at each invocation. Changed unscored configuration,
template data, unknown source or excluded data prevents reduction credit.

An analyzer or classification upgrade establishes a labeled baseline, preserves
historical receipts and earns no Work credit. Delivered Work requires fewer
measured decisions, comparable source and policy, and successful durable behavior
checks and CI on the exact merged revision before it can lower the accepted score.

## Evidence and limits

- 274 manually specified construct/syntax cases cover 26 language/dialect profiles, including six newer-Python cases. C/C++ headers and content-detected scripts have additional shared admission paths. Twenty declarative formats retain diagnostics. These regression checks are not a blind holdout or human-rated maintainability validation.
- Lizard 1.24.1 supplies an independent comparison for 15 programming languages. Unique start-line pairing records unmatched routines. Agreement is diagnostic, not accuracy: closure ownership, preprocessor, type markers and exception conventions differ. Historical disagreement triage is retained in `reference-triage-v2.json`.
- Pinned LibCST 1.9.0 parses Python 3.12–3.14 independently of the producer interpreter. Babel, tree-sitter grammars and static readers have versioned identities. Repository code is never executed or rendered.
- Go/Plan 9 assembly uses Go 1.25.3 instruction tables, architecture-specific branches and conditional moves. `generate_go_opcodes.py` reproduces the vocabulary from a trusted SDK; source hashes and the Go license are retained. Other assembler dialects remain unsupported.
- AngularJS common directives and JavaScript-compatible expressions are supported. Filters and unsupported expression dialects stay unmeasured. Caller-dependent C/C++ macro fragments, custom template dialects and customer DSLs also remain unknown when they cannot be fully analyzed. PowerShell's pinned grammar targets 5.1; unrecognized newer syntax stays unknown.
- Conventional metadata, assets and recorded data are separately inventoried and fingerprinted. Coverage is file based; diagnostic-only files cannot inflate scored-source coverage. Partial coverage never rounds to 100%.
- Budgets remain finite: 200,000 eligible source files, 250,000 inventory entries, 8 MiB per source file, 100,000 units per file, 12 MiB wire and 256 MiB expanded evidence. Capacity failures cannot establish a partial baseline. Exact histograms preserve all counts; only 1,000 hotspot examples enter the bounded projection.

## Results

All 20 archives complete: 19 scored and 1 diagnostic-only, with 15,602 analyzed files and 167,690 programming units. The cohorts were selected before execution, but results were inspected; there is no blind performance claim.

The large Skaffold sample improves from 95.43% to 99.97% scored-source coverage. All valid files behind its gaps are analyzed. Three incomplete Dockerfile examples remain unmeasured: two use `...` and one contains an empty `RUN`. This is not a claim that every future language, dialect or malformed customer file is supported.

| Repository | Role | v5 | v6 | Scored source coverage | Parse failures | Unsupported |
|---|---|---:|---:|---:|---:|---:|
| [psf/requests](https://github.com/psf/requests/tree/0e322af87745eff34caffe4df68456ebc20d9068) | python | 14.07 | 14.67 | 93.48% | 0 | 3 |
| [expressjs/express](https://github.com/expressjs/express/tree/cd7d4397c398a3f3ecadeaf9ef6ac1377bd414c4) | javascript | 3.15 | 3.18 | 81.92% | 8 | 24 |
| [vuejs/core](https://github.com/vuejs/core/tree/6eb29d345aa73746207f80c89ee8b37ff7b949c9) | typescript/tsx | 13.04 | 12.97 | 99.29% | 0 | 4 |
| [go-chi/chi](https://github.com/go-chi/chi/tree/0a20a0e3400e551803f463d17a0ab84ee8afef3c) | go | 13.28 | 13.28 | 100.0% | 0 | 0 |
| [DapperLib/Dapper](https://github.com/DapperLib/Dapper/tree/bd4f75b512de3e00f2c2631d5309961a1ecfea23) | csharp | 6.52 | 9.35 | 100.0% | 0 | 0 |
| [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic/tree/500158f732419217507c7656904b8e6aa1bcc0d6) | java | 7.71 | 11.59 | 91.94% | 3 | 4 |
| [sinatra/sinatra](https://github.com/sinatra/sinatra/tree/7b50a1bbb5324838908dfaa00ec53ad322673a29) | ruby | 4.0 | 4.27 | 66.15% | 0 | 87 |
| [slimphp/Slim](https://github.com/slimphp/Slim/tree/5943393b88716eb9e82c4161caa956af63423913) | php | 10.66 | 10.66 | 100.0% | 0 | 0 |
| [tokio-rs/axum](https://github.com/tokio-rs/axum/tree/c59208c86fded335cd85e388030ad59347b0e5ae) | rust | 7.88 | 7.88 | 98.38% | 1 | 4 |
| [dart-lang/shelf](https://github.com/dart-lang/shelf/tree/2536c15a562cb183dabbc628824a215663830325) | dart | 18.96 | 20.08 | 100.0% | 0 | 0 |
| [Kotlin/kotlinx.serialization](https://github.com/Kotlin/kotlinx.serialization/tree/f9f160a680da9f92c3bb121ae3644c96e57ba42e) | kotlin | 5.07 | 5.81 | 100.0% | 127 | 0 |
| [apple/swift-http-types](https://github.com/apple/swift-http-types/tree/ef18d829e8b92d731ad27bb81583edd2094d1ce3) | swift | 17.87 | 16.75 | 100.0% | 0 | 0 |
| [libuv/libuv](https://github.com/libuv/libuv/tree/8fb9cb919489a48880680a56efecff6a7dfb4504) | c | 23.7 | 23.86 | 80.26% | 66 | 9 |
| [fmtlib/fmt](https://github.com/fmtlib/fmt/tree/9cf9f38eded63e5e0fb95cd536ba51be601d7fa2) | cpp | 19.07 | 19.83 | 53.76% | 38 | 5 |
| [lunarmodules/busted](https://github.com/lunarmodules/busted/tree/02f31a9c103a44e166617cfdb6ba1b8994a9c912) | lua | 10.47 | 10.59 | 86.89% | 1 | 15 |
| [bats-core/bats-core](https://github.com/bats-core/bats-core/tree/b640ec3cf2c7c9cfc9e6351479261186f76eeec8) | bash | 18.88 | 25.47 | 23.39% | 4 | 222 |
| [terraform-aws-modules/terraform-aws-vpc](https://github.com/terraform-aws-modules/terraform-aws-vpc/tree/961c9b51e3ed3959d9419f019e7085c087bf7297) | hcl | diagnostic only | 7.08 | 100.0% | 0 | 0 |
| [dbt-labs/jaffle-shop](https://github.com/dbt-labs/jaffle-shop/tree/5beb145b00f5465ec759cfcdd9745e858818cf95) | sql/jinja | 11.67 | 11.67 | 50.0% | 15 | 1 |
| [necolas/normalize.css](https://github.com/necolas/normalize.css/tree/fc091cce1534909334c1911709a39c22d406977b) | css | diagnostic only | diagnostic only | 0.0% | 1 | 0 |
| [GoogleContainerTools/skaffold](https://github.com/GoogleContainerTools/skaffold/tree/f132ab25adf1599c7fbdce733144991126565386) | yaml/json | 21.66 | 21.6 | 99.97% | 3 | 0 |

## Reproduce

Install `.[dev]` in an isolated environment, then run:

```sh
python -m pytest
python benchmarks/run.py --cache /absolute/cache --output /absolute/results
python benchmarks/summarize.py --report /absolute/results/report.json --before /absolute/v5/report.json --output benchmarks/calibration-v4.json
```

The independent analyzer is a dev dependency. `--write-digests` is only for
pinning a new manifest; ordinary runs reject archive digest changes. Validation
archives have a 128 MiB compressed and 512 MiB expanded bound. Native ingestion
retains its stricter transport limits. Full receipts stay in local acceptance
evidence; compact results and hashes are committed in `calibration-v4.json`.

Methodology references: [Lizard](https://github.com/terryyin/lizard) and
[Sonar complexity definitions](https://docs.sonarsource.com/sonarqube-server/2025.1/user-guide/code-metrics/metrics-definition).
Our explicit conventions and branch evidence remain the measurement contract.
