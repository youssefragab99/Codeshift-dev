"""Loader for deprecation database YAML files."""

from pathlib import Path
from typing import Any

import yaml

from codeshift.watcher.models import (
    DeprecationPattern,
    DeprecationSeverity,
    PatternType,
    ReleaseCycle,
)


class DeprecationDBLoader:
    """Load and cache deprecation patterns from YAML files."""

    _pattern_cache: dict[str, list[DeprecationPattern]] = {}
    _release_cycle_cache: dict[str, ReleaseCycle] = {}

    @classmethod
    def get_db_path(cls) -> Path:
        """Return path to deprecation_db directory."""
        return Path(__file__).parent

    @classmethod
    def get_supported_libraries(cls) -> list[str]:
        """List all libraries with deprecation data."""
        db_path = cls.get_db_path()
        return sorted(
            f.stem for f in db_path.glob("*.yaml") if f.stem != "__init__"
        )

    @classmethod
    def load(cls, library: str) -> list[DeprecationPattern]:
        """Load deprecation patterns for a library.

        Args:
            library: Name of the library (e.g., "pydantic")

        Returns:
            List of DeprecationPattern objects

        Raises:
            FileNotFoundError: If no deprecation data exists for the library
            ValueError: If the YAML file is malformed
        """
        if library in cls._pattern_cache:
            return cls._pattern_cache[library]

        yaml_path = cls.get_db_path() / f"{library}.yaml"
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"No deprecation data found for library: {library}"
            )

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty or invalid YAML file: {yaml_path}")

        patterns = cls._parse_patterns(data, library)
        cls._pattern_cache[library] = patterns

        # Also cache release cycle info
        if "release_cycle" in data:
            cls._release_cycle_cache[library] = cls._parse_release_cycle(
                data["release_cycle"]
            )

        return patterns

    @classmethod
    def load_release_cycle(cls, library: str) -> ReleaseCycle | None:
        """Load release cycle metadata for a library.

        Args:
            library: Name of the library

        Returns:
            ReleaseCycle object or None if not available
        """
        if library in cls._release_cycle_cache:
            return cls._release_cycle_cache[library]

        # Try loading the library to populate the cache
        try:
            cls.load(library)
            return cls._release_cycle_cache.get(library)
        except FileNotFoundError:
            return None

    @classmethod
    def load_all(cls) -> dict[str, list[DeprecationPattern]]:
        """Load all deprecation patterns from all libraries.

        Returns:
            Dictionary mapping library names to their deprecation patterns
        """
        result: dict[str, list[DeprecationPattern]] = {}
        for library in cls.get_supported_libraries():
            try:
                result[library] = cls.load(library)
            except (FileNotFoundError, ValueError):
                # Skip libraries with invalid/missing data
                continue
        return result

    @classmethod
    def load_all_release_cycles(cls) -> dict[str, ReleaseCycle]:
        """Load all release cycle metadata.

        Returns:
            Dictionary mapping library names to their release cycles
        """
        # Ensure all libraries are loaded
        cls.load_all()
        return cls._release_cycle_cache.copy()

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached data."""
        cls._pattern_cache.clear()
        cls._release_cycle_cache.clear()

    @classmethod
    def _parse_patterns(
        cls, data: dict[str, Any], library: str
    ) -> list[DeprecationPattern]:
        """Parse deprecation patterns from YAML data."""
        patterns: list[DeprecationPattern] = []

        deprecations = data.get("deprecations", [])
        if not isinstance(deprecations, list):
            raise ValueError(f"'deprecations' must be a list in {library}.yaml")

        for item in deprecations:
            try:
                pattern = cls._parse_single_pattern(item, library)
                patterns.append(pattern)
            except (KeyError, ValueError) as e:
                # Log warning but continue parsing other patterns
                import warnings

                warnings.warn(
                    f"Skipping invalid deprecation pattern in {library}.yaml: {e}"
                )
                continue

        return patterns

    @classmethod
    def _parse_single_pattern(
        cls, item: dict[str, Any], library: str
    ) -> DeprecationPattern:
        """Parse a single deprecation pattern from YAML data."""
        # Required fields
        pattern_id = item.get("id")
        if not pattern_id:
            raise KeyError("Missing required field 'id'")

        pattern = item.get("pattern")
        if not pattern:
            raise KeyError(f"Missing required field 'pattern' in {pattern_id}")

        pattern_type_str = item.get("pattern_type", "regex")
        try:
            pattern_type = PatternType(pattern_type_str)
        except ValueError:
            raise ValueError(
                f"Invalid pattern_type '{pattern_type_str}' in {pattern_id}"
            )

        message = item.get("message")
        if not message:
            raise KeyError(f"Missing required field 'message' in {pattern_id}")

        severity_str = item.get("severity", "info")
        try:
            severity = DeprecationSeverity.from_string(severity_str)
        except ValueError:
            raise ValueError(
                f"Invalid severity '{severity_str}' in {pattern_id}"
            )

        deprecated_in = item.get("deprecated_in")
        if not deprecated_in:
            raise KeyError(f"Missing required field 'deprecated_in' in {pattern_id}")

        return DeprecationPattern(
            id=pattern_id,
            library=library,
            pattern=pattern,
            pattern_type=pattern_type,
            message=message,
            severity=severity,
            deprecated_in=str(deprecated_in),
            removed_in=str(item["removed_in"]) if item.get("removed_in") else None,
            removal_estimated=item.get("removal_estimated"),
            context=item.get("context"),
            replacement=item.get("replacement"),
            link=item.get("link"),
            auto_fixable=item.get("auto_fixable", False),
            transform_name=item.get("transform_name"),
        )

    @classmethod
    def _parse_release_cycle(cls, data: dict[str, Any]) -> ReleaseCycle:
        """Parse release cycle metadata from YAML data."""
        return ReleaseCycle(
            typical_major_interval_months=data.get(
                "typical_major_interval_months", 24
            ),
            current_version=data.get("current_version"),
            next_major_estimated=data.get("next_major_estimated"),
        )
