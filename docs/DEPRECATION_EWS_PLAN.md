# Deprecation Early Warning System - Implementation Plan

## Overview

Transform Codeshift from a reactive to proactive tool by detecting deprecated patterns in code **before** they become breaking changes.

### Value Proposition
- Prevents emergency migrations
- Gives teams planning time
- Creates regular touchpoints with users
- Surfaces migration opportunities proactively

---

## Architecture

```
codeshift/
├── cli/commands/
│   ├── deprecations.py      # `codeshift deprecations` - List all warnings
│   └── watch.py             # `codeshift watch` - Background monitoring (daemon)
├── watcher/
│   ├── __init__.py
│   ├── models.py            # DeprecationPattern, DeprecationMatch, ScanResult
│   ├── deprecation_db/      # YAML files per library
│   │   ├── __init__.py
│   │   ├── loader.py        # Load and validate YAML files
│   │   ├── pydantic.yaml    # Pydantic deprecations
│   │   ├── sqlalchemy.yaml  # SQLAlchemy deprecations
│   │   ├── fastapi.yaml     # FastAPI deprecations
│   │   └── requests.yaml    # Requests deprecations
│   ├── scanner.py           # Scan code for deprecated patterns
│   └── notifier.py          # Output formatting (console, JSON, CI)
```

---

## Phase 1: Data Models (`codeshift/watcher/models.py`)

### Deprecation Severity Enum

```python
from enum import Enum

class DeprecationSeverity(Enum):
    INFO = "info"           # Soft deprecation, alternative available
    WARNING = "warning"     # Deprecated, removal planned
    CRITICAL = "critical"   # Removal imminent or already in next major version
```

### Deprecation Pattern Model

```python
@dataclass
class DeprecationPattern:
    """A single deprecation pattern to match against code."""
    id: str                          # Unique identifier, e.g., "pydantic-config-class"
    library: str                     # e.g., "pydantic"
    pattern: str                     # Regex or AST pattern to match
    pattern_type: str                # "regex", "import", "decorator", "class_attr"
    context: str | None              # Additional context (e.g., "inside BaseModel subclass")
    deprecated_in: str               # Version deprecated, e.g., "2.0"
    removed_in: str | None           # Version to be removed, e.g., "3.0" or None
    severity: DeprecationSeverity
    message: str                     # Human-readable warning message
    replacement: str | None          # Suggested replacement code/pattern
    link: str | None                 # Documentation link
    auto_fixable: bool = False       # Can Codeshift auto-fix this?
    transform_name: str | None       # Reference to existing transform if auto-fixable
```

### Match Result Model

```python
@dataclass
class DeprecationMatch:
    """A matched deprecation in user code."""
    pattern: DeprecationPattern
    file_path: Path
    line_number: int
    column: int | None
    matched_code: str                # The actual code that matched
    context_lines: list[str]         # Surrounding code for context
```

### Scan Result Model

```python
@dataclass
class DeprecationScanResult:
    """Result of scanning a project for deprecations."""
    project_path: Path
    scanned_at: datetime
    files_scanned: int
    matches: list[DeprecationMatch]

    @property
    def by_severity(self) -> dict[DeprecationSeverity, list[DeprecationMatch]]:
        """Group matches by severity."""

    @property
    def by_library(self) -> dict[str, list[DeprecationMatch]]:
        """Group matches by library."""

    @property
    def critical_count(self) -> int
    @property
    def warning_count(self) -> int
    @property
    def info_count(self) -> int

    def to_json(self) -> dict:
        """Export for CI integration."""
```

---

## Phase 2: Deprecation Database (`codeshift/watcher/deprecation_db/`)

### YAML Schema

