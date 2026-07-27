"""Format-agnostic record-source contracts, for any LAG service."""

from lag_service_kit.sources.base import ChunkedRecordSource, RecordSource

__all__ = ["RecordSource", "ChunkedRecordSource"]
