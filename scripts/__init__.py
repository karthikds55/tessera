"""Operational scripts for tessera (universe seeding, one-off maintenance).

Modules here are CLI entry points run via ``python -m scripts.<name>`` and wired
into the ``invoke`` task surface (``tasks.py``). They depend on the ``tessera``
package but contain no importable pipeline logic of their own.
"""

from __future__ import annotations
