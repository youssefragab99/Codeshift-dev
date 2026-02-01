"""Notifiers for deprecation scan results."""

import json
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from codeshift.watcher.models import (
    DeprecationMatch,
    DeprecationScanResult,
    DeprecationSeverity,
)


class DeprecationNotifier(ABC):
    """Base class for deprecation notification."""

    @abstractmethod
    def notify(self, result: DeprecationScanResult, **kwargs) -> None:
        """Send notification about deprecations.

        Args:
            result: Scan result to report
            **kwargs: Additional options for the notifier
        """
        pass


class ConsoleNotifier(DeprecationNotifier):
    """Rich console output for deprecation warnings."""

    SEVERITY_ICONS = {
        DeprecationSeverity.CRITICAL: "[red]CRIT[/]",
        DeprecationSeverity.WARNING: "[yellow]WARN[/]",
        DeprecationSeverity.DEPRECATED: "[magenta]DEPR[/]",
        DeprecationSeverity.INFO: "[blue]INFO[/]",
    }

    SEVERITY_COLORS = {
        DeprecationSeverity.CRITICAL: "red",
        DeprecationSeverity.WARNING: "yellow",
        DeprecationSeverity.DEPRECATED: "magenta",
        DeprecationSeverity.INFO: "blue",
    }

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def notify(
        self,
        result: DeprecationScanResult,
        verbose: bool = False,
        show_context: bool = False,
    ) -> None:
        """Print formatted deprecation report to console.

        Args:
            result: Scan result to report
            verbose: Show detailed output
            show_context: Show code context around matches
        """
        if not result.matches:
            self.console.print(
                Panel(
                    "[green]No deprecations found![/]\n\n"
                    "Your code appears to be up-to-date with the latest API patterns.",
                    title="Deprecation Scan Complete",
                )
            )
            return

        # Header
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]Deprecation Early Warning System[/]\n\n"
                f"Found [yellow]{result.total_count}[/] deprecations "
                f"in [cyan]{result.files_scanned}[/] files",
                title="Scan Results",
            )
        )

        # Summary
        self._print_summary(result)

        # Findings table
        self._print_findings_table(result, verbose)

        # Detailed context if requested
        if show_context and result.matches:
            self._print_detailed_context(result)

        # Auto-fix hint
        if result.auto_fixable_count > 0:
            self.console.print()
            libraries = set(m.library for m in result.matches if m.pattern.auto_fixable)
            lib_list = ", ".join(sorted(libraries))
            self.console.print(
                f"[dim]Run [cyan]codeshift deprecations --fix[/] to auto-fix "
                f"{result.auto_fixable_count} issues in: {lib_list}[/]"
            )

    def _print_summary(self, result: DeprecationScanResult) -> None:
        """Print summary counts by severity."""
        summary_parts = []
        if result.critical_count > 0:
            summary_parts.append(f"[red]CRITICAL: {result.critical_count}[/]")
        if result.warning_count > 0:
            summary_parts.append(f"[yellow]WARNING: {result.warning_count}[/]")
        if result.deprecated_count > 0:
            summary_parts.append(f"[magenta]DEPRECATED: {result.deprecated_count}[/]")
        if result.info_count > 0:
            summary_parts.append(f"[blue]INFO: {result.info_count}[/]")

        self.console.print()
        self.console.print("  ".join(summary_parts))
        self.console.print()

    def _print_findings_table(
        self, result: DeprecationScanResult, verbose: bool
    ) -> None:
        """Print table of findings."""
        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity", width=6)
        table.add_column("Library", width=12)
        table.add_column("Location", width=35)
        table.add_column("Issue", width=45)

        # Sort by severity (critical first), then by file
        sorted_matches = sorted(
            result.matches,
            key=lambda m: (
                -list(DeprecationSeverity).index(m.severity),
                str(m.file_path),
                m.line_number,
            ),
        )

        # Limit display unless verbose
        display_matches = sorted_matches if verbose else sorted_matches[:20]

        for match in display_matches:
            severity_icon = self.SEVERITY_ICONS[match.severity]

            # Make path relative if possible
            try:
                rel_path = match.file_path.relative_to(result.project_path)
            except ValueError:
                rel_path = match.file_path

            location = f"{rel_path}:{match.line_number}"

            # Truncate message if too long
            message = match.pattern.message
            if len(message) > 45:
                message = message[:42] + "..."

            table.add_row(
                severity_icon,
                match.library,
                location,
                message,
            )

        self.console.print(table)

        # Show truncation notice
        if not verbose and len(sorted_matches) > 20:
            self.console.print(
                f"\n[dim]Showing 20 of {len(sorted_matches)} findings. "
                f"Use --verbose to see all.[/]"
            )

    def _print_detailed_context(self, result: DeprecationScanResult) -> None:
        """Print detailed context for each match."""
        self.console.print("\n[bold]Detailed Findings:[/]\n")

        by_file = result.by_file()
        for file_path, matches in by_file.items():
            try:
                rel_path = file_path.relative_to(result.project_path)
            except ValueError:
                rel_path = file_path

            self.console.print(f"[bold cyan]{rel_path}[/]")

            for match in matches:
                severity_color = self.SEVERITY_COLORS[match.severity]
                self.console.print(
                    f"  [{severity_color}]Line {match.line_number}:[/] "
                    f"{match.pattern.message}"
                )
                if match.pattern.replacement:
                    self.console.print(
                        f"  [dim]Suggested:[/] {match.pattern.replacement}"
                    )
                if match.context_lines:
                    self.console.print("  [dim]Context:[/]")
                    for line in match.context_lines[:3]:
                        self.console.print(f"    {line}")
                self.console.print()


