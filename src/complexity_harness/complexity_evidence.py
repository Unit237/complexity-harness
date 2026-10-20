"""Bounded, lossless transport for immutable source evidence (never executable)."""
import base64
import gzip
import hashlib
import json
import zlib

ENCODING = "complexity-gzip-json-v1"
MAX_RECEIPT_BYTES = 12 * 1024 * 1024
MAX_EXPANDED_BYTES = 256 * 1024 * 1024
MAX_FILE_EVIDENCE_BYTES = 16 * 1024 * 1024


def pack(payload, *, threshold=4096, limit=MAX_EXPANDED_BYTES):
    raw = json.dumps(payload, separators=(",",":"), sort_keys=True).encode()
    if len(raw)>limit:
        raise ValueError("Complexity evidence exceeds its expanded byte budget")
    if len(raw)<=threshold:
        return payload
    return {"encoding":ENCODING,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),
        "data":base64.b64encode(gzip.compress(raw,compresslevel=6,mtime=0)).decode()}


def unpack(payload, *, limit=MAX_EXPANDED_BYTES):
    if not isinstance(payload,dict):
        raise ValueError("Complexity evidence must be an object")
    if "encoding" not in payload:
        return payload
    if (payload.get("encoding")!=ENCODING or type(payload.get("bytes")) is not int
            or not 0<=payload["bytes"]<=limit or not isinstance(payload.get("data"),str)
            or len(payload["data"])>2*limit):
        raise ValueError("Complexity evidence encoding or expanded size is invalid")
    try:
        compressed=base64.b64decode(payload["data"],validate=True)
        reader=zlib.decompressobj(wbits=31)
        raw=reader.decompress(compressed,payload["bytes"]+1)
        if (len(raw)!=payload["bytes"] or not reader.eof or reader.unused_data
                or hashlib.sha256(raw).hexdigest()!=payload.get("sha256")):
            raise ValueError("Complexity evidence is incomplete or its fingerprint changed")
        result=json.loads(raw)
        if not isinstance(result,dict) or "encoding" in result:
            raise ValueError("Nested or non-object evidence envelopes are invalid")
        return result
    except (zlib.error,UnicodeDecodeError,json.JSONDecodeError) as exc:
        raise ValueError("Complexity evidence is malformed") from exc


def pack_file(row):
    if row.get("evidence") is not None:
        return row
    body={key:row[key] for key in ("functions","unattributed_branches") if key in row}
    encoded=pack(body,limit=MAX_FILE_EVIDENCE_BYTES)
    if encoded is body:
        return row
    return {**{k:v for k,v in row.items() if k not in body},"evidence":encoded,
        "function_count":len(row.get("functions",[]))}


def unpack_file(row):
    if "evidence" not in row:
        return row
    if "functions" in row or "unattributed_branches" in row:
        raise ValueError("A file cannot contain conflicting evidence forms")
    body=unpack(row["evidence"],limit=MAX_FILE_EVIDENCE_BYTES)
    if (set(body)!={"functions","unattributed_branches"} or not isinstance(body["functions"],list)
            or type(row.get("function_count")) is not int
            or row.get("function_count")!=len(body["functions"])):
        raise ValueError("Compressed file evidence must conserve its function inventory")
    return {**{k:v for k,v in row.items() if k not in {"evidence","function_count"}},**body}


def pack_snapshot(snapshot):
    snapshot=unpack(snapshot)
    payload={**snapshot,"files":[pack_file(row) for row in snapshot["files"]]}
    return pack(payload)
