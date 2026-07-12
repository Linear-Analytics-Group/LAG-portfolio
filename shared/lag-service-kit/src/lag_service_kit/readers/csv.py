"""CSV record reader."""

from pathlib import Path

import pandas as pd


class CsvRecordReader:
    """Load tabular records from a CSV file.

    Satisfies the ``RecordReader`` protocol.
    """

    def load(self, path: Path) -> pd.DataFrame:
        """Load records from a CSV file into a DataFrame.

        Parameters
        ----------
        path : Path
            Path to the source CSV file.

        Returns
        -------
        pd.DataFrame
            One row per CSV record, columns as defined by the file header.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist.
        """
        return pd.read_csv(path)
