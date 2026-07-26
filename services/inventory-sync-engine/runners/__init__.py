"""Inventory sync runners.

Two independent bases combine via multiple inheritance into each
destination leaf class: ``InventoryDomainMixin`` (source-agnostic dedup
and record handling) and a protocol-specific base such as
``BaseODataInventorySyncRunner`` (write-protocol mechanics). A runner is
additionally paired with a source feed (see ``sources``) via composition
at construction time, never through inheritance — the same destination
leaf class works with any source format.
"""

from runners.base import InventoryDomainMixin
from runners.odata import BaseODataInventorySyncRunner

__all__ = ["InventoryDomainMixin", "BaseODataInventorySyncRunner"]
