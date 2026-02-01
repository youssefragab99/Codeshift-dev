"""Scanner for detecting deprecated patterns in code."""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from codeshift.utils.config import ProjectConfig
from codeshift.watcher.deprecation_db.loader import DeprecationDBLoader
from codeshift.watcher.models import (
    DeprecationMatch,
    DeprecationPattern,
    DeprecationScanResult,
    DeprecationSeverity,
    PatternType,
    ReleaseCycle,
)


@dataclass
class MatchLocation:
    """Location of a pattern match in source code."""

    line_number: int
    column: int | None
    matched_code: str
    context_lines: list[str]


class PatternMatcher(ABC):
    """Base class for pattern matching strategies."""

    @abstractmethod
    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        """Find all matches of the pattern in code.

        Args:
            code: Source code to search
            pattern: Deprecation pattern to match
            file_path: Path to the file being scanned

        Returns:
            List of match locations
        """
        pass

    def _get_context_lines(
        self, lines: list[str], line_number: int, context: int = 2
    ) -> list[str]:
        """Get surrounding context lines."""
        start = max(0, line_number - context - 1)
        end = min(len(lines), line_number + context)
        return lines[start:end]


class RegexMatcher(PatternMatcher):
    """Simple regex-based pattern matching."""

    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        matches: list[MatchLocation] = []
        lines = code.splitlines()

        # Escape special regex chars if pattern doesn't look like a regex
        search_pattern = pattern.pattern
        if not any(c in search_pattern for c in r".*+?^$[]{}|\()"):
            search_pattern = re.escape(search_pattern)

        try:
            regex = re.compile(search_pattern)
        except re.error:
            # Invalid regex, try as literal
            regex = re.compile(re.escape(pattern.pattern))

        for i, line in enumerate(lines):
            for match in regex.finditer(line):
                matches.append(
                    MatchLocation(
                        line_number=i + 1,
                        column=match.start() + 1,
                        matched_code=match.group(),
                        context_lines=self._get_context_lines(lines, i + 1),
                    )
                )

        return matches


class ImportMatcher(PatternMatcher):
    """Import statement matching using regex for reliability."""

    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        # Use regex-based matching for imports (more reliable)
        return RegexMatcher().match(code, pattern, file_path)


class DecoratorMatcher(PatternMatcher):
    """Decorator matching using regex for reliability."""

    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        # Use regex-based matching for decorators
        return RegexMatcher().match(code, pattern, file_path)


class MethodCallMatcher(PatternMatcher):
    """Method call matching using regex for reliability."""

    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        # Use regex-based matching for method calls
        return RegexMatcher().match(code, pattern, file_path)


class ClassDefinitionMatcher(PatternMatcher):
    """Class definition matching using regex for reliability."""

    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        # Use regex-based matching for class definitions
        return RegexMatcher().match(code, pattern, file_path)


class AttributeMatcher(PatternMatcher):
    """Attribute access matching using regex for reliability."""

    def match(
        self, code: str, pattern: DeprecationPattern, file_path: Path
    ) -> list[MatchLocation]:
        # Use regex-based matching for attribute access
        return RegexMatcher().match(code, pattern, file_path)


