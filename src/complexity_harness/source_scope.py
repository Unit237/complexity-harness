"""One eligible-source policy for local and brokered repository scans."""
from fnmatch import fnmatch
import hashlib
import json
from pathlib import Path
from .complexity_languages import EXTENSIONS, LANGUAGE_EXTENSIONS, NAMES, DATA_DIRECTORIES, GENERATED_SUFFIXES

SOURCE_SUFFIXES = set(EXTENSIONS)

DEFAULT_EXCLUDE = {
    ".git", ".venv", "venv", "node_modules", "dist", "build",
    ".build", ".spec", "coverage", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".tox",
}


def _matches_pattern(path: str, pattern: str) -> bool:
    normalized = pattern.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if not normalized:
        return False
    if normalized.endswith("/**"):
        prefix = normalized[:-3].rstrip("/")
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return fnmatch(path, normalized) or (
        normalized.startswith("**/") and fnmatch(path, normalized[3:])
    )


def _is_excluded(
    relative: Path,
    *,
    directory_names: set[str],
    patterns: set[str],
    workspace_path: str | None,
) -> bool:
    if any(part in directory_names for part in relative.parts):
        return True
    repository_relative = relative.as_posix()
    candidates = {repository_relative}
    if workspace_path:
        candidates.add(f"{workspace_path.rstrip('/')}/{repository_relative}")
    return any(
        _matches_pattern(candidate, pattern)
        for candidate in candidates
        for pattern in patterns
    )



def source_policy(config, exclude_patterns=()):
    configured = {str(value) for value in config.get("exclude") or []}
    directories = DEFAULT_EXCLUDE | {value for value in configured if "/" not in value and "*" not in value}
    patterns = {value for value in configured if value not in directories} | set(exclude_patterns)
    digest = hashlib.sha256(json.dumps({"directories": sorted(directories), "patterns": sorted(patterns), "inventory_policy": "all-files-v2", "classification_revision":3, "data_directories":sorted(DATA_DIRECTORIES), "generated_suffixes":GENERATED_SUFFIXES, "languages": LANGUAGE_EXTENSIONS, "names": NAMES}, sort_keys=True).encode()).hexdigest()
    return directories, patterns, digest


def blob_fingerprint(blob_sha):
    return hashlib.sha256(("git-blob:" + blob_sha).encode()).hexdigest()


def content_fingerprint(data):
    blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    return blob_fingerprint(blob)


def file_fingerprint(path):
    """Fingerprint large non-parsed files without loading their bodies in RAM."""
    digest=hashlib.sha1(b"blob "+str(path.stat().st_size).encode()+b"\0")
    with path.open('rb') as stream:
        while chunk:=stream.read(1024*1024):
            digest.update(chunk)
    return blob_fingerprint(digest.hexdigest())
