"""CSV-backed inventory source.

The only source-specific knowledge here is reading the ERP mock feed's
CSV format via ``lag_service_kit.readers.CsvRecordReader``. This class
knows nothing about which destination — Dataverse, SAP, Salesforce, or
anything else — its records end up in; it is paired with a destination
runner by the caller, via composition, not inheritance.
"""

from pathlib import Path

import pandas as pd
from lag_service_kit.readers import CsvRecordReader

CSV_PATH: Path = Path(__file__).parent.parent / "data" / "erp_mock_inventory_data_feed.csv"


class CsvInventorySource:
    """Reads inventory records from a CSV feed, satisfying ``InventorySource``.

    Notes
    -----
    Any destination-specific runner (``DataverseInventorySyncRunner``, a
    future ``SapInventorySyncRunner``, ...) is paired with this source by
    passing an instance of it to the runner's constructor — the runner
    never inherits from or otherwise depends on this class directly, so
    the same destination logic works unchanged against any source. A
    future source format (JSON, Parquet, a REST feed) is added as a
    sibling module — ``sources/json.py``, ``sources/parquet.py`` —
    implementing only :meth:`read_records`.
    """

    def __init__(self, csv_path: Path = CSV_PATH) -> None:
        """Bind this source to a CSV file.

        Parameters
        ----------
        csv_path : Path
            Path to the source CSV file. Defaults to the ERP mock feed
            shipped with this service.
        """
        self.csv_path = csv_path

    def read_records(self) -> pd.DataFrame:
        """Read the CSV feed into a DataFrame.

        Returns
        -------
        pd.DataFrame
            Raw, not-yet-deduplicated inventory records, one row per CSV
            record, with ``sku_id``, ``item_name``, and ``unit_price``
            columns.

        Raises
        ------
        FileNotFoundError
            If :attr:`csv_path` does not exist.
        """
        return CsvRecordReader().load(self.csv_path)