class JSONNotifier(DeprecationNotifier):
    """JSON output for CI/CD integration."""

    def notify(
        self,
        result: DeprecationScanResult,
        output_file: Path | None = None,
        pretty: bool = True,
    ) -> None:
        """Output JSON report.

        Args:
            result: Scan result to report
            output_file: File to write JSON to (stdout if None)
            pretty: Pretty-print the JSON output
        """
        data = result.to_dict()

        if pretty:
            json_str = json.dumps(data, indent=2, default=str)
        else:
            json_str = json.dumps(data, default=str)

        if output_file:
            output_file.write_text(json_str)
        else:
            print(json_str)


class FileNotifier(DeprecationNotifier):
    """File-based notification for watch mode."""

    def __init__(self, output_path: Path):
        self.output_path = output_path

    def notify(self, result: DeprecationScanResult, **kwargs) -> None:
        """Write results to file.

        Args:
            result: Scan result to report
        """
        data = result.to_dict()
        self.output_path.write_text(json.dumps(data, indent=2, default=str))


class WebhookNotifier(DeprecationNotifier):
    """Webhook notification for external integrations."""

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def notify(self, result: DeprecationScanResult, **kwargs) -> None:
        """POST to webhook with JSON payload.

        Args:
            result: Scan result to report
        """
        import urllib.request
        import urllib.error

        data = result.to_dict()
        json_data = json.dumps(data, default=str).encode("utf-8")

        req = urllib.request.Request(
            self.webhook_url,
            data=json_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                if response.status >= 400:
                    print(
                        f"Warning: Webhook returned status {response.status}",
                        file=sys.stderr,
                    )
        except urllib.error.URLError as e:
            print(f"Warning: Failed to send webhook: {e}", file=sys.stderr)


def get_notifier(
    notify_type: str,
    console: Console | None = None,
    output_file: Path | None = None,
    webhook_url: str | None = None,
) -> DeprecationNotifier:
    """Factory function to create appropriate notifier.

    Args:
        notify_type: Type of notifier ("console", "json", "file", "webhook")
        console: Console instance for console notifier
        output_file: Output file path for file notifier
        webhook_url: URL for webhook notifier

    Returns:
        Appropriate DeprecationNotifier instance
    """
    if notify_type == "json":
        return JSONNotifier()
    elif notify_type == "file" and output_file:
        return FileNotifier(output_file)
    elif notify_type == "webhook" and webhook_url:
        return WebhookNotifier(webhook_url)
    else:
        return ConsoleNotifier(console)
