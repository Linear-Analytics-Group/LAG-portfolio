"""Format-specific record readers implementing the ``RecordReader`` protocol."""

from lag_service_kit.readers.base import RecordReader
from lag_service_kit.readers.csv import CsvRecordReader
from lag_service_kit.readers.json import JsonRecordReader
from lag_service_kit.readers.parquet import ParquetRecordReader

__all__ = [
    "RecordReader",
    "CsvRecordReader",
    "JsonRecordReader",
    "ParquetRecordReader",
]
