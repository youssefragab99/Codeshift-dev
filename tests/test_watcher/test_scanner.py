"""Tests for deprecation scanner."""

import tempfile
from pathlib import Path

import pytest

from codeshift.watcher.models import (
    DeprecationPattern,
    DeprecationSeverity,
    PatternType,
)
from codeshift.watcher.scanner import (
    AttributeMatcher,
    ClassDefinitionMatcher,
    DecoratorMatcher,
    DeprecationScanner,
    ImportMatcher,
    MethodCallMatcher,
    RegexMatcher,
)


class TestRegexMatcher:
    """Tests for RegexMatcher."""

    def test_simple_pattern(self):
        """Test matching a simple pattern."""
        matcher = RegexMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="deprecated_func",
            pattern_type=PatternType.REGEX,
            message="Test",
            severity=DeprecationSeverity.INFO,
            deprecated_in="1.0",
        )
        code = """
def main():
    deprecated_func()
    other_func()
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) == 1
        assert matches[0].line_number == 3

    def test_multiple_matches(self):
        """Test matching multiple occurrences."""
        matcher = RegexMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern=".dict()",
            pattern_type=PatternType.REGEX,
            message="Test",
            severity=DeprecationSeverity.INFO,
            deprecated_in="1.0",
        )
        code = """
model1.dict()
model2.dict()
model3.json()
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) == 2


class TestImportMatcher:
    """Tests for ImportMatcher."""

    def test_from_import(self):
        """Test matching from imports."""
        matcher = ImportMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="from pydantic import",
            pattern_type=PatternType.IMPORT,
            message="Test",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
        )
        code = """
from pydantic import BaseModel, validator, Field

class MyModel(BaseModel):
    pass
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1

    def test_direct_import(self):
        """Test matching direct imports."""
        matcher = ImportMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="import attr",
            pattern_type=PatternType.IMPORT,
            message="Test",
            severity=DeprecationSeverity.INFO,
            deprecated_in="1.0",
        )
        code = """
import attr
import attrs

@attr.s
class MyClass:
    pass
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1


class TestDecoratorMatcher:
    """Tests for DecoratorMatcher."""

    def test_simple_decorator(self):
        """Test matching simple decorator."""
        matcher = DecoratorMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="@validator",
            pattern_type=PatternType.DECORATOR,
            message="Test",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
        )
        code = """
from pydantic import BaseModel, validator

class MyModel(BaseModel):
    name: str

    @validator('name')
    def validate_name(cls, v):
        return v.upper()
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1

    def test_decorator_with_arguments(self):
        """Test matching decorator with arguments."""
        matcher = DecoratorMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="@root_validator",
            pattern_type=PatternType.DECORATOR,
            message="Test",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
        )
        code = """
from pydantic import BaseModel, root_validator

class MyModel(BaseModel):
    x: int
    y: int

    @root_validator(pre=True)
    def check_values(cls, values):
        return values
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1


class TestMethodCallMatcher:
    """Tests for MethodCallMatcher."""

    def test_method_call(self):
        """Test matching method calls."""
        matcher = MethodCallMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern=".dict(",
            pattern_type=PatternType.METHOD_CALL,
            message="Test",
            severity=DeprecationSeverity.INFO,
            deprecated_in="2.0",
        )
        code = """
model = MyModel(name="test")
data = model.dict()
json_str = model.json()
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1

    def test_function_call(self):
        """Test matching function calls."""
        matcher = MethodCallMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="declarative_base(",
            pattern_type=PatternType.METHOD_CALL,
            message="Test",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="1.4",
        )
        code = """
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    pass
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1


class TestClassDefinitionMatcher:
    """Tests for ClassDefinitionMatcher."""

    def test_inner_class(self):
        """Test matching inner class definitions."""
        matcher = ClassDefinitionMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="class Config:",
            pattern_type=PatternType.CLASS_DEFINITION,
            context="inside BaseModel subclass",
            message="Test",
            severity=DeprecationSeverity.WARNING,
            deprecated_in="2.0",
        )
        code = """
from pydantic import BaseModel

class MyModel(BaseModel):
    name: str

    class Config:
        orm_mode = True
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1


class TestAttributeMatcher:
    """Tests for AttributeMatcher."""

    def test_attribute_access(self):
        """Test matching attribute access."""
        matcher = AttributeMatcher()
        pattern = DeprecationPattern(
            id="test",
            library="test",
            pattern="__fields__",
            pattern_type=PatternType.ATTRIBUTE,
            message="Test",
            severity=DeprecationSeverity.INFO,
            deprecated_in="2.0",
        )
        code = """
class MyModel(BaseModel):
    name: str

fields = MyModel.__fields__
print(fields)
"""
        matches = matcher.match(code, pattern, Path("test.py"))
        assert len(matches) >= 1


class TestDeprecationScanner:
    """Tests for DeprecationScanner."""

    @pytest.fixture
    def temp_project(self):
        """Create a temporary project directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            project_path = Path(tmpdir)

            # Create a Python file with deprecations
            (project_path / "models.py").write_text("""
from pydantic import BaseModel, validator

class User(BaseModel):
    name: str

    class Config:
        orm_mode = True

    @validator('name')
    def validate_name(cls, v):
        return v.upper()

    def to_dict(self):
        return self.dict()
""")

            # Create another file
            (project_path / "utils.py").write_text("""
import numpy as np

data = np.float(1.5)
""")

            # Create an excluded file
            excluded_dir = project_path / ".venv"
            excluded_dir.mkdir()
            (excluded_dir / "dep.py").write_text("""
from pydantic import validator  # Should not be scanned
""")

            yield project_path

    def test_scan_file(self, temp_project):
        """Test scanning a single file."""
        from codeshift.watcher.deprecation_db.loader import DeprecationDBLoader

        scanner = DeprecationScanner(temp_project)
        patterns = DeprecationDBLoader.load("pydantic")

        matches = scanner.scan_file(temp_project / "models.py", patterns)
        assert len(matches) > 0

    def test_scan_project(self, temp_project):
        """Test scanning entire project."""
        scanner = DeprecationScanner(temp_project)
        result = scanner.scan_project(libraries=["pydantic"])

        assert result.project_path == temp_project
        assert result.files_scanned >= 1
        assert result.total_count > 0

    def test_scan_with_library_filter(self, temp_project):
        """Test scanning with library filter."""
        scanner = DeprecationScanner(temp_project)

        # Scan only numpy
        result = scanner.scan_project(libraries=["numpy"])

        # Should find numpy deprecations but not pydantic
        libraries = set(m.library for m in result.matches)
        if result.matches:
            assert "numpy" in libraries or len(libraries) == 0

    def test_excluded_directories(self, temp_project):
        """Test that excluded directories are skipped."""
        scanner = DeprecationScanner(temp_project)
        files = scanner._get_python_files()

        # .venv should be excluded
        venv_files = [f for f in files if ".venv" in str(f)]
        assert len(venv_files) == 0

    def test_detect_used_libraries(self, temp_project):
        """Test library detection from imports."""
        scanner = DeprecationScanner(temp_project)
        files = scanner._get_python_files()
        libraries = scanner._detect_used_libraries(files)

        assert "pydantic" in libraries or "numpy" in libraries
