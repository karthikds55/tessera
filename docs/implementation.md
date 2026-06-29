# Implementation Reference — PR-draft Series

This document maps the approved scaffold plan for **tessera** (the EDGAR Fundamentals
Lakehouse) onto the code that ships it. The plan was decomposed into a sequence of small,
reviewable pull requests (the `pr-drafts/` series); each section below is a detailed
reference for one PR: what shipped, the file inventory, the notable design decisions, and
how to run/verify that layer.

> For the high-level picture see [`architecture.md`](architecture.md); for table-level detail
> see [`data_model.md`](data_model.md). Where this document and those disagree, the code wins.

## Status at a glance

| #  | PR | Branch | Depends on | Status |
|----|----|--------|-----------|--------|
| 01 | Project scaffolding & tooling | `chore/project-scaffolding` | — | ✅ merged |
| 02 | Config, logging, errors | `feat/config-logging-errors` | 01 | ✅ merged |
| 03 | EDGAR ingestion client & models | `feat/edgar-ingestion-client` | 02 | ✅ merged |
| 04 | dlt sources & seed-universe script | `feat/dlt-sources-seed-universe` | 03 | ✅ merged |
| 05 | Iceberg lakehouse & DuckDB warehouse | `feat/lakehouse-warehouse` | 03 | ✅ merged |
| 06 | dbt transform (seed → staging → marts) | `feat/dbt-transform` | 05 | ✅ merged |
| 07 | Dagster orchestration | `feat/orchestration-dagster` | 06 | ✅ merged |
| 08 | Streamlit screener dashboard | `feat/streamlit-dashboard` | 06 | ✅ merged |
| 09 | RAG-over-filings stubs | `feat/rag-stubs` | 02 | 🟡 implemented (branch) |
| 10 | Docker infra (MinIO + pgvector) | `chore/docker-infra` | 01 | ⬜ planned |
| 11 | CI — GitHub Actions | `ci/github-actions` | 06 | ⬜ planned |

## Global conventions

- **Package:** `src/tessera/` (`import tessera`), built with `hatchling`.
- **Toolchain:** `uv` with **Python 3.12** pinned (`.python-version`). `uv sync` builds the venv.
- **Profiles:** a single `Settings.profile` switch (`local` / `cloud`) repoints the whole stack.
  The **local** profile (DuckDB + SQLite Iceberg catalog + `./data` filesystem) is the default
  for all verification; Docker (MinIO/pgvector) and Snowflake are optional.
- **Quality bar:** every PR keeps the tree importable and green under `ruff`,
  `mypy --strict`, and `pytest -m 'not live'`. Unit tests ship with the code they cover.
- **Conventions:** full type hints, Google-style docstrings on public symbols, structured
  logging (`structlog`) — never `print`, `SecretStr` for all keys.

---

## PR-01 — Project scaffolding & tooling

**Branch:** `chore/project-scaffolding` · **Status:** ✅ merged · **Depends on:** —

Stands up the repository's tooling foundation so every later PR has a working environment,
linting, type-checking, tests, a task runner, and a docs skeleton.

**Files:**
- `pyproject.toml` — `[project]` (name `tessera`, `requires-python = ">=3.11,<3.13"`), `src/`
  layout via hatchling; core deps (`httpx`, `tenacity`, `dlt`, `pydantic`, `pydantic-settings`,
  `structlog`, `pyiceberg[sql-sqlite]`, `pyarrow`, `duckdb`, `dbt-core`, `dbt-duckdb`,
  `streamlit`, `dagster`, `dagster-webserver`, `soda-core-duckdb`, `invoke`); `cloud` and `rag`
  optional extras; `dev` dependency group; `[tool.ruff]` (rules `E,W,F,I,D,UP,B,C4,SIM,TCH`,
  line length 100, google pydocstyle), `[tool.mypy]` (`strict`, py3.12, `mypy_path = "src"`,
  pydantic plugin), `[tool.pytest.ini_options]` (markers `live`, `integration`,
  `addopts = "-ra -q -m 'not live'"`).
- `.python-version` (`3.12`), `.gitignore`, `.env.example` (documents every variable, no
  secrets), `.pre-commit-config.yaml` (ruff lint+format, mypy, whitespace fixers).
- `tasks.py` — the full invoke surface: `setup`, `lint`, `format`, `typecheck`, `test`,
  `seed`, `ingest`, `build`, `dashboard`, `dagster`, `pipeline`, `compose` (thin where later
  PRs flesh them out, but the commands exist from day one).
