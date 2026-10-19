"""Babel parses source as data in a bounded V8 context without host bindings.

Customer code is never evaluated. Only the shipped parser and metric visitor
execute; the source string is a JSON argument to the parser.
"""
from collections import Counter
import atexit
import hashlib
from importlib.metadata import version
from pathlib import Path
from threading import Lock
import json
import re

from .models import BranchEvidence, FileMetric, FunctionMetric

_LOCK = Lock()
_CONTEXT = None
_VENDOR = Path(__file__).with_name("vendor")


def _close_context():
    global _CONTEXT
    with _LOCK:
        context, _CONTEXT = _CONTEXT, None
        if context is not None:
            context.close()


# V8 owns an asyncio thread. Dispose it while Python's thread machinery is
# still alive, rather than waiting for module garbage collection at shutdown.
atexit.register(_close_context)


def analyze_javascript_bytes(data, *, relative_path, language):
    global _CONTEXT
    base = dict(path=relative_path, language=language, sha256=hashlib.sha256(data).hexdigest(),
                lines=len(data.splitlines()))
    try:
        from py_mini_racer import MiniRacer
        if version("mini-racer") != "0.14.1":
            raise ValueError("JavaScript runtime differs from the analysis contract")
        source = data.decode("utf-8-sig")
        base["lines"] = len(re.split(r"\r\n|[\r\n\u2028\u2029]",source))-bool(re.search(r"[\r\n\u2028\u2029]$",source)) if source else 0
        with _LOCK:
            if _CONTEXT is None:
                context = MiniRacer()
                try:
                    context.set_hard_memory_limit(256 * 1024 * 1024)
                    context.eval("var exports = {};")
                    parser = (_VENDOR / "babel_parser.js").read_bytes()
                    manifest = json.loads((_VENDOR / "babel-source.json").read_text())
                    if manifest["version"]!="7.29.8" or hashlib.sha256(parser).hexdigest()!=manifest["sha256"]:
                        raise ValueError("Bundled JavaScript parser differs from the analysis contract")
                    context.eval(parser.decode(), timeout_sec=5)
                    context.eval((_VENDOR / "javascript_metrics.js").read_text(), timeout_sec=5)
                except BaseException:
                    context.close()
                    raise
                _CONTEXT = context
            try:
                rows = _CONTEXT.call("complexityMetrics", source, language, base["lines"], timeout_sec=5)
            except Exception as exc:
                if type(exc).__name__ in {"JSOOMException","JSTimeoutException"}:
                    _CONTEXT.close()
                    _CONTEXT = None
                raise
        occurrences, functions = Counter(), []
        for row in rows:
            symbol = row["symbol"]
            occurrences[symbol] += 1
            branches = tuple(BranchEvidence(**item) for item in row["branches"])
            functions.append(FunctionMetric(symbol, occurrences[symbol], row["line"], row["end_line"],
                1 + sum(b.contribution for b in branches), branches))
        return FileMetric(**base, functions=tuple(functions))
    except Exception as exc:
        # A syntax error, missing dependency, timeout or memory limit cannot
        # publish a partial file. Do not include source-bearing parser messages.
        return FileMetric(**base, parse_error=f"JavaScript/TypeScript analysis unavailable: {type(exc).__name__}")
