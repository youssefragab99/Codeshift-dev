"""CLI command for watching deprecations in the background."""

import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console

from codeshift.utils.config import ProjectConfig
from codeshift.watcher.notifier import (
    ConsoleNotifier,
    FileNotifier,
    WebhookNotifier,
    get_notifier,
)
from codeshift.watcher.scanner import DeprecationScanner

console = Console()


@click.command()
@click.option(
    "--path",
    "-p",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
    default=".",
    help="Project path to watch",
)
@click.option(
    "--interval",
    "-i",
    type=int,
    default=300,
    help="Scan interval in seconds (default: 300 = 5 minutes)",
)
@click.option(
    "--daemon",
    "-d",
    is_flag=True,
    help="Run as background daemon",
)
@click.option(
    "--notify",
    type=click.Choice(["console", "file", "webhook"]),
    default="console",
    help="Notification method",
)
@click.option(
    "--webhook-url",
    help="Webhook URL for notifications (required if --notify=webhook)",
)
@click.option(
    "--output-file",
    type=click.Path(path_type=Path),
    help="File to write results (for file notify mode)",
)
@click.option(
    "--library",
    "-l",
    multiple=True,
    help="Limit to specific library(s)",
)
@click.option(
    "--once",
    is_flag=True,
    help="Run single scan and exit (useful for testing)",
)
def watch(
    path: Path,
    interval: int,
    daemon: bool,
    notify: str,
    webhook_url: str | None,
    output_file: Path | None,
    library: tuple[str, ...],
    once: bool,
) -> None:
    """Watch project for deprecated patterns.

    Continuously monitors your codebase and alerts when
    deprecated patterns are detected.

    \b
    Examples:
        # Watch current directory (foreground)
        codeshift watch

        # Run as daemon, write to file
        codeshift watch --daemon --notify file --output-file .codeshift/deprecations.json

        # Watch with webhook notifications
        codeshift watch --notify webhook --webhook-url https://hooks.example.com/deprecations

        # Watch with 1 minute interval
        codeshift watch --interval 60

        # Single scan (for testing)
        codeshift watch --once
    """
    project_path = path.resolve()

    # Validate options
    if notify == "webhook" and not webhook_url:
        console.print("[red]Error:[/] --webhook-url is required when --notify=webhook")
        sys.exit(1)

    if notify == "file" and not output_file:
        # Default output file
        output_file = project_path / ".codeshift" / "deprecations.json"

    # Ensure output directory exists for file notify
    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)

    # Daemonize if requested
    if daemon:
        _daemonize(project_path, output_file)

    # Create notifier
    notifier = get_notifier(
        notify,
        console=console,
        output_file=output_file,
        webhook_url=webhook_url,
    )

    # Load configuration
    try:
        project_config = ProjectConfig.from_pyproject(project_path)
    except Exception:
        project_config = ProjectConfig()

    # Convert library tuple to list
    libraries = list(library) if library else None

    # Create scanner
    scanner = DeprecationScanner(project_path, project_config)

    # Setup signal handlers for graceful shutdown
    running = True

    def signal_handler(signum, frame):
        nonlocal running
        running = False
        if notify == "console":
            console.print("\n[yellow]Stopping watch...[/]")

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Show startup message
    if notify == "console":
        console.print(
            f"[bold]Deprecation Watch[/]\n"
            f"  Project: [cyan]{project_path}[/]\n"
            f"  Interval: [cyan]{interval}s[/]\n"
            f"  Notify: [cyan]{notify}[/]"
        )
        if output_file:
            console.print(f"  Output: [cyan]{output_file}[/]")
        console.print("\n[dim]Press Ctrl+C to stop[/]\n")

    # Main watch loop
    scan_count = 0
    last_result = None

    while running:
        try:
            scan_count += 1
            scan_start = datetime.now()

            if notify == "console":
                console.print(
                    f"[dim][{scan_start.strftime('%H:%M:%S')}] "
                    f"Scan #{scan_count}...[/]"
                )

            # Run scan
            result = scanner.scan_project(libraries=libraries)

            # Check if results changed
            changed = _results_changed(last_result, result)

            if changed or scan_count == 1:
                # Notify about results
                if notify == "console":
                    if result.matches:
                        notifier.notify(result, verbose=False, show_context=False)
                    else:
                        console.print("[green]No deprecations found[/]")
                else:
                    notifier.notify(result)

            else:
                if notify == "console":
                    console.print(
                        f"[dim]No changes ({result.total_count} deprecations)[/]"
                    )

            last_result = result

            # Exit if --once flag
            if once:
                break

            # Wait for next interval
            if running:
                time.sleep(interval)

        except Exception as e:
            if notify == "console":
                console.print(f"[red]Error during scan:[/] {e}")
            # Continue watching despite errors
            if once:
                sys.exit(1)
            time.sleep(interval)

    # Cleanup message
    if notify == "console" and not once:
        console.print("[dim]Watch stopped.[/]")


def _results_changed(old_result, new_result) -> bool:
    """Check if scan results have changed."""
    if old_result is None:
        return True

    if old_result.total_count != new_result.total_count:
        return True

    # Compare match IDs and locations
    old_keys = set(
        (m.pattern.id, str(m.file_path), m.line_number)
        for m in old_result.matches
    )
    new_keys = set(
        (m.pattern.id, str(m.file_path), m.line_number)
        for m in new_result.matches
    )

    return old_keys != new_keys


def _daemonize(project_path: Path, output_file: Path | None) -> None:
    """Fork process to run as background daemon."""
    # Create pid file location
    codeshift_dir = project_path / ".codeshift"
    codeshift_dir.mkdir(exist_ok=True)
    pid_file = codeshift_dir / "watch.pid"

    # Check if already running
    if pid_file.exists():
        try:
            old_pid = int(pid_file.read_text().strip())
            # Check if process is still running
            os.kill(old_pid, 0)
            console.print(
                f"[yellow]Watch daemon already running (PID {old_pid})[/]"
            )
            console.print(
                f"[dim]Stop with: kill {old_pid}[/]"
            )
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Process not running, remove stale pid file
            pid_file.unlink()

    # First fork
    try:
        pid = os.fork()
        if pid > 0:
            # Parent process
            console.print(f"[green]Watch daemon started (PID {pid})[/]")
            if output_file:
                console.print(f"[dim]Results will be written to: {output_file}[/]")
            console.print(f"[dim]Stop with: kill {pid}[/]")
            sys.exit(0)
    except OSError as e:
        console.print(f"[red]Fork failed:[/] {e}")
        sys.exit(1)

    # Decouple from parent environment
    os.chdir(str(project_path))
    os.setsid()
    os.umask(0)

    # Second fork
    try:
        pid = os.fork()
        if pid > 0:
            sys.exit(0)
    except OSError as e:
        sys.exit(1)

    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()

    # Write pid file
    pid_file.write_text(str(os.getpid()))

    # Setup cleanup on exit
    import atexit

    def cleanup():
        try:
            pid_file.unlink()
        except Exception:
            pass

    atexit.register(cleanup)

    # Redirect stdout/stderr to log file
    log_file = codeshift_dir / "watch.log"
    with open(log_file, "a") as f:
        os.dup2(f.fileno(), sys.stdout.fileno())
        os.dup2(f.fileno(), sys.stderr.fileno())