- `README.md`, `docs/architecture.md`, `docs/data_model.md`, `src/tessera/__init__.py`,
  `uv.lock`.

**Verify:** `uv sync` succeeds; `uv run ruff check .`, `uv run mypy --strict src`,
`uv run pytest`, and `uv run invoke --list` all pass.

---

## PR-02 — Config, logging, errors

**Branch:** `feat/config-logging-errors` · **Status:** ✅ merged · **Depends on:** PR-01

The cross-cutting core every other module imports. After this PR there are **no ad-hoc
`os.environ` reads** anywhere else.

**Files:**
- `src/tessera/config.py` — `Settings(BaseSettings)` with `profile: Literal["local","cloud"]`,
  SEC/storage/warehouse fields, `SecretStr` for keys (`price_provider_api_key`,
  `anthropic_api_key`), `is_local`/`is_cloud` and `universe_path` helpers, and
  `@lru_cache get_settings()`.
- `src/tessera/logging.py` — `configure_logging` (console renderer local, JSON cloud; ISO
  timestamps; binds `profile`; idempotent), `get_logger`, and `bind_run_context(run_id, cik, concept)`.
- `src/tessera/errors.py` — `TesseraError` base + `ConfigError`, `EdgarHTTPError`
  (carries `status_code`, `url`), `RateLimitError`, `NormalizationError`, `CatalogError`,
  `WarehouseError`.
- Tests: `tests/test_config.py`, `tests/test_logging.py`.

**Key decisions:** settings are the single source of environment truth; `SecretStr` keeps keys
out of logs/`repr`; `configure_logging` is safe to call repeatedly.

**Verify:** `uv run mypy --strict src`; `uv run pytest tests/test_config.py tests/test_logging.py`.

---

## PR-03 — EDGAR ingestion client & models

**Branch:** `feat/edgar-ingestion-client` · **Status:** ✅ merged · **Depends on:** PR-02

Real, working SEC EDGAR access: a rate-limited, retrying `httpx` client returning typed
pydantic models — the authoritative source of facts for the whole pipeline.

**Files:**
- `src/tessera/ingestion/models.py` — pydantic v2 payload models (`CompanyFacts`,
  `ConceptUnitFact`, `ConceptData`, `CompanyConcept`, `FrameResponse`, `FrameFact`,
  `Submissions`, `RecentFilings`, `FilingsIndex`, `TickerMapEntry`, `FactRow`) plus
  `flatten_company_facts()` → tidy one-fact-per-row records. Tolerant of unknown fields
  (`extra="ignore"`) but fail-fast on missing/mistyped required fields.
- `src/tessera/ingestion/concepts.py` — `STANDARD_CONCEPTS` (candidate raw tags per standard
  concept), `all_candidate_tags()`, `concept_for_tag()`. The in-code source of truth the dbt
  `concept_map.csv` mirrors.
- `src/tessera/ingestion/edgar_client.py` — `EdgarClient` over `httpx.Client`: descriptive
  `User-Agent`, thread-safe **rate gate** (min-interval / token-bucket under a `Lock`),
  `tenacity` **retry** (backoff on 429/403/5xx, terminal → `EdgarHTTPError`), typed methods
  (`get_company_facts`, `get_company_concept`, `get_frame`, `get_submissions`,
  `get_ticker_map`), `_format_cik` zero-padding, context-manager support.
- `src/tessera/ingestion/prices.py` — `PriceProvider` Protocol + `NullPriceProvider` default
  (the core carries **zero** hard price dependency).
- Tests/fixtures: `tests/fixtures/*.json` (real-shaped AAPL/frames/submissions/ticker-map),
  `tests/conftest.py`, `tests/test_edgar_client.py` (mocked via `respx` — retry, terminal
  raise, rate-limit interval, UA header, CIK padding), `tests/test_models.py`.

**Key decisions:** retries live **only** at the client boundary; no live network in unit tests
(an opt-in `@pytest.mark.live` smoke test is deselected by default).

**Verify:** `uv run mypy --strict src`; `uv run pytest -m 'not live'`.

---

## PR-04 — dlt sources & seed-universe script

**Branch:** `feat/dlt-sources-seed-universe` · **Status:** ✅ merged · **Depends on:** PR-03

Declarative extract-load with incremental state, plus the script that builds the small working
universe (~5 tickers) the pipeline runs against.