```yaml
# codeshift/watcher/deprecation_db/pydantic.yaml
library: pydantic
display_name: Pydantic
documentation_url: https://docs.pydantic.dev/latest/migration/

deprecations:
  # Pattern-based matching
  - id: pydantic-inner-config
    pattern: "class Config:"
    pattern_type: class_definition
    context: "inside BaseModel subclass"
    deprecated_in: "2.0"
    removed_in: null
    severity: warning
    message: "Inner Config class is deprecated, use model_config = ConfigDict(...)"
    replacement: "model_config = ConfigDict(strict=True, ...)"
    link: "https://docs.pydantic.dev/latest/migration/#changes-to-config"
    auto_fixable: true
    transform_name: config_to_configdict

  - id: pydantic-validator-decorator
    pattern: "@validator"
    pattern_type: decorator
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: warning
    message: "@validator is deprecated, use @field_validator instead"
    replacement: "@field_validator('field_name', mode='before')"
    link: "https://docs.pydantic.dev/latest/migration/#changes-to-validators"
    auto_fixable: true
    transform_name: validator_to_field_validator

  - id: pydantic-root-validator
    pattern: "@root_validator"
    pattern_type: decorator
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: warning
    message: "@root_validator is deprecated, use @model_validator instead"
    replacement: "@model_validator(mode='before')"
    link: "https://docs.pydantic.dev/latest/migration/#changes-to-validators"
    auto_fixable: true
    transform_name: root_validator_to_model_validator

  - id: pydantic-schema-method
    pattern: ".schema()"
    pattern_type: method_call
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: info
    message: ".schema() is deprecated, use .model_json_schema() instead"
    replacement: "Model.model_json_schema()"
    auto_fixable: true

  - id: pydantic-dict-method
    pattern: ".dict()"
    pattern_type: method_call
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: info
    message: ".dict() is deprecated, use .model_dump() instead"
    replacement: "instance.model_dump()"
    auto_fixable: true

  - id: pydantic-json-method
    pattern: ".json()"
    pattern_type: method_call
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: info
    message: ".json() is deprecated, use .model_dump_json() instead"
    replacement: "instance.model_dump_json()"
    auto_fixable: true

  - id: pydantic-parse-obj
    pattern: ".parse_obj("
    pattern_type: method_call
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: warning
    message: ".parse_obj() is deprecated, use .model_validate() instead"
    replacement: "Model.model_validate(data)"
    auto_fixable: true

  - id: pydantic-update-forward-refs
    pattern: "update_forward_refs()"
    pattern_type: method_call
    deprecated_in: "2.0"
    removed_in: "3.0"
    severity: warning
    message: "update_forward_refs() is deprecated, use model_rebuild() instead"
    replacement: "Model.model_rebuild()"
    auto_fixable: true
```

### Loader Implementation

```python
# codeshift/watcher/deprecation_db/loader.py
class DeprecationDBLoader:
    """Load and cache deprecation patterns from YAML files."""

    _cache: dict[str, list[DeprecationPattern]] = {}

    @classmethod
    def get_db_path(cls) -> Path:
        """Return path to deprecation_db directory."""

    @classmethod
    def get_supported_libraries(cls) -> list[str]:
        """List all libraries with deprecation data."""

    @classmethod
    def load(cls, library: str) -> list[DeprecationPattern]:
        """Load deprecation patterns for a library."""

    @classmethod
    def load_all(cls) -> dict[str, list[DeprecationPattern]]:
        """Load all deprecation patterns."""

    @classmethod
    def clear_cache(cls) -> None:
        """Clear the cache."""
```

---

## Phase 3: Scanner (`codeshift/watcher/scanner.py`)

### Pattern Matching Strategies

```python
class PatternMatcher(ABC):
    """Base class for pattern matching strategies."""

    @abstractmethod
    def match(self, code: str, pattern: DeprecationPattern) -> list[MatchLocation]:
        """Find all matches of the pattern in code."""

class RegexMatcher(PatternMatcher):
    """Simple regex-based matching."""

class DecoratorMatcher(PatternMatcher):
    """AST-based decorator matching using libcst."""

class MethodCallMatcher(PatternMatcher):
    """AST-based method call matching."""

class ClassDefinitionMatcher(PatternMatcher):
    """AST-based class definition matching (e.g., inner Config class)."""
```

### Deprecation Scanner

