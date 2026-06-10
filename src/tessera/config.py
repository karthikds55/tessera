"""Typed, environment-driven configuration for tessera.

A single :class:`Settings` object is the only place environment variables are
read. Every other module receives or imports :func:`get_settings` rather than
touching ``os.environ`` directly. The ``profile`` field switches the whole stack
between a local (DuckDB + SQLite Iceberg catalog + filesystem/MinIO) and a cloud
(Snowflake/Athena + Glue + S3) deployment without code changes.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

Profile = Literal["local", "cloud"]
"""The two supported deployment profiles."""


class Settings(BaseSettings):
    """Application settings resolved from the environment and an optional ``.env`` file.

    Field values are sourced (highest precedence first) from constructor
    arguments, then environment variables, then a ``.env`` file, then defaults.
    Secret-bearing fields use :class:`~pydantic.SecretStr` so they never appear
    in logs or ``repr`` output.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Profile ---------------------------------------------------------------
    profile: Profile = "local"

    # --- SEC EDGAR access ------------------------------------------------------
    sec_user_agent: str = "tessera (set SEC_USER_AGENT) dev@example.com"
    request_rate_limit: float = 10.0

    # --- Local storage / warehouse ---------------------------------------------
    data_dir: Path = Path("./data")
    duckdb_path: Path = Path("./data/tessera.duckdb")
    iceberg_catalog_uri: str = "sqlite:///./data/iceberg_catalog.db"
    iceberg_warehouse: str = "./data/iceberg_warehouse"

    # --- dlt extract-load pipeline ---------------------------------------------
    dlt_pipeline_name: str = "tessera_edgar"
    dlt_dataset_name: str = "bronze"

    # --- Object storage (MinIO local / S3 cloud) -------------------------------
    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "tessera"
    s3_access_key_id: str = "minioadmin"
    s3_secret_access_key: SecretStr = SecretStr("minioadmin")

    # --- Cloud warehouse (used when profile == "cloud") ------------------------
    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_password: SecretStr | None = None
    snowflake_role: str | None = None
    snowflake_database: str = "TESSERA"
    snowflake_warehouse: str = "COMPUTE_WH"
    snowflake_schema: str = "PUBLIC"

    # --- Optional integrations -------------------------------------------------
    price_provider_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    @property
    def universe_path(self) -> Path:
        """Return the path of the seeded ticker/CIK universe file."""
        return self.data_dir / "universe.json"

    @property
    def is_local(self) -> bool:
        """Return ``True`` when running against the local stack."""
        return self.profile == "local"

    @property
    def is_cloud(self) -> bool:
        """Return ``True`` when running against the cloud stack."""
        return self.profile == "cloud"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings`, constructed once and cached.

    Returns:
        The cached settings instance. Call ``get_settings.cache_clear()`` to force
        a reload (primarily useful in tests).
    """
    return Settings()
