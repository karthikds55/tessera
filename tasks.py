"""Invoke task definitions for the tessera project.

Cross-platform developer commands (work in PowerShell and POSIX shells) that wrap
the project's tooling and pipeline stages. Run ``uv run invoke --list`` to see them.

Several tasks are intentionally thin in this scaffolding PR and are fleshed out by
later PRs (ingest, build, dashboard, pipeline). They are declared here so the task
surface is stable from the start.
"""

from __future__ import annotations

from invoke import Context, task

# Default working universe for the local end-to-end run.
DEFAULT_UNIVERSE = "AAPL,MSFT,GOOGL,AMZN,NVDA"


@task
def setup(ctx: Context) -> None:
    """Create/refresh the virtual environment and install all dependency groups."""
    ctx.run("uv sync --all-extras", pty=False)


@task
def lint(ctx: Context) -> None:
    """Run ruff lint checks over the project."""
    ctx.run("uv run ruff check .", pty=False)


@task
def format(ctx: Context, check: bool = False) -> None:  # noqa: A001 - invoke task name
    """Format the codebase with ruff (use ``--check`` to verify without writing)."""
    cmd = "uv run ruff format --check ." if check else "uv run ruff format ."
    ctx.run(cmd, pty=False)


@task
def typecheck(ctx: Context) -> None:
    """Run mypy in strict mode over the source tree."""
    ctx.run("uv run mypy --strict src", pty=False)


@task
def test(ctx: Context, live: bool = False) -> None:
    """Run the pytest suite (offline by default; pass ``--live`` to include SEC tests)."""
    marker = "" if live else "-m 'not live'"
    ctx.run(f"uv run pytest {marker}".strip(), pty=False)


@task(
    help={
        "tickers": "Comma-separated ticker symbols to resolve into the universe.",
        "offline": "Resolve against the local ticker-map fixture instead of the live SEC map.",
    }
)
def seed(ctx: Context, tickers: str = DEFAULT_UNIVERSE, offline: bool = False) -> None:
    """Build the initial ticker/CIK universe (writes data/universe.json)."""
    flag = " --offline" if offline else ""
    ctx.run(
        f"uv run python -m scripts.seed_universe --tickers {tickers}{flag}",
        pty=False,
        warn=True,
    )


@task
def ingest(ctx: Context) -> None:
    """Extract SEC facts for the seeded universe via dlt (DuckDB bronze; Iceberg in PR-05)."""
    ctx.run("uv run python -m tessera.ingestion.run", pty=False, warn=True)


@task(name="ci-seed")
def ci_seed(ctx: Context) -> None:
    """Seed Iceberg bronze from local fixtures (offline) for CI's dbt build."""
    ctx.run("uv run python -m scripts.ci_seed", pty=False)


@task
def build(ctx: Context) -> None:
    """Build dbt models on the DuckDB target. (Implemented in PR-06.)."""
    with ctx.cd("dbt/edgar"):
        ctx.run("uv run dbt deps", pty=False, warn=True)
        ctx.run("uv run dbt seed", pty=False, warn=True)
        ctx.run("uv run dbt build", pty=False, warn=True)


@task
def dashboard(ctx: Context) -> None:
    """Launch the Streamlit screener. (Implemented in PR-08.)."""
    ctx.run("uv run streamlit run dashboard/app.py", pty=False, warn=True)


@task
def dagster(ctx: Context) -> None:
    """Launch the Dagster UI over the tessera asset graph (`dagster dev`)."""
    ctx.run("uv run dagster dev -f orchestration/definitions.py", pty=False, warn=True)


@task(pre=[seed, ingest, build])
def pipeline(ctx: Context) -> None:
    """Run the full local pipeline: seed -> ingest -> iceberg bronze -> dbt build."""
    print("Pipeline complete: universe seeded, facts ingested, marts built.")


@task(help={"down": "Tear the stack down instead of bringing it up."})
def compose(ctx: Context, down: bool = False) -> None:
    """Bring the optional Docker stack (MinIO + pgvector) up or down. (Implemented in PR-10.)."""
    action = "down" if down else "up -d"
    ctx.run(f"docker compose {action}", pty=False, warn=True)