```python
class DeprecationScanner:
    """Scan codebase for deprecated patterns."""

    def __init__(self, project_path: Path, config: ProjectConfig | None = None):
        self.project_path = project_path
        self.config = config or ProjectConfig.from_pyproject(project_path)
        self.matchers = self._init_matchers()

    def _init_matchers(self) -> dict[str, PatternMatcher]:
        """Initialize pattern matchers by type."""

    def scan_file(self, file_path: Path, patterns: list[DeprecationPattern]) -> list[DeprecationMatch]:
        """Scan a single file for deprecation patterns."""

    def scan_project(
        self,
        libraries: list[str] | None = None,
        severity_filter: list[DeprecationSeverity] | None = None,
    ) -> DeprecationScanResult:
        """
        Scan entire project for deprecations.

        Args:
            libraries: Limit scan to specific libraries (default: all)
            severity_filter: Only return matches of these severities
        """

    def _get_python_files(self) -> list[Path]:
        """Get all Python files respecting exclusion patterns."""

    def _detect_used_libraries(self) -> list[str]:
        """Detect which libraries the project uses."""
```

---

## Phase 4: CLI Commands

### `codeshift deprecations` Command

```python
# codeshift/cli/commands/deprecations.py

@click.command()
@click.option("--path", "-p", type=click.Path(exists=True), default=".",
              help="Project path to scan")
@click.option("--library", "-l", multiple=True,
              help="Limit to specific library(s)")
@click.option("--severity", "-s",
              type=click.Choice(["info", "warning", "critical", "all"]),
              default="all", help="Filter by severity")
@click.option("--json", "output_json", is_flag=True,
              help="Output as JSON for CI integration")
@click.option("--fail-on", type=click.Choice(["critical", "warning", "info"]),
              help="Exit with non-zero code if findings at this level or higher")
@click.option("--verbose", "-v", is_flag=True,
              help="Show detailed output including code context")
def deprecations(
    path: str,
    library: tuple[str, ...],
    severity: str,
    output_json: bool,
    fail_on: str | None,
    verbose: bool
) -> None:
    """
    Scan for deprecated patterns in your code.

    Detects usage of deprecated APIs, methods, and patterns
    before they become breaking changes.

    Examples:

        # Scan current directory
        codeshift deprecations

        # Scan with JSON output for CI
        codeshift deprecations --json --fail-on warning

        # Scan only pydantic deprecations
        codeshift deprecations --library pydantic
    """
```

**Console Output Example:**

```
╭─ Deprecation Early Warning System ─╮
│                                    │
│  Scanning project for deprecated   │
│  patterns...                       │
│                                    │
╰────────────────────────────────────╯

Found 12 deprecations in 8 files

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Summary                                                                 ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ 🔴 CRITICAL: 2   🟡 WARNING: 6   🔵 INFO: 4                             │
└─────────────────────────────────────────────────────────────────────────┘

┏━━━━━━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━┓
┃ Severity  ┃ Library   ┃ File                      ┃ Issue              ┃
┡━━━━━━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ 🔴 CRIT   │ pydantic  │ models/user.py:45         │ @validator is...   │
│ 🔴 CRIT   │ pydantic  │ models/order.py:23        │ @root_validator... │
│ 🟡 WARN   │ pydantic  │ models/user.py:12         │ class Config:...   │
│ 🟡 WARN   │ pydantic  │ models/order.py:8         │ class Config:...   │
│ 🔵 INFO   │ pydantic  │ services/auth.py:67       │ .dict() deprecated │
│ ...       │ ...       │ ...                       │ ...                │
└───────────┴───────────┴───────────────────────────┴────────────────────┘

💡 Run 'codeshift upgrade pydantic' to auto-fix 10 of these issues.
```

**JSON Output Schema:**

