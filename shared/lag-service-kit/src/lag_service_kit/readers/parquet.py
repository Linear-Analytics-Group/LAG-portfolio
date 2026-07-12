"""Parquet record reader."""

from pathlib import Path

import pandas as pd


class ParquetRecordReader:
    """Load tabular records from a Parquet file.

    Satisfies the ``RecordReader`` protocol.
    """

    def load(self, path: Path) -> pd.DataFrame:
        """Load records from a Parquet file into a DataFrame.

        Parameters
        ----------
        path : Path
            Path to the source Parquet file.

        Returns
        -------
        pd.DataFrame
            One row per Parquet record, columns as defined by the file schema.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist.
        """
        return pd.read_parquet(path)
