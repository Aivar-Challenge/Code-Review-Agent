"""
CLI entry point for the Code Review Agent.

Usage:
  python cli.py review <PR_URL> [OPTIONS]
  python cli.py runs list
  python cli.py runs show <RUN_ID>
"""
import asyncio
import json
import sys
import os

# Add project root to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.text import Text
from rich import box
from rich.live import Live
from rich.layout import Layout

console = Console()


def _async_run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@click.group()
def cli():
    """🤖 Code Review Agent — AI-powered GitHub PR reviewer."""
    pass


@cli.command()
@click.argument("pr_url")
@click.option("--dry-run", is_flag=True, default=False, help="Print findings locally, do not post to GitHub.")
@click.option("--domains", default="correctness,security,performance,test_coverage",
              help="Comma-separated list of domains to analyze.")
@click.option("--min-confidence", default="MEDIUM", type=click.Choice(["HIGH", "MEDIUM", "LOW"]),
              help="Minimum confidence threshold for posting comments.")
@click.option("--model", default=None, help="LLM model to use (e.g. gpt-4o-mini).")
@click.option("--no-synthesis", is_flag=True, default=False, help="Disable cross-chunk synthesis pass.")
@click.option("--output-json", is_flag=True, default=False, help="Output results as JSON.")
@click.option("--github-token", default=None, envvar="GITHUB_TOKEN", help="GitHub personal access token.")
def review(pr_url, dry_run, domains, min_confidence, model, no_synthesis, output_json, github_token):
    """Run a code review on a GitHub PR URL."""
    from backend.db.database import init_db
    from backend.agent.analyzer import run_review

    # Parse domains
    domain_list = [d.strip() for d in domains.split(",")]
    domains_config = {
        "correctness": "correctness" in domain_list,
        "security": "security" in domain_list,
        "performance": "performance" in domain_list,
        "test_coverage": "test_coverage" in domain_list,
    }

    config = {
        "domains": domains_config,
        "min_confidence": min_confidence,
        "dry_run": dry_run,
        "synthesis_pass": not no_synthesis,
    }
    if model:
        config["model"] = model
    if github_token:
        config["github_token"] = github_token

    # Print header
    if not output_json:
        console.print(Panel.fit(
            f"[bold cyan]🤖 Code Review Agent[/bold cyan]\n"
            f"PR: [link={pr_url}]{pr_url}[/link]\n"
            f"Domains: {', '.join([d for d, e in domains_config.items() if e])}\n"
            f"Min confidence: [bold]{min_confidence}[/bold]\n"
            f"Dry run: [bold]{'Yes' if dry_run else 'No'}[/bold]",
            border_style="cyan",
        ))

    logs: list[dict] = []

    async def _log_fn(msg: str, level: str = "info"):
        logs.append({"message": msg, "level": level})
        if not output_json:
            color_map = {
                "info": "white",
                "debug": "dim",
                "warning": "yellow",
                "error": "red bold",
                "success": "green",
            }
            color = color_map.get(level, "white")
            console.print(f"  [{color}]{msg}[/{color}]")

    async def _run():
        await init_db()
        return await run_review(
            pr_url=pr_url,
            config_dict=config,
            log_fn=_log_fn,
        )

    result = _async_run(_run())

    if output_json:
        console.print(json.dumps(result, indent=2, default=str))
        return

    if result.get("status") == "failed":
        console.print(f"\n[red bold]❌ Review failed: {result.get('error')}[/red bold]")
        sys.exit(1)

    # Print findings table
    findings = []
    if result.get("run_id"):
        # Load from DB
        async def _get_findings():
            from backend.db.database import AsyncSessionLocal
            from backend.db.models import Finding
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                res = await db.execute(
                    select(Finding).where(Finding.run_id == result["run_id"])
                )
                return res.scalars().all()

        findings = _async_run(_get_findings())

    _print_findings_table(findings, result, dry_run)
    _print_cost_report(result.get("cost", {}))


def _print_findings_table(findings, result: dict, dry_run: bool):
    """Print a rich table of findings."""
    domain_colors = {
        "correctness": "blue",
        "security": "red",
        "performance": "yellow",
        "test_coverage": "cyan",
    }
    confidence_colors = {
        "HIGH": "red bold",
        "MEDIUM": "yellow",
        "LOW": "dim",
    }

    total = len(findings)
    posted = sum(1 for f in findings if f.posted)
    suppressed = sum(1 for f in findings if f.suppressed)

    console.print()
    console.print(Panel.fit(
        f"[bold green]Review Complete![/bold green]\n"
        f"Total findings: [bold]{total}[/bold] | "
        f"Posted: [green bold]{posted}[/green bold] | "
        f"Suppressed/Deduped: [dim]{suppressed}[/dim]"
        + (" | [yellow]DRY RUN — nothing posted to GitHub[/yellow]" if dry_run else ""),
        border_style="green",
    ))

    if not findings:
        console.print("\n[green]✅ No issues found![/green]\n")
        return

    table = Table(
        title="Findings",
        box=box.ROUNDED,
        show_lines=True,
        expand=True,
    )
    table.add_column("Domain", style="bold", width=14)
    table.add_column("Confidence", width=10)
    table.add_column("File", width=30)
    table.add_column("Line", width=6)
    table.add_column("Title", width=40)
    table.add_column("Status", width=12)

    for f in findings:
        domain = f.domain if hasattr(f, "domain") else f.get("domain", "")
        confidence = f.confidence if hasattr(f, "confidence") else f.get("confidence", "")
        file_path = f.file_path if hasattr(f, "file_path") else f.get("file_path", "")
        line_number = f.line_number if hasattr(f, "line_number") else f.get("line_number")
        title = f.title if hasattr(f, "title") else f.get("title", "")
        posted = f.posted if hasattr(f, "posted") else f.get("posted", False)
        suppressed = f.suppressed if hasattr(f, "suppressed") else f.get("suppressed", False)

        domain_color = domain_colors.get(domain, "white")
        conf_color = confidence_colors.get(confidence, "white")

        if suppressed:
            status_text = Text("skipped", style="dim")
        elif posted:
            status_text = Text("✅ posted", style="green")
        elif dry_run:
            status_text = Text("dry-run", style="yellow")
        else:
            status_text = Text("pending", style="dim")

        # Truncate long paths
        if file_path and len(file_path) > 28:
            file_path = "…" + file_path[-27:]

        table.add_row(
            Text(domain, style=domain_color),
            Text(confidence, style=conf_color),
            file_path or "-",
            str(line_number) if line_number else "-",
            (title[:38] + "…") if title and len(title) > 38 else (title or "-"),
            status_text,
        )

    console.print(table)


