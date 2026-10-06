"""Command line entry point: `seeder --help`."""
from __future__ import annotations

import asyncio
import logging
from enum import Enum

import typer

from seeder.client.http import SunbirdClient
from seeder.config import load_settings
from seeder.stages.context import Ctx
from seeder.state.store import Store

app = typer.Typer(add_completion=False, help="Seed Sunbird Spark test data and export JMeter CSVs.")
state = {"env": "config/bench.yaml", "volumes": "config/volumes.yaml", "verbose": False}


class Stage(str, Enum):
    users = "users"
    content = "content"
    courses = "courses"
    batches = "batches"
    enrolments = "enrolments"
    all = "all"


ORDER = ["users", "content", "courses", "batches", "enrolments"]


@app.callback()
def main(env: str = typer.Option("config/bench.yaml", help="Environment config"),
         volumes: str = typer.Option("config/volumes.yaml", help="Volumes config"),
         verbose: bool = typer.Option(False, "-v", help="Debug logging")):
    state.update(env=env, volumes=volumes, verbose=verbose)


def _setup():
    settings = load_settings(state["env"], state["volumes"])
    out = settings.output_dir
    logging.basicConfig(
        level=logging.DEBUG if state["verbose"] else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler(out / "seeder.log")])
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return settings, Store(out / "state.db")


def _run(coro_fn):
    settings, store = _setup()

    async def go():
        client = SunbirdClient(settings)
        try:
            return await coro_fn(Ctx(settings, store, client))
        finally:
            await client.close()
            store.close()

    return asyncio.run(go())


@app.command()
def seed(stage: Stage = typer.Argument(..., help="Stage to run, or 'all' in order")):
    """Create entities for a stage. Safe to rerun: finished items are skipped."""
    from seeder.stages import batches, content, courses, enrolments, users
    mods = {"users": users, "content": content, "courses": courses,
            "batches": batches, "enrolments": enrolments}
    names = ORDER if stage == Stage.all else [stage.value]

    async def go(ctx: Ctx):
        total = 0
        for name in names:
            failed = await mods[name].seed(ctx)
            logging.info("stage %s finished with %d failures", name, failed)
            total += failed
        return total

    failed = _run(go)
    raise typer.Exit(code=1 if failed else 0)


@app.command()
def export(workers: int = typer.Option(1, help="Number of JMeter workers to split per-user files")):
    """Write JMeter CSVs to output/<run_id>/csv."""
    from seeder.export.csv_export import export_all
    settings, store = _setup()
    path = export_all(store, settings.volumes, settings.output_dir, workers,
                      settings.secrets["TEST_USER_PASSWORD"])
    store.close()
    typer.echo(f"CSVs written to {path}")


@app.command()
def verify():
    """Show counts by status against expected volumes, and recent errors."""
    from seeder.verify import report
    settings, store = _setup()
    ok = report(store, settings.volumes)
    store.close()
    raise typer.Exit(code=0 if ok else 1)


@app.command()
def cleanup(yes: bool = typer.Option(False, "--yes", help="Confirm retiring seeded data")):
    """Retire seeded courses and content."""
    if not yes:
        typer.echo("Dry run. Re-run with --yes to retire seeded courses and content.")
        raise typer.Exit()
    from seeder.cleanup import retire
    failed = _run(retire)
    raise typer.Exit(code=1 if failed else 0)


if __name__ == "__main__":
    app()
