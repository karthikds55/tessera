"""Smoke test: the package imports and exposes a version."""

from __future__ import annotations

import tessera


def test_package_exposes_version() -> None:
    assert isinstance(tessera.__version__, str)
    assert tessera.__version__
