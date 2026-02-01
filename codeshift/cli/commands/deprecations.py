"""CLI command for scanning deprecations."""

import sys
from pathlib import Path

import click
from rich.console import Console

from codeshift.utils.config import ProjectConfig
from codeshift.watcher.deprecation_db.loader import DeprecationDBLoader
from codeshift.watcher.models import DeprecationSeverity
from codeshift.watcher.notifier import ConsoleNotifier, JSONNotifier
from codeshift.watcher.scanner import DeprecationScanner

console = Console()


@click.command()
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
    help="Project path to scan",
)
@click.option(
    "--library",
    "-l",
    multiple=True,
    help="Limit to specific library(s). Can be specified multiple times.",
)
@click.option(
    "--severity",
    "-s",
    type=click.Choice(["info", "deprecated", "warning", "critical", "all"]),
    default="all",
    help="Filter by minimum severity level",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    help="Output as JSON for CI integration",
)
@click.option(
    "--fail-on",
    type=click.Choice(["info", "deprecated", "warning", "critical"]),
    help="Exit with non-zero code if findings at this level or higher",
)
@click.option(
    "--fix",
    is_flag=True,
    help="Automatically fix auto-fixable deprecations using upgrade transforms",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show detailed output including all findings",
)
@click.option(
    "--context",
    "-c",
    is_flag=True,
    help="Show code context around each finding",
)
@click.option(
    "--list-libraries",
    is_flag=True,
    help="List all libraries with deprecation data",
)
def deprecations(
    path: Path,
    library: tuple[str, ...],
    severity: str,
    output_json: bool,
    fail_on: str | None,
    fix: bool,
    verbose: bool,
    context: bool,
    list_libraries: bool,
) -> None:
    """Scan for deprecated patterns in your code.

    Detects usage of deprecated APIs, methods, and patterns
    before they become breaking changes.

    \b
    Examples:
        # Scan current directory
        codeshift deprecations

        # Scan with JSON output for CI
        codeshift deprecations --json --fail-on warning

        # Scan only pydantic deprecations
        codeshift deprecations --library pydantic

        # Show all findings with context
        codeshift deprecations --verbose --context

        # Auto-fix deprecations
        codeshift deprecations --fix
    """
    # Handle --list-libraries
    if list_libraries:
        _list_libraries()
        return

    project_path = path.resolve()

    # Load configuration
    try:
        project_config = ProjectConfig.from_pyproject(project_path)
    except Exception:
        project_config = ProjectConfig()

    # Convert library tuple to list
    libraries = list(library) if library else None

    # Convert severity filter
    severity_filter = None
    if severity != "all":
        min_severity = DeprecationSeverity.from_string(severity)
        # Include all severities >= min_severity
        severity_filter = [
            s for s in DeprecationSeverity if s >= min_severity
        ]

    # Show scanning message for non-JSON output
    if not output_json:
        console.print("[dim]Scanning for deprecated patterns...[/]")

    # Create scanner and run scan
    scanner = DeprecationScanner(project_path, project_config)
    result = scanner.scan_project(libraries=libraries, severity_filter=severity_filter)

    # Handle --fix option
    if fix and result.auto_fixable_count > 0:
        _handle_fix(result, project_path, output_json)
        return

    # Output results
    if output_json:
        notifier = JSONNotifier()
        notifier.notify(result)
    else:
        notifier = ConsoleNotifier(console)
        notifier.notify(result, verbose=verbose, show_context=context)

    # Handle --fail-on
    if fail_on and result.matches:
        fail_severity = DeprecationSeverity.from_string(fail_on)
        if result.has_severity_at_or_above(fail_severity):
            count = len(result.filter_by_severity(fail_severity))
            if not output_json:
                console.print(
                    f"\n[red]Failing due to {count} findings at "
                    f"{fail_on.upper()} level or higher[/]"
                )
            sys.exit(1)


def _list_libraries() -> None:
    """List all libraries with deprecation data."""
    from rich.table import Table

    libraries = DeprecationDBLoader.get_supported_libraries()

    table = Table(title="Available Libraries with Deprecation Data")
    table.add_column("Library", style="cyan")
    table.add_column("Patterns", justify="right")
    table.add_column("Release Cycle")

    for lib in libraries:
        try:
            patterns = DeprecationDBLoader.load(lib)
            cycle = DeprecationDBLoader.load_release_cycle(lib)
            cycle_info = (
                f"{cycle.typical_major_interval_months}mo cycle"
                if cycle
                else "Unknown"
            )
            table.add_row(lib, str(len(patterns)), cycle_info)
        except Exception:
            table.add_row(lib, "Error", "N/A")

    console.print(table)
    console.print(
        f"\n[dim]Total: {len(libraries)} libraries with deprecation tracking[/]"
    )


def _handle_fix(result, project_path: Path, output_json: bool) -> None:
    """Handle the --fix option by running upgrade transforms."""
    from codeshift.migrator.engine import MigrationEngine
    from codeshift.utils.config import Config

    if not output_json:
        console.print(
            f"\n[yellow]Auto-fixing {result.auto_fixable_count} deprecations...[/]"
        )

    # Group by library
    by_library = result.by_library()
    fixed_count = 0

    for library, matches in by_library.items():
        fixable_matches = [m for m in matches if m.pattern.auto_fixable]
        if not fixable_matches:
            continue

        if not output_json:
            console.print(f"  Processing [cyan]{library}[/]...")

        try:
            # Create migration config
            config = Config(
                project_path=project_path,
                target_library=library,
                target_version="latest",
                project_config=ProjectConfig.from_pyproject(project_path),
                state_file=None,
                dry_run=False,
                verbose=False,
            )

            # Get affected files
            files = set(m.file_path for m in fixable_matches)

            # Run migration engine for those files
            engine = MigrationEngine(config)
            for file_path in files:
                try:
                    results = engine.migrate_file(file_path)
                    if results and results.has_changes:
                        # Write changes
                        file_path.write_text(results.transformed_code)
                        fixed_count += results.change_count
                except Exception as e:
                    if not output_json:
                        console.print(
                            f"    [red]Error fixing {file_path}: {e}[/]"
                        )

        except Exception as e:
            if not output_json:
                console.print(f"    [red]Error processing {library}: {e}[/]")

    if output_json:
        import json
        print(json.dumps({
            "action": "fix",
            "fixed_count": fixed_count,
            "total_auto_fixable": result.auto_fixable_count,
        }))
    else:
        if fixed_count > 0:
            console.print(
                f"\n[green]Fixed {fixed_count} deprecations![/]"
            )
            console.print(
                "[dim]Run 'codeshift deprecations' again to verify.[/]"
            )
        else:
            console.print(
                "\n[yellow]No deprecations were auto-fixed. "
                "Some may require manual intervention.[/]"
            )
