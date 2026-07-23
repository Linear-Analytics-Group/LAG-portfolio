"""Generic ingest-validation primitives, for any LAG service.

Checks the basic structural shape of records read from a source feed
— required columns present, a business key never null or blank —
before they reach dedup or a destination write. Destination- and
domain-agnostic: this module has no knowledge of Dataverse, inventory,
or any other concrete schema; a service's own domain layer (e.g.
``runners.base.InventoryDomainMixin``) supplies which columns matter
and calls these functions with them.
"""

from typing import Sequence

import pandas as pd


class RecordValidationError(Exception):
    """Raised when ingested records fail a basic structural check.

    Used in exactly two places today: raised by
    ``require_columns``/``require_non_null`` in this module (called
    from ``InventoryDomainMixin.load_records()``), and caught by
    ``BaseSyncRunner.run()`` alongside ``pydantic.ValidationError``
    and ``AuthenticationError`` so a bad data file gets the same
    clean, logged failure treatment those two already get, instead of
    falling into ``run()``'s generic "unexpected error" branch.

    Defined here, in the generic ``lag_service_kit`` layer, rather
    than in the inventory service, so that ``run()`` can catch it
    without importing anything inventory-specific — the same reason
    ``AuthenticationError`` lives in the generic transport layer
    (``lag_data_utils``) rather than in a Dataverse-specific module.
    A second service built later could raise this same exception type
    for its own validation rules and get the same treatment for free,
    but that's a byproduct of where this class lives, not something
    already wired up today.
    """


def require_columns(records: pd.DataFrame, required: Sequence[str]) -> None:
    """Raise if any of ``required`` is missing from ``records``.

    Parameters
    ----------
    records : pd.DataFrame
        The records to check.
    required : Sequence[str]
        Column names that must be present.

    Returns
    -------
    None

    Raises
    ------
    RecordValidationError
        Naming every missing column, if any. Checked all at once
        rather than one at a time, so a caller sees the full list of
        what's wrong with a malformed feed in one error, not one
        column per failed run.
    """
    missing = [name for name in required if name not in records.columns]
    if missing:
        raise RecordValidationError(
            f"Missing required column(s): {', '.join(missing)}."
        )


def require_non_null(records: pd.DataFrame, column: str) -> None:
    """Raise if any row's ``column`` value is null, NaN, or blank.

    Parameters
    ----------
    records : pd.DataFrame
        The records to check. Assumed to already have ``column`` —
        call :func:`require_columns` first so a missing column raises
        that clearer error instead of this function's own.
    column : str
        The column that must carry a real value on every row (e.g. a
        business key used as a destination system's alternate key).

    Returns
    -------
    None

    Raises
    ------
    RecordValidationError
        Naming ``column`` and the number of offending rows, if any.
    """
    values = records[column]
    is_blank = values.isna() | (values.astype(str).str.strip() == "")
    blank_count = int(is_blank.sum())
    if blank_count:
        raise RecordValidationError(
            f"{blank_count} row(s) have a null or blank '{column}' "
            f"value; '{column}' must uniquely identify every record."
        )