class DeprecationScanner:
    """Scan codebase for deprecated patterns."""

    def __init__(self, project_path: Path, config: ProjectConfig | None = None):
        """Initialize the scanner.

        Args:
            project_path: Root path of the project to scan
            config: Project configuration (optional)
        """
        self.project_path = project_path
        self.config = config or ProjectConfig.from_pyproject(project_path)
        self.matchers = self._init_matchers()

    def _init_matchers(self) -> dict[PatternType, PatternMatcher]:
        """Initialize pattern matchers by type."""
        return {
            PatternType.REGEX: RegexMatcher(),
            PatternType.IMPORT: ImportMatcher(),
            PatternType.DECORATOR: DecoratorMatcher(),
            PatternType.METHOD_CALL: MethodCallMatcher(),
            PatternType.CLASS_DEFINITION: ClassDefinitionMatcher(),
            PatternType.ATTRIBUTE: AttributeMatcher(),
        }

    def scan_file(
        self, file_path: Path, patterns: list[DeprecationPattern]
    ) -> list[DeprecationMatch]:
        """Scan a single file for deprecation patterns.

        Args:
            file_path: Path to the Python file
            patterns: List of patterns to search for

        Returns:
            List of deprecation matches found
        """
        matches: list[DeprecationMatch] = []

        try:
            code = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            return matches

        for pattern in patterns:
            matcher = self.matchers.get(pattern.pattern_type, RegexMatcher())
            locations = matcher.match(code, pattern, file_path)

            for loc in locations:
                matches.append(
                    DeprecationMatch(
                        pattern=pattern,
                        file_path=file_path,
                        line_number=loc.line_number,
                        column=loc.column,
                        matched_code=loc.matched_code,
                        context_lines=loc.context_lines,
                    )
                )

        return matches

    def scan_project(
        self,
        libraries: list[str] | None = None,
        severity_filter: list[DeprecationSeverity] | None = None,
    ) -> DeprecationScanResult:
        """Scan entire project for deprecations.

        Args:
            libraries: Limit scan to specific libraries (default: all)
            severity_filter: Only return matches of these severities

        Returns:
            DeprecationScanResult with all findings
        """
        # Get Python files
        python_files = self._get_python_files()

        # Load patterns
        if libraries:
            patterns: list[DeprecationPattern] = []
            for lib in libraries:
                try:
                    patterns.extend(DeprecationDBLoader.load(lib))
                except FileNotFoundError:
                    continue
        else:
            # Detect which libraries are used and load those patterns
            used_libraries = self._detect_used_libraries(python_files)
            patterns = []
            for lib in used_libraries:
                try:
                    patterns.extend(DeprecationDBLoader.load(lib))
                except FileNotFoundError:
                    continue

        # Apply severity filter to patterns
        if severity_filter:
            patterns = [p for p in patterns if p.severity in severity_filter]

        # Scan all files
        all_matches: list[DeprecationMatch] = []
        for file_path in python_files:
            file_matches = self.scan_file(file_path, patterns)
            all_matches.extend(file_matches)

        # Load release cycles
        release_cycles: dict[str, ReleaseCycle] = {}
        matched_libraries = set(m.library for m in all_matches)
        for lib in matched_libraries:
            cycle = DeprecationDBLoader.load_release_cycle(lib)
            if cycle:
                release_cycles[lib] = cycle

        return DeprecationScanResult(
            project_path=self.project_path,
            scanned_at=datetime.now(),
            files_scanned=len(python_files),
            matches=all_matches,
            release_cycles=release_cycles,
        )

    def _get_python_files(self) -> list[Path]:
        """Get all Python files respecting exclusion patterns."""
        python_files: list[Path] = []

        for file_path in self.project_path.rglob("*.py"):
            # Check exclusion patterns
            relative_path = str(file_path.relative_to(self.project_path))
            excluded = False
            for pattern in self.config.exclude:
                if _match_glob_pattern(relative_path, pattern):
                    excluded = True
                    break

            if not excluded:
                python_files.append(file_path)

        return python_files

    def _detect_used_libraries(self, python_files: list[Path]) -> list[str]:
        """Detect which libraries the project uses based on imports."""
        supported_libraries = set(DeprecationDBLoader.get_supported_libraries())
        used_libraries: set[str] = set()

        # Common import aliases
        import_aliases = {
            "pd": "pandas",
            "np": "numpy",
            "plt": "matplotlib",
            "tf": "tensorflow",
            "sk": "sklearn",
        }

        for file_path in python_files[:50]:  # Sample first 50 files for speed
            try:
                code = file_path.read_text(encoding="utf-8")
                # Simple regex-based import detection
                import_pattern = re.compile(
                    r"^(?:from|import)\s+([\w.]+)", re.MULTILINE
                )
                for match in import_pattern.finditer(code):
                    module = match.group(1).split(".")[0]
                    # Check if it's a supported library
                    if module in supported_libraries:
                        used_libraries.add(module)
                    # Check aliases
                    elif module in import_aliases:
                        lib = import_aliases[module]
                        if lib in supported_libraries:
                            used_libraries.add(lib)
            except (OSError, UnicodeDecodeError):
                continue

        return list(used_libraries)


def _match_glob_pattern(path: str, pattern: str) -> bool:
    """Match a path against a glob-like pattern."""
    import fnmatch

    # Normalize pattern
    pattern = pattern.rstrip("/")
    if pattern.endswith("/*"):
        pattern = pattern[:-2] + "/**"

    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path, pattern + "/**")
