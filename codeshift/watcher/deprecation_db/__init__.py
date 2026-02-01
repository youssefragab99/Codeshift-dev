"""Deprecation database for Codeshift.

Contains YAML-based deprecation patterns for various Python libraries.
"""

from codeshift.watcher.deprecation_db.loader import DeprecationDBLoader

__all__ = ["DeprecationDBLoader"]
