# tessera

Open-source fundamentals data engine: ingest fragmented SEC filings, normalize, query, screen.

Tessera builds the normalization engine that paid financial-data vendors charge for. It ingests
raw XBRL company facts directly from the U.S. SEC (free, public, authoritative), reconciles the
inconsistent concept tagging across thousands of issuers into a single governed warehouse, and
serves a fundamentals screener plus a natural-language Q&A layer over filing narratives.

The defensible engineering value is **concept normalization** — deciding what counts as
"revenue", "net income", or "total assets" when 500 issuers tag the same idea five different
ways. That raw-tag → standard-concept mapping is version-controlled **data** (a dbt seed), not
buried logic, so it is auditable and extensible.

## Architecture

```
SEC EDGAR (companyfacts, frames, submissions, ticker map)
      │  httpx + tenacity, rate-limited (<=10 req/s, descriptive User-Agent)
      ▼
Ingestion  ──  dlt sources/resources  (declarative EL, incremental state)
      ▼
Raw lakehouse  ──  Parquet + Apache Iceberg  (bronze; partitioned; schema evolution)
      ▼
Transform  ──  dbt  (staging → intermediate → marts; concept normalization via seed)
      ▼
Warehouse / query  ──  DuckDB (local)  →  Snowflake / Athena (cloud)
      ▼
Serving  ──  Streamlit screener  +  RAG Q&A over filing narratives

Cross-cutting:  Dagster (assets, schedules, sensors, asset checks)
                Elementary / Soda (freshness + anomaly detection)
                GitHub Actions (lint, type-check, tests, dbt build)
```

**Layered data flow**

- **Bronze** — raw SEC payloads flattened to tidy facts, written to Iceberg. Immutable, append-only.
- **Silver** — typed, deduplicated, conformed facts; one row per `(cik, concept, period, form, frame)`,
  plus a slowly-changing `dim_company` (SCD2) built from submissions metadata.
- **Gold (marts)** — analytics-ready: a standardized fact table, a wide annual fundamentals mart,
  and derived metrics. This is what the dashboard and any ML/RAG consumers read.

See [`docs/architecture.md`](docs/architecture.md) and [`docs/data_model.md`](docs/data_model.md)
for detail.

## Quickstart (local profile)

Requires [`uv`](https://docs.astral.sh/uv/). Python 3.12 is pinned via `.python-version`.

```bash
# 1. Install dependencies into a managed venv (Python 3.12).
uv sync --all-extras

# 2. Configure: copy the example env and set a descriptive SEC User-Agent.
cp .env.example .env        # PowerShell: Copy-Item .env.example .env
#   edit .env -> SEC_USER_AGENT="Your Name your.email@example.com"

# 3. Run the whole pipeline on a small universe (seed → ingest → bronze → dbt build).
uv run invoke pipeline

# 4. Launch the screener.
uv run invoke dashboard
```

Run `uv run invoke --list` to see every task (`setup`, `lint`, `format`, `typecheck`, `test`,
`seed`, `ingest`, `build`, `dashboard`, `pipeline`, `compose`).

## Local ↔ cloud switch

The same code runs against a local or cloud stack — the only thing that changes is configuration.

| Concern        | `PROFILE=local`                    | `PROFILE=cloud`              |
| -------------- | ---------------------------------- | ---------------------------- |
| Warehouse      | DuckDB                             | Snowflake / Athena           |
| Iceberg catalog| SQLite                            | AWS Glue                     |
| Object storage | filesystem / MinIO                | S3                           |
| dbt target     | `duckdb`                          | `snowflake`                  |

Switching is a `PROFILE=cloud` change plus the relevant DSNs in `.env` — no code edits.

## Repository layout

```
src/tessera/        core library (config, logging, ingestion, lakehouse, warehouse, rag)
dbt/edgar/          dbt project: concept_map seed, staging → intermediate → marts, tests
orchestration/      Dagster software-defined assets, schedules, sensors, asset checks
dashboard/          Streamlit screener
scripts/            seed_universe and other one-off utilities
tests/              mocked-HTTP unit tests + normalization coverage
docs/               architecture and data-model documentation
```

## Development

```bash
uv run invoke lint          # ruff check
uv run invoke format        # ruff format
uv run invoke typecheck     # mypy --strict src
uv run invoke test          # pytest (offline; --live to include SEC tests)
uv run pre-commit install   # enable the pre-commit gate
```

`ruff` + `mypy --strict` + `pytest` must pass before every commit. No secrets are committed —
only `.env.example`.

## License

MIT — see [`LICENSE`](LICENSE).
