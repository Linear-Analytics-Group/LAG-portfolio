"""Destination-agnostic sync orchestration scaffolding for every LAG service."""

from lag_service_kit.runners.base import BaseSyncRunner
from lag_service_kit.runners.odata import BaseODataSyncRunner

__all__ = ["BaseSyncRunner", "BaseODataSyncRunner"]
