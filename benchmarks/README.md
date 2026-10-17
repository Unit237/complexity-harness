# Complexity calibration, 17 October 2026

This validation uses 20 pinned public repositories as customer stand-ins across
backend, frontend, mobile, systems, testing, infrastructure and data products.
It never builds, imports or executes code from those repositories. Archives
are read without extraction; commit and archive SHA-256 are pinned in
`repositories-v1.json`. Recordings live outside the checkout; the compact
versioned results and reference disagreement audit are committed here.

## What the number means

`complexity-burden-v3` measures explicit control-flow decisions. The fixed
anchors are 0, 5, 14 and 24 decisions → 0, 20.83, 58.33 and 100 load points.
A repository combines 60% mean unit load and 40% highest-decile mean load.
A product uses its highest repository score. These thresholds are policy
choices for investigation, not an empirical prediction of defects, labor or
maintainability. Large essential algorithms can score highly; source review
must determine whether a reduction would help. Nesting is not cognitive load
in this index. Saturation keeps the display bounded; raw counts remain visible.

The initial v2 corpus showed document structure setting the score in 18 of
19 completed repositories. Ordinary manifests and markup could dominate
program logic. v3 preserves structural diagnostics without a common numeric
scale. Document-only repositories have no primary score. An analysis upgrade
is explicitly a new baseline; it earns no reduction credit.

## Validation and limitations

- 180 hand-specified construct cases span 17 programming-language adapters.
  They include defaults, closures, short circuits, guarded matches, loops,
  propagation, type-only syntax, comments and strings. Counts are independent
  expectations, not values copied from the analyzer. These cases drove fixes,
  so their pass rate is regression evidence, not blind predictive accuracy.
- Fixed anchor, concentration, population replication, dilution, displacement,
  unknown-source and version-change tests protect score meaning and credit.
- Lizard 1.24.1 provides an independent comparison across 15 languages. Dart
  and Bash are covered by manual construct oracles, not that comparison.
  Pairing uses unique start lines and records unmatched routines. Different
  spans, nested closure ownership, nullable type syntax, preprocessor and
  exception conventions prevent interpreting agreement as accuracy.
- `reference-triage-v1.json` inspects the largest paired disagreement per
  compared language with exact source links, spans and branch kinds. This
  exposed missed Java enhanced loops and inappropriate Swift `try` counting.
  Remaining differences include Lizard parsing type markers or empty Rust
  closures as choices and grouping several routines into one span. Reviewed
  counterexamples are retained in the construct oracle.
- Python syntax is pinned to the 3.11 grammar across producer runtimes;
  newer syntax remains unmeasured until a versioned grammar upgrade.
- The corpus includes unsupported dialects, embedded templates, parser
  failures, unknown source and a resource-limited monorepo. No case is
  silently omitted or assigned zero. Percentage coverage is file based,
  not a guarantee about unparsed lines. Diagnostic documents do not inflate
  the scored-source coverage shown beside the number.
- The manifest's two cohorts were chosen before execution, but all initial
  results were inspected. There is no blind holdout claim. There are no
  human-rated complexity or actual customer engineering outcome labels.

## Results

“Before” uses the prior v2 method; changes are recalibration, never Work credit.
Scored coverage excludes declarative formats and includes unknown files in the
denominator. The full Skaffold tree exceeds 100,000 measured units; a bounded
snapshot is refused rather than truncated. Large-repository partitioning is a
remaining capability, not a tested production claim.

