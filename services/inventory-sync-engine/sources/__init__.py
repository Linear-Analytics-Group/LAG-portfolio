"""Inventory sources: pluggable, format-specific feed readers.

Independent of any destination — a destination-specific sync runner is
paired with one of these at construction time, via composition, never
through inheritance. Adding a source format never touches a runner;
adding a destination never touches a source.
"""

from .base import InventorySource
from .csv import CsvInventorySource

__all__ = ["InventorySource", "CsvInventorySource"]
