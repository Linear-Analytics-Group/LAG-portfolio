"""Inventory sync runners.

This service supplies exactly one thing this axis needs:
``InventoryDomainMixin`` (source-agnostic dedup and record handling,
inventory-domain-specific). It combines via multiple inheritance with
a protocol-specific base such as
``lag_service_kit.runners.odata.BaseODataSyncRunner`` (write-protocol
mechanics — destination/domain-agnostic, promoted to shared
scaffolding since it has no inventory-specific knowledge of its own)
into each destination leaf class. A runner is additionally paired with
a source feed (see ``sources``) via composition at construction time,
never through inheritance — the same destination leaf class works
with any source format.
"""

from runners.base import InventoryDomainMixin

__all__ = ["InventoryDomainMixin"]
