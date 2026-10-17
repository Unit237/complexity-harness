"""The index owns its numeric meaning; source evidence owns comparability."""
import copy
import json
from pathlib import Path

import pytest

from complexity_harness.burden import ANALYZER, POLICY, level, measure_snapshot, reduction_evidence, score_values
from complexity_harness.scanner import scan_repository

ROOT = Path(__file__).parents[1]


def snapshot(values=(25,), sha="a", path="service.py"):
    functions = [{"symbol":f"function_{i}","line":i*100+1,"end_line":i*100+90,"cyclomatic":value,
        "branches":[{"kind":"if","line":i*100+2,"contribution":value-1}] if value>1 else []}
        for i,value in enumerate(values)]
    return {"schema_version":"complexity-snapshot-v1","repository":{"commit":sha*40,"clean":True},
        "coverage":{"analyzer":ANALYZER,"scope_hash":"c"*64,"unsupported_paths":[],"inventory_complete":True,"inventory_policy":"all-files-v2",
            "inventory":[{"path":path,"kind":"source","language":"python","sha256":sha*64}]},
        "files":[{"path":path,"language":"python","sha256":sha*64,"lines":1000,"functions":functions,"unattributed_branches":[]}]}


def test_fixed_policy_and_gold_cases_preserve_hotspot_tail_and_direction():
    assert POLICY == json.loads((ROOT/"contracts/complexity-burden-v6.json").read_text())
    for case in json.loads((ROOT/"tests/fixtures/burden-gold-v1.json").read_text()):
        assert score_values(case["values"]) == case["score"]
        assert level(case["score"]) == case["level"]


def test_missing_languages_and_parse_failures_never_become_healthy_code(tmp_path):
    (tmp_path/"service.py").write_text("def choose(a):\n    if a:\n        return 1\n    return 0\n")
    (tmp_path/"legacy.cbl").write_text("       IDENTIFICATION DIVISION.")
    payload=scan_repository(tmp_path).as_dict()
    payload["repository"].update(clean=True,commit="a"*40)
    result=measure_snapshot(payload)
    assert result["summary"]["decisions"]==1
    assert result["coverage"]["percent"]==50 and not result["coverage"]["complete"]
    assert result["coverage"]["unsupported_paths"]==["legacy.cbl"]
    payload["files"][0]["parse_error"]="Invalid syntax"
    assert measure_snapshot(payload)["score"] is None
    payload["files"]=[]
    with pytest.raises(ValueError,match="Every eligible"):
        measure_snapshot(payload)


def test_a_lower_index_cannot_prove_reduction_by_splitting_or_diluting_functions():
    before=measure_snapshot(snapshot((25,)))
    after=measure_snapshot(snapshot((13,13),sha="b"))
    assert after["score"]<before["score"]
    result=reduction_evidence(before,after)
    assert not result["comparable"] and result["decisions_removed"]==0
    after=measure_snapshot(snapshot((10,),sha="b"))
    assert reduction_evidence(before,after)["comparable"]
    after["scope_hash"]="e"*64
    assert not reduction_evidence(before,after)["comparable"]


@pytest.mark.parametrize("mutation",["dirty","fake-score","unsafe-path","wrong-branches","missing-analyzer"])
def test_measurements_require_reconstructable_commit_bound_evidence(mutation):
    payload=copy.deepcopy(snapshot())
    if mutation=="dirty": payload["repository"]["clean"]=False
    if mutation=="fake-score":
        payload["score"]=0
        assert measure_snapshot(payload)["score"]==100
        return
    if mutation=="unsafe-path": payload["files"][0]["path"]="../service.py"
    if mutation=="wrong-branches": payload["files"][0]["functions"][0]["cyclomatic"]=2
    if mutation=="missing-analyzer": payload["coverage"].pop("analyzer")
    with pytest.raises(ValueError): measure_snapshot(payload)


def test_product_burden_cannot_be_diluted_by_another_repository():
    from complexity_harness.burden import score_repositories
    assert score_repositories([80, 10]) == 80
    assert score_repositories([80, 12, 0, None]) == 80
    assert score_repositories([78, 12]) == 78
    assert score_repositories([None]) is None


def test_source_inventory_never_follows_file_symlinks(tmp_path):
    from complexity_harness.source_scope import content_fingerprint
    external=tmp_path.parent/(tmp_path.name+"-external.py")
    external.write_text("private_source_must_not_be_analyzed = True")
    (tmp_path/"linked.py").symlink_to(external)
    payload=scan_repository(tmp_path).as_dict()
    assert not payload["files"]
    assert payload["coverage"]["unsupported_paths"]==["linked.py"]
    assert payload["coverage"]["unsupported_hashes"]["linked.py"]==content_fingerprint(str(external).encode())


