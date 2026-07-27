"""JSON-backed inventory source.

The only source-specific knowledge here is reading the ERP mock feed's
JSON format via ``lag_service_kit.readers.JsonRecordReader``. This class
knows nothing about which destination — Dataverse, SAP, Salesforce, or
anything else — its records end up in; it is paired with a destination
runner by the caller, via composition, not inheritance.
"""

from pathlib import Path

import pandas as pd
from lag_service_kit.readers import JsonRecordReader

JSON_PATH: Path = (
    Path(__file__).parent.parent / "data" / "erp_mock_inventory_data_feed.json"
)


class JsonInventorySource:
    """Reads inventory records from a JSON feed.

    Satisfies ``lag_service_kit.sources.base.RecordSource`` structurally
    — no explicit inheritance, per this repo's Protocols-over-inheritance
    convention.

    Notes
    -----
    Any destination-specific runner (``DataverseInventorySyncRunner``, a
    future ``SapInventorySyncRunner``, ...) is paired with this source by
    passing an instance of it to the runner's constructor — the runner
    never inherits from or otherwise depends on this class directly, so
    the same destination logic works unchanged whether it is paired with
    this source or ``sources.CsvInventorySource``. A future source format
    (Parquet, a REST feed) is added the same way, as a sibling module
    implementing only :meth:`read_records`.
    """

    def __init__(self, json_path: Path = JSON_PATH) -> None:
        """Bind this source to a JSON file.

        Parameters
        ----------
        json_path : Path
            Path to the source JSON file, containing an
            ``orient="records"`` array of flat record objects. Defaults
            to the ERP mock feed shipped with this service.
        """
        self.json_path = json_path

    def read_records(self) -> pd.DataFrame:
        """Read the JSON feed into a DataFrame.

        Returns
        -------
        pd.DataFrame
            Raw, not-yet-deduplicated inventory records, one row per
            JSON record, with ``sku_id``, ``item_name``, and
            ``unit_price`` columns.

        Raises
        ------
        FileNotFoundError
            If :attr:`json_path` does not exist.
        """
        return JsonRecordReader().load(self.json_path)
