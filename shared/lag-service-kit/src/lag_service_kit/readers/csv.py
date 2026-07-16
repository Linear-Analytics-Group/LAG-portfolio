"""CSV record reader."""

from pathlib import Path
from typing import Iterator

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

    def load_chunks(
        self, path: Path, chunksize: int
    ) -> Iterator[pd.DataFrame]:
        """Load records from a CSV file in fixed-size row chunks.

        Unlike :meth:`load`, this never materializes the full file as
        one DataFrame — at most ``chunksize`` rows are held in memory
        at once, bounding memory usage for files too large to load
        whole. CSV's line-delimited structure is what makes true,
        constant-memory chunked reading possible here; formats without
        that structure (e.g. a single JSON array) cannot stream the
        same way, which is why this method exists only on
        ``CsvRecordReader`` and not on the ``RecordReader`` protocol
        every reader satisfies.

        Parameters
        ----------
        path : Path
            Path to the source CSV file.
        chunksize : int
            Maximum number of rows per yielded chunk.

        Returns
        -------
        Iterator[pd.DataFrame]
            Successive row chunks in file order, each with the same
            columns as :meth:`load` would return.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist. Raised immediately, not on the
            first chunk read, since parsing the header requires opening
            the file up front regardless of ``chunksize``.
        """
        return pd.read_csv(path, chunksize=chunksize)