**Files:**
- `src/tessera/ingestion/sources.py` — `@dlt.source edgar_source(client, ciks)` exposing:
  `company_facts` (merge, incremental cursor on `filed`, surrogate `fact_id` hash key because
  the natural period columns are nullable), `submissions` (merge on `cik`), `ticker_map`
  (replace each run).
- `scripts/__init__.py`, `scripts/seed_universe.py` — `UniverseEntry`, `resolve_universe`,
  `build_universe` (live ticker-map), `load_offline_ticker_map`, `write_universe`,
  `read_universe`, `seed()`, and a CLI (`python -m scripts.seed_universe`). Default universe:
  AAPL, MSFT, GOOGL, AMZN, NVDA.
- `tasks.py` — `inv seed` / `inv ingest` wired to these.
- `tests/test_seed_universe.py` — offline ticker→CIK resolution against the trimmed fixture.

**Key decisions:** dlt owns state/schema-inference/load; the EDGAR client owns rate-limiting and
retries. dlt's local DuckDB output is the hand-off the PR-05 landing step reads back.

**Verify:** `uv run mypy --strict src scripts`; `uv run pytest tests/test_seed_universe.py`;
`inv seed --offline` writes `data/universe.json`.

---

## PR-05 — Iceberg lakehouse & DuckDB warehouse

**Branch:** `feat/lakehouse-warehouse` · **Status:** ✅ merged · **Depends on:** PR-03

Lands raw SEC facts as immutable Iceberg bronze tables and exposes them to DuckDB so dbt can
transform them.

**Files:**
- `src/tessera/lakehouse/catalog.py` — `Catalog` Protocol seam; `build_catalog(settings)`
  (local SQLite `sql` catalog over a filesystem warehouse; cloud Glue); `ensure_namespace`.
- `src/tessera/lakehouse/schemas.py` — pyiceberg + paired pyarrow schemas for
  `bronze.company_facts`, `bronze.submissions`, `bronze.ticker_map`; facts partitioned by
  **identity on `fy`** (bucketing avoided so the local stack needs no `pyiceberg-core` Rust ext).
- `src/tessera/lakehouse/writers.py` — `create_table_if_absent`, `append_facts` (pyarrow →
  Iceberg) with a **schema-evolution** path that evolves rather than fails on new columns.
- `src/tessera/lakehouse/landing.py` — `land_bronze_from_duckdb()` reads dlt's DuckDB output
  back as Arrow, re-aggregates dlt's spilled `tickers`/`exchanges` child tables, casts to the
  exact bronze schemas, and appends to Iceberg.
- `src/tessera/warehouse/duckdb_io.py` — `connect` (loads `iceberg`/`httpfs`),
  `register_bronze_views` (native `iceberg_scan`, **falling back to direct Parquet** reads),
  `run_sql`.
- `src/tessera/ingestion/run.py` — `run_ingest()` orchestrates EL → land → register-views.
- Tests: writers round-trip + lakehouse/ingest integration tests.

**Key decision (version friction):** DuckDB's `iceberg` extension can't reliably open the
pyiceberg-written `file://` metadata on Windows, so view registration tries `iceberg_scan`
first and falls back to reading the snapshot's Parquet data files directly — the Iceberg
**write** path is unaffected, and the fallback still honours snapshot isolation.

**Verify:** `uv run mypy --strict src`; `uv run pytest tests/test_writers.py`; a manual
`inv ingest` writes bronze queryable from DuckDB.

---

## PR-06 — dbt transform (seed → staging → marts)

**Branch:** `feat/dbt-transform` · **Status:** ✅ merged · **Depends on:** PR-05

The heart of the project: turning raw bronze facts into governed marts via concept
normalization driven by a version-controlled seed — ELT in SQL, not Python glue.

**Files (under `dbt/edgar/`):**
- `dbt_project.yml` (layered materializations: staging=view, intermediate=ephemeral,
  marts=table; `elementary` models disabled), `profiles.yml` (`duckdb` default +
  env-driven `snowflake`), `packages.yml` (`dbt_utils`, `elementary`).
- `seeds/concept_map.csv` — `raw_tag,taxonomy,standard_concept,sign,notes`; the single source of
  normalization truth, mirroring `ingestion/concepts.py`.
- `models/staging/` — `stg_companyfacts`, `stg_submissions`, `stg_ticker_map` + `_sources.yml`
  (bronze DuckDB views) + `_staging__models.yml`.
- `models/intermediate/` — `int_facts_normalized` (joins facts to `concept_map`, applies `sign`,
  inner-joins to drop unmapped) and `int_company_scd` (SCD2-shaped).
