"""JSON record reader."""

from pathlib import Path

import pandas as pd


class JsonRecordReader:
    """Loads tabular records from a JSON file, satisfying the ``RecordReader`` protocol.

    Expects a JSON array of flat, record-shaped objects (the ``orient="records"``
    layout), matching how ``pandas.DataFrame.to_json(orient="records")`` writes data.
    """

    def load(self, path: Path) -> pd.DataFrame:
        """Load records from a JSON file into a DataFrame.

        Parameters
        ----------
        path : Path
            Path to the source JSON file, containing an array of record
            objects.

        Returns
        -------
        pd.DataFrame
            One row per JSON record, columns as defined by each object's keys.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist.
        """
        return pd.read_json(path, orient="records")
