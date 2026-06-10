"""Tests for tessera.config: env-driven loading, profile switching, secrets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tessera.config import Settings, get_settings

if TYPE_CHECKING:
    import pytest


def test_env_driven_load(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PROFILE", "cloud")
    monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")
    monkeypatch.setenv("REQUEST_RATE_LIMIT", "5")

    settings = Settings()

    assert settings.profile == "cloud"
    assert settings.sec_user_agent == "Test User test@example.com"
    assert settings.request_rate_limit == 5.0


def test_profile_switching() -> None:
    local = Settings(profile="local")
    assert local.is_local is True
    assert local.is_cloud is False

    cloud = Settings(profile="cloud")
    assert cloud.is_cloud is True
    assert cloud.is_local is False


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEC_USER_AGENT", "Cache User cache@example.com")
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second
    get_settings.cache_clear()


def test_secret_not_leaked_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "super-secret-value")

    settings = Settings()

    assert settings.anthropic_api_key is not None
    assert settings.anthropic_api_key.get_secret_value() == "super-secret-value"
    assert "super-secret-value" not in repr(settings)
    assert "super-secret-value" not in str(settings)