def test_clean_commit_inventory_excludes_ignored_files_and_accounts_for_symlink_directories(tmp_path):
    import subprocess
    def git(*args):
        return subprocess.check_output(["git","-C",str(tmp_path),*args],text=True).strip()
    git("init","-q")
    git("config","user.name","Complexity test")
    git("config","user.email","complexity@example.invalid")
    (tmp_path/".gitignore").write_text("ignored.py\n")
    (tmp_path/"ignored.py").write_text("not_committed = True")
    (tmp_path/"source.py").write_text("def source():\n    return 1\n")
    (tmp_path/"folder.py").symlink_to(tmp_path.parent,target_is_directory=True)
    git("add",".");git("commit","-qm","source inventory")
    result=measure_snapshot(scan_repository(tmp_path).as_dict())
    assert result["coverage"]["eligible_files"]==2
    assert result["coverage"]["unsupported_paths"]==["folder.py"]
    assert [row["path"] for row in result["files"]]==["source.py"]


@pytest.mark.parametrize("replacement",[
    "decide = lambda value: 1 if value else 0\ndef choose(value):\n    return decide(value)\n",
    "if True:\n    result = 1\nelse:\n    result = 0\ndef choose(value):\n    return result\n",
])
def test_moving_branches_outside_named_functions_cannot_earn_reduction_credit(replacement):
    from dataclasses import asdict
    from complexity_harness.python_analyzer import analyze_python_bytes
    before=snapshot(sha="a");after=snapshot(sha="b")
    before["files"]=[asdict(analyze_python_bytes(b"def choose(value):\n    return 1 if value else 0\n",relative_path="service.py"))]
    after["files"]=[asdict(analyze_python_bytes(replacement.encode(),relative_path="service.py"))]
    measured_before,measured_after=measure_snapshot(before),measure_snapshot(after)
    assert measured_after["score"]<measured_before["score"]
    assert measured_after["summary"]["decisions"]==measured_before["summary"]["decisions"]==1
    assert measured_after["files"][0]["unattributed_decisions"]==1
    assert not reduction_evidence(measured_before,measured_after)["comparable"]


def test_reference_anchors_are_fixed_and_concentrated_hotspots_remain_visible():
    for anchor in POLICY["anchors"]:
        assert score_values([anchor["decisions"]+1]*100) == anchor["score"]
    # Equal total decisions, concentrated versus dispersed; tail should expose concentration.
    assert score_values([25]+[1]*9) > score_values([4]*8+[1]*2)
    assert score_values([1,6,15,25]*2) == score_values([1,6,15,25]*20)
    assert score_values([49]*10) == 100  # Saturation is explicit; raw counts remain available.


def test_declarative_documents_never_set_or_dilute_the_control_flow_score(tmp_path):
    (tmp_path/"service.py").write_text("def choose(x):\n"+"".join(f" if x == {i}:\n  return {i}\n" for i in range(18))+" return 0\n")
    def measure(sha):
        payload=scan_repository(tmp_path).as_dict();payload["repository"].update(clean=True,commit=sha*40)
        return measure_snapshot(payload)
    before=measure("a")
    (tmp_path/"config.json").write_text(json.dumps({str(i):{"a":{"b":{"c":{"d":i}}}} for i in range(50)}))
    mixed=measure("b")
    assert mixed["score"] == before["score"]
    assert mixed["summary"] == before["summary"]
    assert mixed["findings"][0]["metric_family"] == "control_flow"
    assert mixed["factors"]["structure"]["decisions"] > 0
    assert mixed["factors"]["structure"]["score"] is None
    assert next(f for f in mixed["files"] if f["path"]=="config.json")["score"] is None
    assert not reduction_evidence(before,mixed)["comparable"]
    (tmp_path/"service.py").unlink()
    document_only=measure("c")
    assert document_only["score"] is None and document_only["level"] == "Unmeasured"
    assert document_only["summary"]["functions"] == 0
    assert document_only["coverage"]["complete"]  # Parsed diagnostics, still no primary score.


def test_scale_upgrade_cannot_earn_reduction_credit():
    before=measure_snapshot(snapshot((25,)))
    after=measure_snapshot(snapshot((10,),sha="b"))
    before["version"]="complexity-burden-v2"
    result=reduction_evidence(before,after)
    assert not result["comparable"]
    assert "The measurement policy or exclusions changed" in result["reasons"]