| Repository | Role | v2 | v3 | Scored source coverage | Parse failures |
|---|---|---:|---:|---:|---:|
| [psf/requests](https://github.com/psf/requests/tree/0e322af87745eff34caffe4df68456ebc20d9068) | python | 53.17 | 14.08 | 58.06% | 1 |
| [expressjs/express](https://github.com/expressjs/express/tree/cd7d4397c398a3f3ecadeaf9ef6ac1377bd414c4) | javascript | 55.47 | 3.16 | 79.33% | 4 |
| [vuejs/core](https://github.com/vuejs/core/tree/6eb29d345aa73746207f80c89ee8b37ff7b949c9) | typescript/tsx | 49.79 | 13.07 | 90.26% | 28 |
| [go-chi/chi](https://github.com/go-chi/chi/tree/0a20a0e3400e551803f463d17a0ab84ee8afef3c) | go | 64.0 | 13.28 | 93.59% | 0 |
| [DapperLib/Dapper](https://github.com/DapperLib/Dapper/tree/bd4f75b512de3e00f2c2631d5309961a1ecfea23) | csharp | 40.0 | 6.52 | 84.15% | 1 |
| [spring-projects/spring-petclinic](https://github.com/spring-projects/spring-petclinic/tree/500158f732419217507c7656904b8e6aa1bcc0d6) | java | 75.09 | 7.73 | 62.5% | 8 |
| [sinatra/sinatra](https://github.com/sinatra/sinatra/tree/7b50a1bbb5324838908dfaa00ec53ad322673a29) | ruby | 58.0 | 4.0 | 60.23% | 0 |
| [slimphp/Slim](https://github.com/slimphp/Slim/tree/5943393b88716eb9e82c4161caa956af63423913) | php | 10.66 | 10.66 | 100.0% | 0 |
| [tokio-rs/axum](https://github.com/tokio-rs/axum/tree/c59208c86fded335cd85e388030ad59347b0e5ae) | rust | 18.37 | 7.9 | 82.92% | 4 |
| [dart-lang/shelf](https://github.com/dart-lang/shelf/tree/2536c15a562cb183dabbc628824a215663830325) | dart | 57.13 | 18.86 | 90.48% | 8 |
| [Kotlin/kotlinx.serialization](https://github.com/Kotlin/kotlinx.serialization/tree/f9f160a680da9f92c3bb121ae3644c96e57ba42e) | kotlin | 10.77 | 5.07 | 91.46% | 143 |
| [apple/swift-http-types](https://github.com/apple/swift-http-types/tree/ef18d829e8b92d731ad27bb81583edd2094d1ce3) | swift | 28.0 | 17.87 | 76.19% | 3 |
| [libuv/libuv](https://github.com/libuv/libuv/tree/8fb9cb919489a48880680a56efecff6a7dfb4504) | c | 76.11 | 20.27 | 75.26% | 72 |
| [fmtlib/fmt](https://github.com/fmtlib/fmt/tree/9cf9f38eded63e5e0fb95cd536ba51be601d7fa2) | cpp | 71.35 | 20.1 | 37.86% | 37 |
| [lunarmodules/busted](https://github.com/lunarmodules/busted/tree/02f31a9c103a44e166617cfdb6ba1b8994a9c912) | lua | 58.33 | 10.47 | 79.51% | 1 |
| [bats-core/bats-core](https://github.com/bats-core/bats-core/tree/b640ec3cf2c7c9cfc9e6351479261186f76eeec8) | bash | 68.7 | 18.88 | 16.83% | 1 |
| [terraform-aws-modules/terraform-aws-vpc](https://github.com/terraform-aws-modules/terraform-aws-vpc/tree/961c9b51e3ed3959d9419f019e7085c087bf7297) | hcl | 32.71 | diagnostic only | 0.0% | 0 |
| [dbt-labs/jaffle-shop](https://github.com/dbt-labs/jaffle-shop/tree/5beb145b00f5465ec759cfcdd9745e858818cf95) | sql/jinja | 80.34 | diagnostic only | 0.0% | 16 |
| [necolas/normalize.css](https://github.com/necolas/normalize.css/tree/fc091cce1534909334c1911709a39c22d406977b) | css | 0.0 | diagnostic only | 0.0% | 1 |
| [GoogleContainerTools/skaffold](https://github.com/GoogleContainerTools/skaffold/tree/f132ab25adf1599c7fbdce733144991126565386) | yaml/json | — | resource limited | — | — |

## Reproduce

Install `.[dev]` in an isolated environment (the independent analyzer is a dev
dependency, not a customer runtime dependency), then run:

```sh
python -m pytest
python benchmarks/run.py --cache /absolute/cache --output /absolute/results
python benchmarks/triage.py --report /absolute/results/report.json --cache /absolute/cache --output /absolute/reference-triage.json
```

`--write-digests` is only for deliberately pinning a new manifest. Normal runs
reject archive digest changes. Downloads have a 128 MB compressed bound and
512 MB expanded bound; runtime ingestion retains its stricter existing limits.
The full before/after receipts are retained in the local acceptance evidence.

Independent methodology references: [Lizard](https://github.com/terryyin/lizard)
and [Sonar's complexity definitions](https://docs.sonarsource.com/sonarqube-server/2025.1/user-guide/code-metrics/metrics-definition).
Our declared conventions and exact branch evidence are the measurement contract.