- `models/marts/` — `dim_company` (SCD2 + surrogate key), `fct_financials` (long grain, one
  authoritative value per period/concept), `mart_fundamentals_annual` (wide company-year +
  derived `net_margin`, `roa`, `roe`, `debt_to_equity`, `revenue_growth_yoy`, all NULL-safe) +
  `_marts__models.yml`.
- `tests/assert_revenue_tags_mapped.sql` — singular **warn** test flagging revenue-like tags the
  seed doesn't map (the "no silent drops" tripwire).
- `tests/test_normalization.py` (repo-level) — asserts the seed covers every candidate tag with
  correct concept/sign.

**Key decisions:** `inv build` was already wired (`dbt deps && dbt seed && dbt build`);
referential integrity (`fct.cik → dim_company`) is enforced with a `relationships` schema test;
`elementary` is installed per the plan but its models are disabled to keep `dbt build` green.

**Verify:** `inv build` (DuckDB) green; `uv run pytest tests/test_normalization.py`.

---

## PR-07 — Dagster orchestration

**Branch:** `feat/orchestration-dagster` · **Status:** ✅ merged · **Depends on:** PR-06

Models the pipeline as software-defined assets with partitions, a refresh schedule, a
new-filings sensor, and asset checks mirroring the dbt data-quality rules.

**Files:**
- `orchestration/__init__.py`, `orchestration/definitions.py` — the asset graph
  `ticker_universe → raw_companyfacts → iceberg_bronze → dbt_models → fundamentals_mart`
  (each asset delegates to the **same library functions** the `inv` tasks use); the two upstream
  extract assets are partitioned by fiscal year; a weekly `ScheduleDefinition` refreshes the
  marts; `new_filings_sensor` polls bronze's max `filed` date; four `@asset_check`s mirror the
  DQ rules (grain uniqueness, `fct.cik → dim_company` referential integrity, `net_margin`
  bounds, freshness).
- `tasks.py` — `inv dagster` (`dagster dev`).
- `tests/test_definitions.py` — validates the `Definitions` graph, partitions, checks, schedule,
  and sensor load.

**Key decisions:** dbt runs via a thin `uv run dbt build` **subprocess shell** rather than
`dagster-dbt` (smaller dependency surface, no manifest coupling); fiscal-year partitions
currently scope logging/metadata while the existing ingest pulls full history (per-partition
extraction is a typed `TODO`); the sensor's per-accession diff is likewise a documented `TODO`.

**Verify:** `uv run mypy --strict orchestration`; `uv run pytest tests/test_definitions.py`;
`inv dagster` (manual smoke).

---

## PR-08 — Streamlit screener dashboard

**Branch:** `feat/streamlit-dashboard` · **Status:** ✅ merged · **Depends on:** PR-06

A screener over `mart_fundamentals_annual`: filter, rank, compare peers, and chart a metric's
time series — reading the warehouse via config, never a hardcoded path.

**Files:**
- `dashboard/__init__.py`.
- `dashboard/queries.py` — typed, **Streamlit-free** SQL layer: `marts_available`,
  `load_industries`, `available_fiscal_years`, `list_companies`, `screen(...)`,
  `metric_timeseries(...)`, `peer_comparison(...)`, plus a `METRICS` allow-list.
- `dashboard/app.py` — thin UI: `@st.cache_resource` connection from `connect(get_settings())`,
  `@st.cache_data` query wrappers (connection passed as `_conn` so Streamlit skips hashing),
  a **Screener** tab and a **Company detail** tab (time-series chart + peer table), and a
  graceful empty-state pointing at `inv pipeline` when marts are unbuilt.
- `tests/test_dashboard_queries.py` — offline in-memory DuckDB fixture asserting SQL behaviour.
- `pyproject.toml` — `pandas.*` added to mypy `ignore_missing_imports`.

**Key decisions:** all SQL lives in `queries.py` so the UI stays thin and the queries are
unit-testable; the `metric` argument is validated against `METRICS` before being interpolated
as a SQL identifier (no injection), and all values are parameterized.

**Verify:** `uv run mypy --strict dashboard`; `uv run pytest tests/test_dashboard_queries.py`;
`inv dashboard` (manual smoke).

---

## PR-09 — RAG-over-filings stubs

**Branch:** `feat/rag-stubs` · **Status:** 🟡 implemented on branch · **Depends on:** PR-02

Wires the stretch RAG layer's **interfaces** fully — typed, documented, decoupled from the
core — with explicit `TODO` bodies (never empty contracts).

