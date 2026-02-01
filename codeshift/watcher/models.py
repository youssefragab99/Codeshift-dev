"""Data models for the Deprecation Early Warning System."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path


class DeprecationSeverity(Enum):
    """Severity levels for deprecation warnings.

    Ordered from least to most severe for comparison purposes.
    """

    INFO = "info"  # Soft deprecation, alternative available
    DEPRECATED = "deprecated"  # Officially deprecated, removal not yet scheduled
    WARNING = "warning"  # Deprecated, removal planned in future version
    CRITICAL = "critical"  # Removal imminent or already in next major version

    @classmethod
    def from_string(cls, value: str) -> "DeprecationSeverity":
        """Convert string to DeprecationSeverity enum."""
        try:
            return cls(value.lower())
        except ValueError:
            raise ValueError(
                f"Invalid severity: {value}. "
                f"Must be one of: {', '.join(s.value for s in cls)}"
            )

    def __lt__(self, other: "DeprecationSeverity") -> bool:
        """Compare severities for ordering."""
        order = [self.INFO, self.DEPRECATED, self.WARNING, self.CRITICAL]
        return order.index(self) < order.index(other)

    def __le__(self, other: "DeprecationSeverity") -> bool:
        return self == other or self < other

    def __gt__(self, other: "DeprecationSeverity") -> bool:
        return not self <= other

    def __ge__(self, other: "DeprecationSeverity") -> bool:
        return not self < other


class PatternType(Enum):
    """Types of patterns that can be matched."""

    REGEX = "regex"  # Simple regex pattern matching
    DECORATOR = "decorator"  # AST-based decorator matching
    METHOD_CALL = "method_call"  # AST-based method call matching
    CLASS_DEFINITION = "class_definition"  # AST-based class definition matching
    IMPORT = "import"  # Import statement matching
    ATTRIBUTE = "attribute"  # Attribute access matching


@dataclass
class ReleaseCycle:
    """Release cycle metadata for timeline estimation."""

    typical_major_interval_months: int = 24  # Default: ~2 years between majors
    current_version: str | None = None
    next_major_estimated: str | None = None  # e.g., "2025-Q4" or "2025-06"

    def estimate_removal_date(self, removed_in: str | None) -> str | None:
        """Estimate when a deprecated feature will be removed.

        Returns a human-readable estimate like "~12 months" or "Q4 2025".
        """
        if self.next_major_estimated and removed_in:
            return f"Expected {self.next_major_estimated}"
        elif self.typical_major_interval_months:
            return f"~{self.typical_major_interval_months} months (estimated)"
        return None


@dataclass
class DeprecationPattern:
    """A single deprecation pattern to match against code."""

    id: str  # Unique identifier, e.g., "pydantic-config-class"
    library: str  # e.g., "pydantic"
    pattern: str  # Regex or AST pattern to match
    pattern_type: PatternType  # Type of pattern matching to use
    message: str  # Human-readable warning message
    severity: DeprecationSeverity
    deprecated_in: str  # Version deprecated, e.g., "2.0"
    removed_in: str | None = None  # Version to be removed, e.g., "3.0"
    removal_estimated: str | None = None  # Manual override, e.g., "2025-06"
    context: str | None = None  # Additional context (e.g., "inside BaseModel subclass")
    replacement: str | None = None  # Suggested replacement code/pattern
    link: str | None = None  # Documentation link
    auto_fixable: bool = False  # Can Codeshift auto-fix this?
    transform_name: str | None = None  # Reference to existing transform if auto-fixable

    def get_timeline_estimate(self, release_cycle: ReleaseCycle | None = None) -> str | None:
        """Get estimated timeline to removal."""
        if self.removal_estimated:
            return f"Expected {self.removal_estimated}"
        if self.removed_in and release_cycle:
            return release_cycle.estimate_removal_date(self.removed_in)
        if self.removed_in:
            return f"Removed in v{self.removed_in}"
        return None


@dataclass
class DeprecationMatch:
    """A matched deprecation found in user code."""

    pattern: DeprecationPattern
    file_path: Path
    line_number: int
    matched_code: str  # The actual code that matched
    column: int | None = None
    context_lines: list[str] = field(default_factory=list)  # Surrounding code

    @property
    def location(self) -> str:
        """Get file:line location string."""
        return f"{self.file_path}:{self.line_number}"

    @property
    def severity(self) -> DeprecationSeverity:
        """Convenience property for accessing pattern severity."""
        return self.pattern.severity

    @property
    def library(self) -> str:
        """Convenience property for accessing pattern library."""
        return self.pattern.library


@dataclass
class DeprecationScanResult:
    """Result of scanning a project for deprecations."""

    project_path: Path
    scanned_at: datetime
    files_scanned: int
    matches: list[DeprecationMatch]
    release_cycles: dict[str, ReleaseCycle] = field(default_factory=dict)

    @property
    def total_count(self) -> int:
        """Total number of deprecation matches."""
        return len(self.matches)

    @property
    def critical_count(self) -> int:
        """Count of critical severity matches."""
        return sum(1 for m in self.matches if m.severity == DeprecationSeverity.CRITICAL)

    @property
    def warning_count(self) -> int:
        """Count of warning severity matches."""
        return sum(1 for m in self.matches if m.severity == DeprecationSeverity.WARNING)

    @property
    def deprecated_count(self) -> int:
        """Count of deprecated severity matches."""
        return sum(1 for m in self.matches if m.severity == DeprecationSeverity.DEPRECATED)

    @property
    def info_count(self) -> int:
        """Count of info severity matches."""
        return sum(1 for m in self.matches if m.severity == DeprecationSeverity.INFO)

    @property
    def auto_fixable_count(self) -> int:
        """Count of matches that can be auto-fixed."""
        return sum(1 for m in self.matches if m.pattern.auto_fixable)

    def by_severity(self) -> dict[DeprecationSeverity, list[DeprecationMatch]]:
        """Group matches by severity."""
        result: dict[DeprecationSeverity, list[DeprecationMatch]] = {
            severity: [] for severity in DeprecationSeverity
        }
        for match in self.matches:
            result[match.severity].append(match)
        return result

    def by_library(self) -> dict[str, list[DeprecationMatch]]:
        """Group matches by library."""
        result: dict[str, list[DeprecationMatch]] = {}
        for match in self.matches:
            if match.library not in result:
                result[match.library] = []
            result[match.library].append(match)
        return result

    def by_file(self) -> dict[Path, list[DeprecationMatch]]:
        """Group matches by file path."""
        result: dict[Path, list[DeprecationMatch]] = {}
        for match in self.matches:
            if match.file_path not in result:
                result[match.file_path] = []
            result[match.file_path].append(match)
        return result

    def filter_by_severity(
        self, min_severity: DeprecationSeverity
    ) -> list[DeprecationMatch]:
        """Filter matches to only include those at or above the given severity."""
        return [m for m in self.matches if m.severity >= min_severity]

    def filter_by_library(self, libraries: list[str]) -> list[DeprecationMatch]:
        """Filter matches to only include those from the given libraries."""
        return [m for m in self.matches if m.library in libraries]

    def has_severity_at_or_above(self, severity: DeprecationSeverity) -> bool:
        """Check if any matches are at or above the given severity."""
        return any(m.severity >= severity for m in self.matches)

    def to_dict(self) -> dict:
        """Export as dictionary for JSON serialization."""
        return {
            "scan_time": self.scanned_at.isoformat(),
            "project_path": str(self.project_path),
            "files_scanned": self.files_scanned,
            "summary": {
                "critical": self.critical_count,
                "warning": self.warning_count,
                "deprecated": self.deprecated_count,
                "info": self.info_count,
                "total": self.total_count,
                "auto_fixable": self.auto_fixable_count,
            },
            "findings": [
                {
                    "id": m.pattern.id,
                    "library": m.library,
                    "severity": m.severity.value,
                    "file": str(m.file_path),
                    "line": m.line_number,
                    "column": m.column,
                    "message": m.pattern.message,
                    "deprecated_in": m.pattern.deprecated_in,
                    "removed_in": m.pattern.removed_in,
                    "timeline_estimate": m.pattern.get_timeline_estimate(
                        self.release_cycles.get(m.library)
                    ),
                    "replacement": m.pattern.replacement,
                    "link": m.pattern.link,
                    "auto_fixable": m.pattern.auto_fixable,
                    "matched_code": m.matched_code,
                }
                for m in self.matches
            ],
        }
