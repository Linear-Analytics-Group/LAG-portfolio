"""Inventory sync runners: a destination-agnostic base plus one subclass per destination."""

from .base import BaseInventorySyncRunner

__all__ = ["BaseInventorySyncRunner"]
