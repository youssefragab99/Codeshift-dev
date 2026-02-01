"""Tests for deprecation database loader."""

import pytest

from codeshift.watcher.deprecation_db.loader import DeprecationDBLoader
from codeshift.watcher.models import DeprecationPattern, DeprecationSeverity, PatternType


class TestDeprecationDBLoader:
    """Tests for DeprecationDBLoader."""

    def setup_method(self):
        """Clear cache before each test."""
        DeprecationDBLoader.clear_cache()

    def test_get_supported_libraries(self):
        """Test getting list of supported libraries."""
        libraries = DeprecationDBLoader.get_supported_libraries()
        assert isinstance(libraries, list)
        assert len(libraries) > 0
        assert "pydantic" in libraries
        assert "sqlalchemy" in libraries

    def test_load_pydantic(self):
        """Test loading pydantic deprecations."""
        patterns = DeprecationDBLoader.load("pydantic")
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert all(isinstance(p, DeprecationPattern) for p in patterns)
        assert all(p.library == "pydantic" for p in patterns)

    def test_load_sqlalchemy(self):
        """Test loading sqlalchemy deprecations."""
        patterns = DeprecationDBLoader.load("sqlalchemy")
        assert isinstance(patterns, list)
        assert len(patterns) > 0
        assert all(p.library == "sqlalchemy" for p in patterns)

    def test_load_nonexistent_library(self):
        """Test loading nonexistent library raises error."""
        with pytest.raises(FileNotFoundError):
            DeprecationDBLoader.load("nonexistent_library")

    def test_load_caching(self):
        """Test that patterns are cached."""
        patterns1 = DeprecationDBLoader.load("pydantic")
        patterns2 = DeprecationDBLoader.load("pydantic")
        assert patterns1 is patterns2  # Same object due to caching

    def test_clear_cache(self):
        """Test clearing the cache."""
        patterns1 = DeprecationDBLoader.load("pydantic")
        DeprecationDBLoader.clear_cache()
        patterns2 = DeprecationDBLoader.load("pydantic")
        assert patterns1 is not patterns2  # Different objects after cache clear

    def test_load_all(self):
        """Test loading all deprecations."""
        all_patterns = DeprecationDBLoader.load_all()
        assert isinstance(all_patterns, dict)
        assert "pydantic" in all_patterns
        assert "sqlalchemy" in all_patterns
        assert all(isinstance(v, list) for v in all_patterns.values())

    def test_load_release_cycle(self):
        """Test loading release cycle metadata."""
        cycle = DeprecationDBLoader.load_release_cycle("pydantic")
        assert cycle is not None
        assert cycle.typical_major_interval_months > 0

    def test_load_release_cycle_nonexistent(self):
        """Test loading release cycle for nonexistent library."""
        cycle = DeprecationDBLoader.load_release_cycle("nonexistent")
        assert cycle is None

    def test_pattern_structure(self):
        """Test that loaded patterns have correct structure."""
        patterns = DeprecationDBLoader.load("pydantic")

        for pattern in patterns:
            # Required fields
            assert pattern.id
            assert pattern.library == "pydantic"
            assert pattern.pattern
            assert isinstance(pattern.pattern_type, PatternType)
            assert pattern.message
            assert isinstance(pattern.severity, DeprecationSeverity)
            assert pattern.deprecated_in

            # Optional fields should have correct types
            if pattern.removed_in:
                assert isinstance(pattern.removed_in, str)
            if pattern.replacement:
                assert isinstance(pattern.replacement, str)
            if pattern.link:
                assert isinstance(pattern.link, str)
            assert isinstance(pattern.auto_fixable, bool)

    def test_all_libraries_load_successfully(self):
        """Test that all supported libraries can be loaded."""
        libraries = DeprecationDBLoader.get_supported_libraries()

        for lib in libraries:
            try:
                patterns = DeprecationDBLoader.load(lib)
                assert isinstance(patterns, list)
                assert len(patterns) > 0, f"{lib} has no patterns"
            except Exception as e:
                pytest.fail(f"Failed to load {lib}: {e}")

    def test_severity_distribution(self):
        """Test that patterns have varied severities."""
        patterns = DeprecationDBLoader.load("pydantic")
        severities = set(p.severity for p in patterns)

        # Should have at least 2 different severity levels
        assert len(severities) >= 2

    def test_pattern_types_distribution(self):
        """Test that patterns use various pattern types."""
        patterns = DeprecationDBLoader.load("pydantic")
        pattern_types = set(p.pattern_type for p in patterns)

        # Should have at least 2 different pattern types
        assert len(pattern_types) >= 2
