"""Optional price-provider seam.

The core pipeline reads only SEC EDGAR data and has zero hard dependency on any
price feed. Valuation ratios that need market prices go through the
:class:`PriceProvider` protocol; :class:`NullPriceProvider` is the default no-op
implementation so the core runs without configuring a provider.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date


@runtime_checkable
class PriceProvider(Protocol):
    """A source of historical security prices, injected where ratios need them."""

    def get_price(self, ticker: str, on: date) -> float | None:
        """Return the closing price for ``ticker`` on ``on``.

        Args:
            ticker: The security's ticker symbol.
            on: The date to price as of.

        Returns:
            The price, or ``None`` if unavailable for that date.
        """
        ...


class NullPriceProvider:
    """Default provider that returns no prices; keeps the core price-free."""

    def get_price(self, ticker: str, on: date) -> float | None:
        """Return ``None`` for every request (no price feed configured).

        Args:
            ticker: The security's ticker symbol (ignored).
            on: The date to price as of (ignored).

        Returns:
            Always ``None``.
        """
        return None