```json
{
  "scan_time": "2024-01-15T10:30:00Z",
  "project_path": "/path/to/project",
  "files_scanned": 45,
  "summary": {
    "critical": 2,
    "warning": 6,
    "info": 4,
    "total": 12
  },
  "findings": [
    {
      "id": "pydantic-validator-decorator",
      "library": "pydantic",
      "severity": "critical",
      "file": "models/user.py",
      "line": 45,
      "column": 1,
      "message": "@validator is deprecated, use @field_validator instead",
      "deprecated_in": "2.0",
      "removed_in": "3.0",
      "replacement": "@field_validator('field_name', mode='before')",
      "link": "https://docs.pydantic.dev/...",
      "auto_fixable": true,
      "matched_code": "@validator('email')"
    }
  ],
  "auto_fixable_count": 10
}
```

### `codeshift watch` Command (Optional Daemon Mode)

```python
# codeshift/cli/commands/watch.py

@click.command()
@click.option("--path", "-p", type=click.Path(exists=True), default=".",
              help="Project path to watch")
@click.option("--interval", "-i", type=int, default=300,
              help="Scan interval in seconds (default: 300 = 5 minutes)")
@click.option("--daemon", "-d", is_flag=True,
              help="Run as background daemon")
@click.option("--notify", type=click.Choice(["console", "file", "webhook"]),
              default="console", help="Notification method")
@click.option("--webhook-url", help="Webhook URL for notifications")
@click.option("--output-file", type=click.Path(),
              help="File to write results (for daemon mode)")
def watch(
    path: str,
    interval: int,
    daemon: bool,
    notify: str,
    webhook_url: str | None,
    output_file: str | None,
) -> None:
    """
    Watch project for deprecated patterns.

    Continuously monitors your codebase and alerts when
    deprecated patterns are detected.

    Examples:

        # Watch current directory (foreground)
        codeshift watch

        # Run as daemon, write to file
        codeshift watch --daemon --output-file .codeshift/deprecations.json

        # Watch with webhook notifications
        codeshift watch --notify webhook --webhook-url https://...
    """
```

---

## Phase 5: Notifier (`codeshift/watcher/notifier.py`)

```python
class DeprecationNotifier(ABC):
    """Base class for deprecation notification."""

    @abstractmethod
    def notify(self, result: DeprecationScanResult) -> None:
        """Send notification about deprecations."""

class ConsoleNotifier(DeprecationNotifier):
    """Rich console output."""

    def notify(self, result: DeprecationScanResult, verbose: bool = False) -> None:
        """Print formatted deprecation report to console."""

class JSONNotifier(DeprecationNotifier):
    """JSON output for CI/CD integration."""

    def notify(self, result: DeprecationScanResult, output_file: Path | None = None) -> None:
        """Output JSON report (stdout or file)."""

class WebhookNotifier(DeprecationNotifier):
    """Webhook notification for external integrations."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, result: DeprecationScanResult) -> None:
        """POST to webhook with JSON payload."""
```

---

## Phase 6: Integration with Existing Commands

### Enhance `codeshift scan`

Add a `--deprecations` flag to show deprecation warnings during scan:

```python
# In codeshift/cli/commands/scan.py

@click.option("--deprecations", "show_deprecations", is_flag=True,
              help="Also show deprecation warnings")
def scan(..., show_deprecations: bool):
    # ... existing scan logic ...

    if show_deprecations:
        from codeshift.watcher.scanner import DeprecationScanner
        dep_scanner = DeprecationScanner(project_path)
        dep_result = dep_scanner.scan_project()

        if dep_result.matches:
            console.print("\n[yellow]Deprecation Warnings Found:[/]")
            # Show summary...
```

---

## Implementation Order

### Week 1: Foundation

1. **[ ] Create `codeshift/watcher/` directory structure**
2. **[ ] Implement `models.py`** - DeprecationSeverity, DeprecationPattern, DeprecationMatch, DeprecationScanResult
3. **[ ] Create initial YAML schema and `pydantic.yaml`** with comprehensive patterns
4. **[ ] Implement `deprecation_db/loader.py`** - YAML loading and validation

### Week 2: Scanner Core

5. **[ ] Implement pattern matchers** - RegexMatcher, DecoratorMatcher, MethodCallMatcher, ClassDefinitionMatcher
6. **[ ] Implement `scanner.py`** - DeprecationScanner class
7. **[ ] Add unit tests** for scanner and matchers

