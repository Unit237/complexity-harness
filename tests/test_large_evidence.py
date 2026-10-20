"""Capacity changes preserve complete counts, identity and reduction authority."""
import json
import pytest
from complexity_harness.burden import ANALYZER, measure_snapshot, reduction_evidence
from complexity_harness.complexity_evidence import pack, unpack, pack_snapshot


def source(files=101, functions=1001, decisions=1, sha="a"):
    rows=[];inventory=[]
    for i in range(files):
        path=f"services/{i}.py"
        inventory.append({"path":path,"sha256":sha*64,"kind":"source","language":"python"})
        rows.append({"path":path,"sha256":sha*64,"language":"python","lines":3,"unattributed_branches":[],
            "functions":[{"symbol":f"function_{j}","occurrence":1,"line":1,"end_line":3,"cyclomatic":decisions+1,
                "branches":[{"kind":"if","line":2,"contribution":decisions}] if decisions else []} for j in range(functions)]})
    return {"schema_version":"complexity-snapshot-v1","repository":{"commit":sha*40,"clean":True},"files":rows,
        "coverage":{"analyzer":ANALYZER,"scope_hash":"c"*64,"inventory_complete":True,"inventory_policy":"all-files-v2",
            "inventory":inventory,"unsupported_paths":[],"unsupported_hashes":{}}}


def test_large_receipt_conserves_every_function_and_bounds_only_investigation_examples():
    raw=source(decisions=14)
    packed=pack_snapshot(raw)
    assert len(json.dumps(packed).encode())<12*1024*1024
    measured=measure_snapshot(packed)
    assert measured["summary"]["functions"]==101101
    assert measured["summary"]["hotspots"]==101101
    assert measured["summary"]["decisions"]==101101*14
    assert measured["score"]==58.33
    assert len(measured["findings"])==1000
    assert measured["files"][0]["histogram"]=={"15":1001}
    lower=measure_snapshot(pack_snapshot(source(decisions=13,sha="b")))
    assert reduction_evidence(measured,lower)["comparable"]
    assert measure_snapshot(raw)==measured
    raw["files"].reverse()
    assert measure_snapshot(raw)==measured  # Reuse order cannot change immutable meaning.


def test_more_than_twenty_thousand_source_files_still_require_a_complete_inventory():
    raw=source(files=20001,functions=1)
    measured=measure_snapshot(pack_snapshot(raw))
    assert measured["coverage"]["eligible_files"]==20001
    assert measured["coverage"]["complete"] and measured["summary"]["decisions"]==20001
    raw["files"].pop()
    with pytest.raises(ValueError,match="Every eligible"):
        measure_snapshot(pack_snapshot(raw))


@pytest.mark.parametrize("mutation",["fingerprint","declared-size","truncated","trailing"])
def test_compression_cannot_hide_changed_truncated_or_oversized_evidence(mutation):
    import base64
    envelope=pack({"text":"x"*10000},threshold=0)
    if mutation=="fingerprint":envelope["sha256"]="0"*64
    if mutation=="declared-size":envelope["bytes"]=1
    if mutation=="truncated":envelope["data"]=envelope["data"][:-8]
    if mutation=="trailing":envelope["data"]=base64.b64encode(base64.b64decode(envelope["data"])+b"unaccounted").decode()
    with pytest.raises(ValueError):unpack(envelope,limit=20000)
