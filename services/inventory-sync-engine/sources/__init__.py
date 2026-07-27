"""Inventory sources: pluggable, format-specific feed readers.

Independent of any destination — a destination-specific sync runner is
paired with one of these at construction time, via composition, never
through inheritance. Adding a source format never touches a runner;
adding a destination never touches a source. The format-agnostic
``RecordSource``/``ChunkedRecordSource`` Protocols these implement live
in ``lag_service_kit.sources.base`` — this package holds only the
inventory-feed-specific implementations.
"""

from sources.csv import CsvInventorySource
from sources.json import JsonInventorySource

__all__ = [
    "CsvInventorySource",
    "JsonInventorySource",
]
