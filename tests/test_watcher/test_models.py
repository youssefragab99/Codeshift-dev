"""Tests for watcher models."""

from datetime import datetime
from pathlib import Path

import pytest

from codeshift.watcher.models import (
    DeprecationMatch,
    DeprecationPattern,
    DeprecationScanResult,
    DeprecationSeverity,
    PatternType,
    ReleaseCycle,
)


class TestDeprecationSeverity:
    """Tests for DeprecationSeverity enum."""

    def test_severity_values(self):
        """Test that all severity values are correct."""
        assert DeprecationSeverity.INFO.value == "info"
        assert DeprecationSeverity.DEPRECATED.value == "deprecated"
        assert DeprecationSeverity.WARNING.value == "warning"
        assert DeprecationSeverity.CRITICAL.value == "critical"

    def test_from_string(self):
        """Test creating severity from string."""
        assert DeprecationSeverity.from_string("info") == DeprecationSeverity.INFO
        assert DeprecationSeverity.from_string("INFO") == DeprecationSeverity.INFO
        assert DeprecationSeverity.from_string("critical") == DeprecationSeverity.CRITICAL

    def test_from_string_invalid(self):
        """Test that invalid severity raises ValueError."""
        with pytest.raises(ValueError):
            DeprecationSeverity.from_string("invalid")

    def test_severity_comparison(self):
        """Test severity comparison operators."""
        assert DeprecationSeverity.INFO < DeprecationSeverity.DEPRECATED
        assert DeprecationSeverity.DEPRECATED < DeprecationSeverity.WARNING
        assert DeprecationSeverity.WARNING < DeprecationSeverity.CRITICAL
        assert DeprecationSeverity.CRITICAL > DeprecationSeverity.INFO
        assert DeprecationSeverity.INFO <= DeprecationSeverity.INFO
        assert DeprecationSeverity.CRITICAL >= DeprecationSeverity.WARNING


class TestPatternType:
    """Tests for PatternType enum."""

    def test_pattern_type_values(self):
        """Test that all pattern types are defined."""
        assert PatternType.REGEX.value == "regex"
        assert PatternType.DECORATOR.value == "decorator"
        assert PatternType.METHOD_CALL.value == "method_call"
        assert PatternType.CLASS_DEFINITION.value == "class_definition"
        assert PatternType.IMPORT.value == "import"
        assert PatternType.ATTRIBUTE.value == "attribute"


class TestReleaseCycle:
    """Tests for ReleaseCycle dataclass."""

    def test_default_values(self):
        """Test default release cycle values."""
        cycle = ReleaseCycle()
        assert cycle.typical_major_interval_months == 24
        assert cycle.current_version is None
        assert cycle.next_major_estimated is None

    def test_estimate_removal_date_with_next_major(self):
        """Test timeline estimation with known next major."""
        cycle = ReleaseCycle(
            typical_major_interval_months=24,
            current_version="2.0",
            next_major_estimated="2025-Q4",
        )
        estimate = cycle.estimate_removal_date("3.0")
        assert "2025-Q4" in estimate

    def test_estimate_removal_date_with_interval(self):
        """Test timeline estimation from interval."""
        cycle = ReleaseCycle(typical_major_interval_months=18)
        estimate = cycle.estimate_removal_date("3.0")
        assert "18 months" in estimate


class TestDeprecationPattern:
    """Tests for DeprecationPattern dataclass."""

    def test_pattern_creation(self):
        """Test creating a deprecation pattern."""
        pattern = DeprecationPattern(
            id="test-pattern",
            library="test",
            pattern=".dict(",
            pattern_type=PatternType.METHOD_CALL,
            message="Test message",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
            removed_in="3.0",
        )
        assert pattern.id == "test-pattern"
        assert pattern.library == "test"
        assert pattern.severity == DeprecationSeverity.WARNING
        assert pattern.auto_fixable is False

    def test_get_timeline_estimate(self):
        """Test getting timeline estimate."""
        pattern = DeprecationPattern(
            id="test-pattern",
            library="test",
            pattern=".dict(",
            pattern_type=PatternType.METHOD_CALL,
            message="Test message",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
            removed_in="3.0",
        )
        cycle = ReleaseCycle(next_major_estimated="2025-Q4")
        estimate = pattern.get_timeline_estimate(cycle)
        assert estimate is not None
        assert "2025" in estimate

    def test_get_timeline_estimate_with_removal_estimated(self):
        """Test timeline with manual removal estimate."""
        pattern = DeprecationPattern(
            id="test-pattern",
            library="test",
            pattern=".dict(",
            pattern_type=PatternType.METHOD_CALL,
            message="Test message",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
            removal_estimated="2025-06",
        )
        estimate = pattern.get_timeline_estimate(None)
        assert "2025-06" in estimate