### Week 3: CLI & Output

8. **[ ] Implement `notifier.py`** - ConsoleNotifier, JSONNotifier
9. **[ ] Implement `cli/commands/deprecations.py`** command
10. **[ ] Register command in `cli/main.py`**
11. **[ ] Add integration tests**

### Week 4: Polish & Extras

12. **[ ] Add more library YAML files** - sqlalchemy.yaml, fastapi.yaml, requests.yaml
13. **[ ] Implement `cli/commands/watch.py`** (optional daemon mode)
14. **[ ] Enhance `scan` command** with deprecation flag
15. **[ ] Documentation and examples**

---

## Testing Strategy

### Unit Tests

```python
# tests/test_watcher/test_models.py
- test_deprecation_severity_values
- test_deprecation_pattern_creation
- test_deprecation_match_creation
- test_scan_result_grouping

# tests/test_watcher/test_loader.py
- test_load_pydantic_deprecations
- test_load_nonexistent_library
- test_yaml_validation

# tests/test_watcher/test_scanner.py
- test_regex_matcher
- test_decorator_matcher
- test_method_call_matcher
- test_scan_file_with_deprecations
- test_scan_project

# tests/test_watcher/test_notifier.py
- test_console_notifier_output
- test_json_notifier_format
```

### Integration Tests

```python
# tests/test_cli/test_deprecations_command.py
- test_deprecations_command_basic
- test_deprecations_json_output
- test_deprecations_severity_filter
- test_deprecations_library_filter
- test_deprecations_fail_on_critical
```

---

## Configuration Options

Add to `pyproject.toml`:

```toml
[tool.codeshift]
# Existing options...

# Deprecation settings
deprecation_severity_threshold = "warning"  # Minimum severity to report
deprecation_libraries = ["pydantic", "sqlalchemy"]  # Limit to specific libraries
deprecation_ignore = [
    "pydantic-dict-method",  # Ignore specific deprecation IDs
]
```

---

## CI Integration Examples

### GitHub Actions

```yaml
- name: Check for deprecations
  run: |
    codeshift deprecations --json --fail-on warning > deprecations.json

- name: Upload deprecation report
  uses: actions/upload-artifact@v3
  with:
    name: deprecation-report
    path: deprecations.json
```

### GitLab CI

```yaml
deprecation-check:
  script:
    - codeshift deprecations --json --fail-on warning
  artifacts:
    reports:
      codequality: deprecations.json
```

---

## Future Enhancements (Not in Initial Scope)

- [ ] IDE integration (VS Code extension)
- [ ] Slack/Teams notifications
- [ ] Historical tracking (trend analysis)
- [ ] Custom deprecation patterns (user-defined YAML)
- [ ] Auto-PR creation for fixes
- [ ] Integration with dependabot/renovate

---

## Questions for Review

1. **Severity mapping**: Should we add a `DEPRECATED` severity between WARNING and CRITICAL for patterns that are deprecated but not yet scheduled for removal?

2. **Timeline estimation**: Should we estimate "time to breakage" based on typical major version release cycles (e.g., "~12 months until Pydantic 3.0")?

3. **Auto-fix integration**: Should `codeshift deprecations --fix` automatically run the relevant upgrade transforms?

4. **Watch command priority**: Is the daemon/watch feature a must-have for MVP, or can it be a Phase 2 enhancement?

5. **Additional libraries**: Which libraries beyond pydantic should be included in MVP? (SQLAlchemy, FastAPI, Requests, Django?)

---

## Acceptance Criteria Checklist

- [ ] `codeshift deprecations` scans and lists all deprecated patterns
- [ ] Severity levels: INFO, WARNING, CRITICAL working correctly
- [ ] Estimated timeline to breakage (based on `removed_in` version)
- [ ] `codeshift watch` runs in background (optional daemon mode)
- [ ] JSON output for CI integration (`--json` flag)
- [ ] Exit codes for CI (`--fail-on` flag)
- [ ] At least pydantic.yaml with comprehensive deprecation patterns