def _print_cost_report(cost: dict):
    """Print token usage and cost report."""
    if not cost:
        return

    console.print()
    table = Table(title="💰 Cost Report", box=box.SIMPLE, show_header=True)
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Total tokens", f"{cost.get('total_tokens', 0):,}")
    table.add_row("  Prompt tokens", f"{cost.get('prompt_tokens', 0):,}")
    table.add_row("  Completion tokens", f"{cost.get('completion_tokens', 0):,}")
    table.add_row("Estimated cost", f"${cost.get('estimated_cost_usd', 0):.4f}")

    if "domains" in cost:
        for domain, d in cost["domains"].items():
            table.add_row(
                f"  [{domain}]",
                f"{d.get('total_tokens', 0):,} tokens • ${d.get('estimated_cost_usd', 0):.4f}",
            )

    console.print(table)
    console.print()


@cli.group()
def runs():
    """Manage review runs."""
    pass


@runs.command("list")
@click.option("--limit", default=10, help="Number of runs to show.")
def list_runs(limit):
    """List recent review runs."""
    from backend.db.database import AsyncSessionLocal, init_db
    from backend.db.models import Run
    from sqlalchemy import select, desc

    async def _get_runs():
        await init_db()
        async with AsyncSessionLocal() as db:
            res = await db.execute(
                select(Run).order_by(desc(Run.started_at)).limit(limit)
            )
            return res.scalars().all()

    run_list = _async_run(_get_runs())

    if not run_list:
        console.print("[dim]No runs found.[/dim]")
        return

    table = Table(title="Recent Review Runs", box=box.ROUNDED)
    table.add_column("Run ID", width=12)
    table.add_column("PR", width=40)
    table.add_column("Status", width=12)
    table.add_column("Findings", width=10)
    table.add_column("Cost", width=10)
    table.add_column("Started", width=22)

    for r in run_list:
        status_color = {
            "completed": "green",
            "running": "yellow",
            "failed": "red",
            "queued": "blue",
        }.get(r.status, "white")

        pr_display = f"#{r.pr_number} {r.repo}" if r.pr_number else r.pr_url[:38]
        table.add_row(
            r.id[:8] + "…",
            pr_display[:38],
            Text(r.status, style=status_color),
            str(r.findings_count or 0),
            f"${r.estimated_cost_usd:.4f}" if r.estimated_cost_usd else "-",
            r.started_at.strftime("%Y-%m-%d %H:%M:%S") if r.started_at else "-",
        )

    console.print(table)


@runs.command("show")
@click.argument("run_id")
def show_run(run_id):
    """Show detailed findings for a run."""
    from backend.db.database import AsyncSessionLocal, init_db
    from backend.db.models import Run, Finding
    from sqlalchemy import select

    async def _get():
        await init_db()
        async with AsyncSessionLocal() as db:
            run_res = await db.execute(select(Run).where(Run.id == run_id))
            run = run_res.scalar_one_or_none()
            if not run:
                # Try prefix match
                run_res = await db.execute(select(Run).where(Run.id.startswith(run_id)))
                run = run_res.scalar_one_or_none()

            if not run:
                return None, []

            findings_res = await db.execute(
                select(Finding).where(Finding.run_id == run.id)
            )
            return run, findings_res.scalars().all()

    run, findings = _async_run(_get())

    if not run:
        console.print(f"[red]Run not found: {run_id}[/red]")
        sys.exit(1)

    console.print(Panel(
        f"[bold]Run:[/bold] {run.id}\n"
        f"[bold]PR:[/bold] {run.pr_url}\n"
        f"[bold]Status:[/bold] {run.status}\n"
        f"[bold]Findings:[/bold] {run.findings_count} total, {run.posted_count} posted\n"
        f"[bold]Cost:[/bold] ${run.estimated_cost_usd:.4f} ({run.total_tokens:,} tokens)",
        title="Run Details",
        border_style="blue",
    ))

    _print_findings_table(findings, {}, False)


if __name__ == "__main__":
    cli()
