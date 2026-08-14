"""Evidence-backed software complexity snapshots."""

from .scanner import scan_repository
from .workspace import scan_workspace

__all__ = ["scan_repository", "scan_workspace"]
__version__ = "0.2.0"