**Files (under `src/tessera/rag/`):**
- `filings.py` — `FilingDoc`, `FilingsClient` Protocol (the SEC-client seam, so RAG never imports
  the ingestion package), `fetch_filing_documents`, `extract_narrative_sections`.
- `chunk_embed.py` — `chunk_text()` (the one piece of **real logic**: word-windowed chunking),
  `Chunk`, `Embedder`/`VectorStore` Protocols, and the `SentenceTransformerEmbedder` /
  `LanceDBStore` / `PgVectorStore` skeletons + `embed_and_store`.
- `retriever.py` — `Retriever.search`/`.answer`; `answer` fails fast with `ConfigError` when no
  Anthropic key is set; `DEFAULT_ANSWER_MODEL = "claude-opus-4-8"`.
- `tests/test_rag_interfaces.py` — `chunk_text` behaviour + Protocol satisfaction + stubs raise.

**Key decisions:** the heavy optional dependencies (`sentence-transformers`, `lancedb`,
`psycopg`, `anthropic`) are referenced **only inside `TODO` comments**, never as real imports —
so `import tessera.rag` and `mypy` work without the `rag` extra and no new mypy override is
needed. Everything sits behind Protocols, giving the core pipeline zero dependency on RAG.

**Verify:** `uv run mypy --strict src/tessera/rag`; `uv run pytest tests/test_rag_interfaces.py`;
`uv run python -c "import tessera.rag"` (no `rag` extra installed).

---

## PR-10 — Docker infra (MinIO + pgvector) — *planned*

**Branch:** `chore/docker-infra` · **Status:** ⬜ planned · **Depends on:** PR-01

Optional local infrastructure for the cloud-ish path and RAG. The pure-local DuckDB pipeline
must **not** require any of it.

**Planned files:**
- `docker-compose.yml` — `minio` (+ `createbuckets` init), `postgres` with `pgvector`, optional
  profile-gated `dagster` webserver; compose `profiles:` so `up` brings only what's asked; env
  defaults aligned with `.env.example`.
- `Dockerfile` — slim Python 3.12, `uv sync`, non-root user, entrypoint for `inv pipeline` /
  `dagster dev`.
- `.dockerignore`; `inv compose` up/down helpers; an optional-infra note in `architecture.md`.

**Acceptance:** `docker compose config` validates (docker isn't on the dev box — a reviewer with
docker verifies); `inv pipeline` still runs with **no** containers running.

---

## PR-11 — CI (GitHub Actions) — *planned*

**Branch:** `ci/github-actions` · **Status:** ⬜ planned · **Depends on:** PR-06

A fast, free CI gate on push/PR that fails on any lint/type/test/dbt failure.

**Planned files:**
- `.github/workflows/ci.yml` — checkout → `astral-sh/setup-uv` (cached) →
  `uv python install 3.12` → `uv sync` → `ruff format --check` → `ruff check` →
  `mypy --strict src` → `pytest -m 'not live'` → `dbt build` on the **DuckDB** target using a
  fixture-seeded universe (so CI needs **no** SEC network).
- README CI status-badge placeholder.

**Key decision:** CI runs fully **offline** — bronze is seeded from `tests/fixtures/` rather than
hitting SEC — and the workflow mirrors the local gate exactly. Single OS, Python 3.12, to stay
fast and free.

---

## End-to-end local run

```bash
uv sync --all-extras                  # Python 3.12 venv with all extras
cp .env.example .env                  # set SEC_USER_AGENT="Your Name you@example.com"
uv run invoke pipeline                # seed → ingest → Iceberg bronze → dbt build
uv run invoke dashboard               # launch the Streamlit screener
uv run invoke dagster                 # (optional) open the Dagster asset graph
```

## Repository layout

```
src/tessera/
  config.py  logging.py  errors.py            # PR-02 cross-cutting core
  ingestion/  (models, concepts, edgar_client, prices, sources, run)   # PR-03/04/05
  lakehouse/  (catalog, schemas, writers, landing)                     # PR-05
  warehouse/  (duckdb_io)                                              # PR-05
  rag/        (filings, chunk_embed, retriever)                        # PR-09
scripts/seed_universe.py                       # PR-04
dbt/edgar/                                      # PR-06 dbt project
orchestration/definitions.py                    # PR-07 Dagster assets
dashboard/  (queries, app)                       # PR-08 Streamlit screener
tests/                                           # unit/integration tests per PR
docs/  (architecture, data_model, implementation)
tasks.py                                         # invoke task surface (PR-01+)
```
