"""Destination- and domain-agnostic sync orchestration template."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Generic, TypeVar

import pandas as pd
from pydantic import ValidationError

from lag_data_utils.clients.base import AuthenticationError, BaseClient

from ..logging import configure_logging

logger: logging.Logger = logging.getLogger(__name__)

ClientT = TypeVar("ClientT", bound=BaseClient)


class BaseSyncRunner(ABC, Generic[ClientT]):
    """Template-method orchestrator for a source-to-destination sync service.

    ``BaseSyncRunner`` is the root of the sync-runner hierarchy, mirroring
    ``lag_data_utils.clients.base.BaseClient``: it fixes the *shape* of a
    sync run — load settings, configure logging, authenticate, read
    records, write records, report results — without assuming a source
    format, a record schema, or a destination system. Concrete services
    subclass it, typically through an intermediate protocol-specific base
    class (e.g., a future inventory service's
    ``BaseODataInventorySyncRunner``), to supply those specifics.

    ``BaseSyncRunner`` is generic over ``ClientT``, the transport client
    type this run's destination uses (bound to
    ``lag_data_utils.clients.base.BaseClient``). A protocol-specific
    subclass fixes ``ClientT`` to the narrowest client type its
    destinations all share — e.g.
    ``BaseODataInventorySyncRunner(BaseSyncRunner[ODataClient])`` — so
    that every subclass in the hierarchy agrees on one client type
    for :meth:`build_client` and :meth:`sync_records`, rather than each
    narrowing it independently and violating the Liskov substitution
    principle. Domain logic that doesn't depend on ``ClientT`` (e.g. a
    mixin for record dedup) can instead be layered in independently,
    without joining this generic hierarchy at all.

    Notes
    -----
    Subclasses must implement :meth:`load_settings`, :meth:`build_client`,
    :meth:`load_records`, and :meth:`sync_records`. :meth:`run` wires them
    together in a fixed sequence and should not need to be overridden.
    """

    @abstractmethod
    def load_settings(self) -> Any:
        """Load and validate this run's configuration.

        Returns
        -------
        Any
            A validated settings object exposing ``log_level`` plus
            whatever fields :meth:`build_client` needs.

        Raises
        ------
        pydantic.ValidationError
            If a required configuration field is unset or invalid.
        """
        ...

    @abstractmethod
    def build_client(self, settings: Any) -> ClientT:
        """Construct the transport client for this run.

        Parameters
        ----------
        settings : Any
            The settings object returned by :meth:`load_settings`.

        Returns
        -------
        ClientT
            A client ready to have
            :meth:`~lag_data_utils.clients.base.BaseClient.acquire_bearer_token`
            called on it.
        """
        ...

    @abstractmethod
    def load_records(self) -> pd.DataFrame:
        """Read and prepare the source records for this run.

        Returns
        -------
        pd.DataFrame
            The deduplicated records to synchronize.
        """
        ...

    @abstractmethod
    def sync_records(
        self, client: ClientT, records: pd.DataFrame
    ) -> Dict[str, int]:
        """Write each record to the destination system.

        Parameters
        ----------
        client : ClientT
            An authenticated transport client, as returned by
            :meth:`build_client`.
        records : pd.DataFrame
            The records returned by :meth:`load_records`.

        Returns
        -------
        Dict[str, int]
            Counts under at least the keys ``created``, ``updated``, and
            ``failed`` — the three every caller of :meth:`run` may rely
            on. A concrete implementation may add further protocol- or
            destination-specific keys beyond these three (e.g.
            ``runners.odata.BaseODataInventorySyncRunner`` adds
            ``skipped`` for records never attempted after a circuit
            breaker trips); :meth:`run` never assumes anything beyond
            the three required keys, so an implementation is free to do
            so without breaking that contract.
        """
        ...

    def run(self) -> int:
        """Execute the full sync: configure, authenticate, read, write, report.

        Returns
        -------
        int
            Process exit code: ``0`` if every record synced without error,
            ``1`` if configuration was invalid, authentication failed, the
            source feed could not be found, any record failed to sync, or
            an unexpected error occurred.

        Notes
        -----
        Every step is wrapped in one ``try`` block, with ``except``
        clauses ordered from most to least specific: a validated
        configuration problem, a rejected credential, and a missing
        source feed are all known, expected operational failures, each
        logged with a short, targeted message. Anything else is, by
        definition, unexpected — it is logged with its full traceback
        via :meth:`~logging.Logger.exception` rather than silently
        swallowed or left to crash the process uncaught.
        """
        configure_logging()

        try:
            settings = self.load_settings()
            configure_logging(settings.log_level)

            client = self.build_client(settings)
            client.acquire_bearer_token()

            records = self.load_records()
            result = self.sync_records(client, records)
        except ValidationError as exc:
            logger.error("Configuration error: %s", exc)
            return 1
        except AuthenticationError as exc:
            logger.error("Authentication error: %s", exc)
            return 1
        except FileNotFoundError as exc:
            logger.error("Source error: %s", exc)
            return 1
        except Exception:
            logger.exception("Unexpected error during sync.")
            return 1

        logger.info(
            "Sync complete: %d created, %d updated, %d failed (of %d records).",
            result["created"],
            result["updated"],
            result["failed"],
            len(records),
        )
        return 1 if result["failed"] else 0
