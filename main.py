"""
Content Factory - entry point.

Usage examples:
  # Full quality (Излом channel): trends + scenario + fact-check + render
  python main.py --auto-topic --local-only --no-swarm

  # Custom topic, full quality
  python main.py --topic "Нейтронные звёзды" --local-only --no-swarm

  # Skip fact-check (faster, less safe)
  python main.py --topic "..." --no-fact-check --local-only --no-swarm

  # Strict fact-check: abort if any false fact found
  python main.py --topic "..." --strict-facts --local-only --no-swarm

  # Quick mode without scenario writer (no fact-check either)
  python main.py --topic "..." --no-scenario --local-only --no-swarm

  # Scheduler mode (auto-topic each day, fully automatic)
  python main.py --schedule --local-only --no-swarm
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from loguru import logger
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import settings

console = Console()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI Content Factory - automated video pipeline"
    )
    # Topic source
    topic_group = parser.add_mutually_exclusive_group()
    topic_group.add_argument(
        "--topic", type=str, default=None,
        help="Video topic, e.g. 'Топ-5 фактов о Марсе'"
    )
    topic_group.add_argument(
        "--auto-topic", action="store_true",
        help="Auto-select trending topic via Google Trends + LLM ranking"
    )

    # Pipeline options
    parser.add_argument("--scenes", type=int, default=5,
                        help="Number of scenes (default: 5)")
    parser.add_argument("--no-scenario", action="store_true",
                        help="Skip ScenarioWriter — use fast prompt builder instead")
    parser.add_argument("--local-only", action="store_true",
                        help="Save video locally — skip publishing")
    parser.add_argument("--no-swarm", action="store_true",
                        help="Use sequential pipeline instead of LangGraph Swarm")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only generate images — skip video and publishing")
    parser.add_argument("--no-fact-check", action="store_true",
                        help="Skip fact-checking step (faster but less safe)")
    parser.add_argument("--strict-facts", action="store_true",
                        help="Abort pipeline if any scene contains false facts")
    parser.add_argument("--schedule", action="store_true",
                        help="Scheduler mode — run pipeline on cron schedule")
    parser.add_argument("--session-id", type=str, default=None,
                        help="Custom session ID for output subfoldering")
    parser.add_argument("--history", action="store_true",
                        help="Show list of already generated topics and exit")
    parser.add_argument("--clear-history", action="store_true",
                        help="Clear topics history (allows re-generating the same topics)")
    return parser.parse_args()


async def run_once(
    topic: str | None = None,
    num_scenes: int = 5,
    use_swarm: bool = True,
    dry_run: bool = False,
    local_only: bool = False,
    auto_topic: bool = False,
    use_scenario: bool = True,
    use_fact_check: bool = True,
    fact_check_strict: bool = False,
    session_id: str | None = None,
) -> None:
    settings.ensure_dirs()

    mode_label = "[yellow]LOCAL ONLY[/yellow]" if local_only else "[green]PUBLISH[/green]"
    if dry_run:
        mode_label = "[dim]DRY RUN[/dim]"

    topic_label = topic or ("[bold magenta]AUTO (Multi-source Trends)[/bold magenta]" if auto_topic else "?")
    scenario_label = "[green]ON[/green]" if use_scenario else "[dim]OFF[/dim]"
    fact_label = "[green]ON[/green]" if use_fact_check else "[dim]OFF[/dim]"

    console.print(Panel(
        f"[bold cyan]Content Factory[/bold cyan]  [dim]— канал «ИЗЛОМ»[/dim]\n"
        f"Topic:       [yellow]{topic_label}[/yellow]\n"
        f"Scenes:      {num_scenes}  |  Mode: {mode_label}\n"
        f"Scenario:    {scenario_label}  |  Trends: {'[green]YES[/green]' if auto_topic else '[dim]NO[/dim]'}\n"
        f"Fact-check:  {fact_label}{'  [red bold](strict)[/red bold]' if fact_check_strict else ''}",
        title="Starting pipeline",
    ))

    if dry_run:
        from agents.content_generator.agent import run_image_generator_agent
        logger.info("DRY-RUN mode: generating images only")
        if not topic:
            console.print("[red]--dry-run requires --topic[/red]")
            return
        scenes = await run_image_generator_agent(topic, num_scenes, session_id)
        table = Table(title="Generated Scenes")
        table.add_column("#", style="cyan")
        table.add_column("Subtitle", style="green")
        table.add_column("Image Path", style="dim")
        for s in scenes:
            table.add_row(str(s["index"]), s["subtitle_text"], s["image_path"])
        console.print(table)
        return

    from orchestrator.swarm import run_pipeline
    result = await run_pipeline(
        topic=topic,
        num_scenes=num_scenes,
        use_swarm=use_swarm,
        session_id=session_id,
        local_only=local_only,
        auto_topic=auto_topic,
        use_scenario=use_scenario,
        use_fact_check=use_fact_check,
        fact_check_strict=fact_check_strict,
    )

    video_path = result.get("video_path", "n/a")
    final_topic = result.get("topic", topic or "")
    trend = result.get("trend")

    if local_only:
        trend_info = (
            f"\nTrend: [magenta]{trend['topic']}[/magenta] "
            f"(score {trend['score']}/10)"
            if trend else ""
        )
        console.print(Panel(
            f"[bold green]Video saved locally![/bold green]\n\n"
            f"[cyan]Title:[/cyan]  {final_topic}\n"
            f"[cyan]Path:[/cyan]   {video_path}"
            + trend_info +
            f"\n\n[dim]Publishing skipped. Run without --local-only to publish.[/dim]",
            title="Done",
            border_style="green",
        ))
    else:
        report = result.get("report", result.get("swarm_output", ""))
        console.print(Panel(
            f"[bold green]Pipeline completed![/bold green]\n"
            f"Session: {result.get('session_id')}\n"
            f"Topic:   {final_topic}\n"
            f"Video:   {video_path}\n"
            f"Report:  {str(report)[:300]}",
            title="Done",
        ))


def start_scheduler(
    use_swarm: bool = True,
    local_only: bool = False,
    use_scenario: bool = True,
) -> None:
    from apscheduler.schedulers.blocking import BlockingScheduler
    from apscheduler.triggers.cron import CronTrigger

    scheduler = BlockingScheduler()
    cron_parts = settings.scheduler_cron.split()
    trigger = CronTrigger(
        minute=cron_parts[0], hour=cron_parts[1],
        day=cron_parts[2], month=cron_parts[3], day_of_week=cron_parts[4],
    )

    def job():
        logger.info("[Scheduler] Auto-picking trending topic ...")
        asyncio.run(run_once(
            auto_topic=True,
            use_swarm=use_swarm,
            local_only=local_only,
            use_scenario=use_scenario,
        ))

    scheduler.add_job(job, trigger=trigger)
    mode = "LOCAL ONLY" if local_only else "WITH PUBLISHING"
    console.print(
        f"[bold green]Scheduler started[/bold green] ({mode})\n"
        f"Cron: [yellow]{settings.scheduler_cron}[/yellow]  |  Press Ctrl+C to stop.\n"
        f"Each run will auto-pick a trending topic from Google Trends."
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


def main() -> None:
    args = parse_args()

    # ── History commands ──────────────────────────────────────────────────────
    if args.history:
        from agents.topics_history import print_history
        print_history()
        return

    if args.clear_history:
        from agents.topics_history import _HISTORY_FILE
        if _HISTORY_FILE.exists():
            _HISTORY_FILE.unlink()
            console.print("[green]Topics history cleared.[/green]")
        else:
            console.print("[dim]History was already empty.[/dim]")
        return

    if args.schedule:
        start_scheduler(
            use_swarm=not args.no_swarm,
            local_only=args.local_only,
            use_scenario=not args.no_scenario,
        )
        return

    if not args.topic and not args.auto_topic:
        console.print(
            "[red]Error:[/red] Specify --topic or --auto-topic.\n\n"
            "[bold]Examples:[/bold]\n"
            "  python main.py --topic \"Топ-5 фактов о Марсе\" --local-only --no-swarm\n"
            "  python main.py --auto-topic --local-only --no-swarm\n"
            "  python main.py --schedule --local-only --no-swarm"
        )
        sys.exit(1)

    asyncio.run(run_once(
        topic=args.topic,
        num_scenes=args.scenes,
        use_swarm=not args.no_swarm,
        dry_run=args.dry_run,
        local_only=args.local_only,
        auto_topic=args.auto_topic,
        use_scenario=not args.no_scenario,
        use_fact_check=not args.no_fact_check,
        fact_check_strict=args.strict_facts,
        session_id=args.session_id,
    ))


if __name__ == "__main__":
    main()
