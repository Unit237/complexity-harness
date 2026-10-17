"""Hand-specified branch counts, independent of the implementation and Lizard."""
import json
from pathlib import Path
import pytest
from complexity_harness.polyglot_analyzer import analyze_bytes
from complexity_harness.complexity_languages import LANGUAGE_EXTENSIONS

CASES=json.loads((Path(__file__).parents[1]/'benchmarks/construct-oracle-v1.json').read_text())['cases']

@pytest.mark.parametrize('case',CASES,ids=lambda case:case['id'])
def test_language_constructs_conserve_explicit_decisions(case):
 language=case['language'];extension=LANGUAGE_EXTENSIONS[language].split()[0]
 metric=analyze_bytes(case['source'].encode(),relative_path='oracle.'+extension,language=language)
 assert not metric.parse_error, metric.parse_error
 decisions=sum(f.cyclomatic-1 for f in metric.functions)+sum(b.contribution for b in metric.unattributed_branches)
 assert decisions==case['decisions'],[(f.symbol,f.cyclomatic,[b.kind for b in f.branches]) for f in metric.functions]


def test_versioned_calibration_disclosure_is_bound_to_the_measured_corpus():
 from complexity_harness.burden import ANALYZER, VERSION
 import hashlib
 root=Path(__file__).parents[1]
 report=json.loads((root/"benchmarks/calibration-v2.json").read_text())
 manifest=json.loads((root/"benchmarks/repositories-v1.json").read_text())
 assert report["measurement_version"]==VERSION and report["analyzer"]==ANALYZER
 assert report["summary"]["construct_cases"]==len(CASES)+report["summary"]["modern_python_cases"]==186
 assert {row["repository"]:row["commit"] for row in report["repositories"]}=={row["repository"]:row["commit"] for row in manifest["repositories"]}
 assert all(len(row["archive_sha256"])==64 for row in manifest["repositories"])
 assert report["evidence_hashes"]["construct_oracle"]==hashlib.sha256((root/"benchmarks/construct-oracle-v1.json").read_bytes()).hexdigest()
 assert report["evidence_hashes"]["repository_manifest"]==hashlib.sha256((root/"benchmarks/repositories-v1.json").read_bytes()).hexdigest()
 assert all(row["score"] is None for row in report["repositories"] if row["status"]!="measured")
