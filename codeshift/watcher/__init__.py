"""Deprecation Early Warning System for Codeshift.

This module provides proactive detection of deprecated patterns in code,
allowing teams to plan migrations before breaking changes occur.
"""

from codeshift.watcher.models import (
    DeprecationMatch,
    DeprecationPattern,
    DeprecationScanResult,
    DeprecationSeverity,
    PatternType,
    ReleaseCycle,
)

__all__ = [
    "DeprecationSeverity",
    "PatternType",
    "ReleaseCycle",
    "DeprecationPattern",
    "DeprecationMatch",
    "DeprecationScanResult",
]