class TestDeprecationMatch:
    """Tests for DeprecationMatch dataclass."""

    def test_match_creation(self):
        """Test creating a deprecation match."""
        pattern = DeprecationPattern(
            id="test-pattern",
            library="pydantic",
            pattern=".dict(",
            pattern_type=PatternType.METHOD_CALL,
            message="Test message",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
        )
        match = DeprecationMatch(
            pattern=pattern,
            file_path=Path("/test/file.py"),
            line_number=42,
            matched_code=".dict()",
        )
        assert match.line_number == 42
        assert match.severity == DeprecationSeverity.WARNING
        assert match.library == "pydantic"

    def test_location_property(self):
        """Test location property."""
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="test",
            pattern_type=PatternType.REGEX,
            message="Test",
            severity=DeprecationSeverity.INFO,
            deprecated_in="1.0",
        )
        match = DeprecationMatch(
            pattern=pattern,
            file_path=Path("/test/file.py"),
            line_number=10,
            matched_code="test",
        )
        assert match.location == "/test/file.py:10"


class TestDeprecationScanResult:
    """Tests for DeprecationScanResult dataclass."""

    @pytest.fixture
    def sample_patterns(self):
        """Create sample patterns for testing."""
        return [
            DeprecationPattern(
                id="critical-1",
                library="lib1",
                pattern="test1",
                pattern_type=PatternType.REGEX,
                message="Critical issue",
                severity=DeprecationSeverity.CRITICAL,
                deprecated_in="1.0",
            ),
            DeprecationPattern(
                id="warning-1",
                library="lib1",
                pattern="test2",
                pattern_type=PatternType.REGEX,
                message="Warning issue",
                severity=DeprecationSeverity.WARNING,
                deprecated_in="1.0",
                auto_fixable=True,
            ),
            DeprecationPattern(
                id="info-1",
                library="lib2",
                pattern="test3",
                pattern_type=PatternType.REGEX,
                message="Info issue",
                severity=DeprecationSeverity.INFO,
                deprecated_in="1.0",
            ),
        ]

    @pytest.fixture
    def sample_result(self, sample_patterns):
        """Create sample scan result."""
        matches = [
            DeprecationMatch(
                pattern=sample_patterns[0],
                file_path=Path("/test/file1.py"),
                line_number=10,
                matched_code="test1",
            ),
            DeprecationMatch(
                pattern=sample_patterns[1],
                file_path=Path("/test/file1.py"),
                line_number=20,
                matched_code="test2",
            ),
            DeprecationMatch(
                pattern=sample_patterns[2],
                file_path=Path("/test/file2.py"),
                line_number=5,
                matched_code="test3",
            ),
        ]
        return DeprecationScanResult(
            project_path=Path("/test"),
            scanned_at=datetime.now(),
            files_scanned=10,
            matches=matches,
        )

    def test_total_count(self, sample_result):
        """Test total count property."""
        assert sample_result.total_count == 3

    def test_severity_counts(self, sample_result):
        """Test severity count properties."""
        assert sample_result.critical_count == 1
        assert sample_result.warning_count == 1
        assert sample_result.info_count == 1
        assert sample_result.deprecated_count == 0

    def test_auto_fixable_count(self, sample_result):
        """Test auto-fixable count."""
        assert sample_result.auto_fixable_count == 1

    def test_by_severity(self, sample_result):
        """Test grouping by severity."""
        by_severity = sample_result.by_severity()
        assert len(by_severity[DeprecationSeverity.CRITICAL]) == 1
        assert len(by_severity[DeprecationSeverity.WARNING]) == 1
        assert len(by_severity[DeprecationSeverity.INFO]) == 1

    def test_by_library(self, sample_result):
        """Test grouping by library."""
        by_library = sample_result.by_library()
        assert len(by_library["lib1"]) == 2
        assert len(by_library["lib2"]) == 1

    def test_by_file(self, sample_result):
        """Test grouping by file."""
        by_file = sample_result.by_file()
        assert len(by_file[Path("/test/file1.py")]) == 2
        assert len(by_file[Path("/test/file2.py")]) == 1

    def test_filter_by_severity(self, sample_result):
        """Test filtering by severity."""
        filtered = sample_result.filter_by_severity(DeprecationSeverity.WARNING)
        assert len(filtered) == 2  # WARNING and CRITICAL

    def test_has_severity_at_or_above(self, sample_result):
        """Test severity check."""
        assert sample_result.has_severity_at_or_above(DeprecationSeverity.CRITICAL)
        assert sample_result.has_severity_at_or_above(DeprecationSeverity.INFO)

    def test_to_dict(self, sample_result):
        """Test JSON serialization."""
        data = sample_result.to_dict()
        assert "scan_time" in data
        assert "project_path" in data
        assert "files_scanned" in data
        assert "summary" in data
        assert "findings" in data
        assert data["summary"]["total"] == 3
        assert len(data["findings"]) == 3
