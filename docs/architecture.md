# Architecture

Tessera is a lakehouse, not just a warehouse: raw immutable facts land in an open table format
(Apache Iceberg) so schema evolution, time travel, and reprocessing are first-class. Business
logic lives in version-controlled dbt SQL, not Python glue (ELT, not ETL).

## Top-down flow

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
```

## Layers

### Bronze (raw)
Raw SEC payloads flattened to tidy facts and written to Iceberg. Immutable and append-only.
Partitioned (e.g. by `standard_concept` and `fiscal_year`) to keep scans cheap. Schema evolution
handles new XBRL tags appearing over time without breaking existing data.

### Silver (conformed)
Typed, deduplicated, conformed facts — one row per `(cik, concept, period, form, frame)`. The
`concept_map` seed is joined here to translate inconsistent raw tags into governed standard
concepts. A slowly-changing `dim_company` (SCD2) is built from submissions metadata so historical
attribute changes (industry, name, state) are preserved.

### Gold (marts)
Analytics-ready models consumed by the dashboard and any ML/RAG layer:

- `fct_financials` — long, one standardized fact per row.
- `dim_company` — SCD2 company dimension.
- `mart_fundamentals_annual` — wide company-year table with derived metrics (`net_margin`,
  `roa`, `roe`, `debt_to_equity`, `revenue_growth_yoy`).

## Cross-cutting concerns

- **Orchestration** — Dagster software-defined assets, partitioned by fiscal year and/or company,
  with schedules, a new-filings sensor, and asset checks that mirror the data-quality rules.
- **Data quality / observability** — dbt schema + singular tests, the `elementary` package for run
  history and anomalies, and `soda-core` for freshness and value-distribution checks on the marts.
- **CI/CD** — GitHub Actions runs `ruff`, `mypy --strict`, `pytest`, and a `dbt build` against the
  DuckDB target on a tiny seeded universe (fast and free).

## Local ↔ cloud by configuration

A single `Settings` object resolves a `local` or `cloud` profile. Local uses DuckDB + a SQLite
Iceberg catalog + filesystem/MinIO storage; cloud uses Snowflake/Athena + an AWS Glue catalog +
S3. The same code and the same dbt models run against either — only configuration changes.

## Optional infrastructure

`docker-compose.yml` provides MinIO (S3-compatible object store) and Postgres with `pgvector` for
the cloud-ish path and RAG. The pure-local DuckDB pipeline requires none of it.

## Deliberately out of scope

Airflow, Spark, Redshift, Great Expectations, and Kafka are intentionally **not** used — they
belong to a different project and would make this one read as a duplicate. The stack is kept
distinct: dlt, Iceberg/pyiceberg, dbt, DuckDB, Dagster, Soda/Elementary.
