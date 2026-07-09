"""Shared input-format abstraction: normalize any source format into a DataFrame."""

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class RecordReader(Protocol):
    """Structural contract for loading tabular records from a source file into a DataFrame.

    Any object implementing ``load`` satisfies this protocol, regardless of
    the underlying source format. Business logic downstream of a reader
    should depend only on this contract — never on a concrete reader class
    or a specific file format — so that adding a new input format never
    requires changing the code that consumes records.
    """

    def load(self, path: Path) -> pd.DataFrame:
        """Load records from ``path`` into a DataFrame.

        Parameters
        ----------
        path : Path
            Path to the source data file.

        Returns
        -------
        pd.DataFrame
            One row per source record, columns as defined by the source
            format.

        Raises
        ------
        FileNotFoundError
            If ``path`` does not exist.
        """
        ...
