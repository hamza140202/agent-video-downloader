"""CLI entry point — `avd` command."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from avd import __version__
from avd.config import get_settings
from avd.orchestrator import Orchestrator
from avd.tester import Tester
from avd.verifier import Verifier

console = Console(stderr=True)
stdout_console = Console()


@click.group()
@click.version_option(__version__, prog_name="avd")
def cli() -> None:
    """agent-video-downloader (avd) — yt-dlp for cloud agents."""


@cli.command()
@click.argument("url")
@click.option("--dest", "-d", default="./download", help="Destination directory")
@click.option("--json", "as_json", is_flag=True, help="Output JSON result to stdout")
@click.option("--no-verify", is_flag=True, help="Skip Verifier (NOT recommended)")
@click.option("--no-truth", is_flag=True, help="Skip Truth Agent")
def download(url: str, dest: str, as_json: bool, no_verify: bool, no_truth: bool) -> None:
    """Download a single URL."""
    orch = Orchestrator()
    opts = {}
    if no_verify:
        opts["no_verify"] = True
    if no_truth:
        opts["no_truth"] = True
    result = asyncio.run(orch.download(url, dest=Path(dest), opts=opts))
    if as_json:
        stdout_console.print_json(json.dumps(result.model_dump(mode="json"), default=str))
    else:
        if result.status == "ok":
            console.print(f"[green]✅ downloaded[/] {result.artifact_path}")
            if result.verifier_report:
                console.print(f"[dim]verifier: integrity_ok={result.verifier_report.integrity_ok} size={result.verifier_report.size_bytes}B duration={result.verifier_report.duration_s}s[/]")
            if result.truth_report:
                console.print(f"[dim]truth: {result.truth_report.verdict} (confidence {result.truth_report.confidence:.2f})[/]")
        elif result.status == "empty":
            console.print(f"[yellow]⚠️ empty[/] {url} — reason: {result.reason}")
        else:
            console.print(f"[red]❌ failed[/] {url} — reason: {result.reason}")
            if result.slots_tried:
                for s in result.slots_tried:
                    console.print(f"[dim]  - {s.extractor_name}: {s.outcome} ({s.failure_signal})[/]")
    sys.exit(0 if result.status == "ok" else 1)


@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--dest", "-d", default="./download", help="Destination directory")
@click.option("--concurrency", "-c", default=3, help="Parallel downloads")
def batch(file: str, dest: str, concurrency: int) -> None:
    """Batch download from a file (one URL per line, # comments OK)."""
    with open(file) as f:
        urls = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    if not urls:
        console.print("[red]no URLs in file[/]")
        sys.exit(1)
    orch = Orchestrator()
    results = asyncio.run(orch.batch(urls, dest=Path(dest), opts={"concurrency": concurrency}))

    table = Table(title="avd batch results")
    table.add_column("URL", overflow="fold")
    table.add_column("Status")
    table.add_column("Path")
    for r in results:
        status_color = "green" if r.status == "ok" else "yellow" if r.status == "empty" else "red"
        table.add_row(r.url, f"[{status_color}]{r.status}[/{status_color}]", str(r.artifact_path or ""))
    console.print(table)
    ok_count = sum(1 for r in results if r.status == "ok")
    sys.exit(0 if ok_count == len(results) else 1)


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output JSON report to stdout")
def verify(path: str, as_json: bool) -> None:
    """Verify a previously downloaded file."""
    v = Verifier()
    report = asyncio.run(v.verify(Path(path)))
    if as_json:
        stdout_console.print_json(json.dumps(report.model_dump(mode="json"), default=str))
    else:
        if report.integrity_ok:
            console.print(f"[green]✅ verified[/] {path}")
            console.print(f"[dim]size={report.size_bytes}B mime={report.mime_type} duration={report.duration_s}s[/]")
        else:
            console.print(f"[red]❌ rejected[/] {path}")
            for issue in report.issues:
                console.print(f"[red]  - {issue}[/]")
    sys.exit(0 if report.integrity_ok else 1)


@cli.command(name="test")
@click.option("--smoke/--full", default=True, help="Smoke (one URL per platform) or full")
@click.option("--platform", "-p", "platforms", multiple=True, help="Filter to platforms (repeatable)")
def test_cmd(smoke: bool, platforms: tuple[str, ...]) -> None:
    """Run end-to-end self-test."""
    tester = Tester()
    reports = asyncio.run(tester.run(platforms=list(platforms) or None, smoke=smoke))
    passed = sum(1 for r in reports if r.downloaded and r.verified)
    console.print(f"\n[bold]Pass: {passed}/{len(reports)}[/]")
    sys.exit(0 if passed >= (1 if smoke else len(reports) // 2) else 1)


@cli.command()
def supported() -> None:
    """Show supported platforms."""
    orch = Orchestrator()
    table = Table(title="Supported platforms")
    table.add_column("Platform")
    for p in orch.supported():
        table.add_row(p)
    console.print(table)


@cli.command()
def agents() -> None:
    """Show agent versions."""
    from avd.truth_agent import TruthAgent

    table = Table(title="Agent versions")
    table.add_column("Agent")
    table.add_column("Version")
    table.add_row("Orchestrator", Orchestrator.__version__)
    table.add_row("Verifier", Verifier.__version__)
    table.add_row("TruthAgent", TruthAgent.__version__)
    table.add_row("Tester", Tester.__version__)
    console.print(table)


@cli.command()
def jobs() -> None:
    """List recent jobs."""
    from avd.utils.state import list_jobs

    rows = list_jobs(limit=20)
    if not rows:
        console.print("[dim]no jobs[/]")
        return
    table = Table(title="Recent jobs")
    table.add_column("ID")
    table.add_column("URL", overflow="fold")
    table.add_column("Status")
    table.add_column("Platform")
    for r in rows:
        table.add_row(r["id"], r["url"][:80], r["status"] or "-", r["platform"] or "-")
    console.print(table)


@cli.command()
@click.argument("job_id")
def resume(job_id: str) -> None:
    """Resume a job by ID."""
    orch = Orchestrator()
    result = asyncio.run(orch.resume(job_id))
    console.print(f"[bold]resume result[/]: {result.status} {result.reason or ''}")


@cli.command()
def dlq() -> None:
    """List dead-letter queue entries."""
    from avd.utils.state import list_dlq

    rows = list_dlq(limit=20)
    if not rows:
        console.print("[dim]DLQ empty[/]")
        return
    table = Table(title="DLQ entries")
    table.add_column("ID")
    table.add_column("URL", overflow="fold")
    table.add_column("Error")
    for r in rows:
        table.add_row(r["id"], r["url"][:80], r["error"] or "-")
    console.print(table)


@cli.command()
@click.argument("dlq_id")
def replay(dlq_id: str) -> None:
    """Replay a DLQ entry."""
    orch = Orchestrator()
    result = asyncio.run(orch.replay(dlq_id))
    console.print(f"[bold]replay result[/]: {result.status} {result.reason or ''}")


@cli.command()
def mcp() -> None:
    """Start MCP server (stdio JSON-RPC 2.0)."""
    from avd.mcp import serve

    serve()


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
