"""Cross-platform helpers for macOS (Apple Silicon) and Windows."""

from __future__ import annotations

import sys

IS_DARWIN = sys.platform == "darwin"
IS_WINDOWS = sys.platform == "win32"

__all__ = ["IS_DARWIN", "IS_WINDOWS"]
