"""Destination- and domain-agnostic sync orchestration template."""

import logging
from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

import pandas as pd
from pydantic import ValidationError

from lag_data_utils.clients.base import AuthenticationError, BaseClient
from lag_service_kit.logging import configure_logging
from lag_service_kit.validation import RecordValidationError

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
    class (e.g. this package's own
    ``lag_service_kit.runners.odata.BaseODataSyncRunner``), to supply
    those specifics.

    ``BaseSyncRunner`` is generic over ``ClientT``, the transport client
    type this run's destination uses (bound to
    ``lag_data_utils.clients.base.BaseClient``). A protocol-specific
    subclass fixes ``ClientT`` to the narrowest client type its
    destinations all share — e.g.
    ``BaseODataSyncRunner(BaseSyncRunner[ODataClient])`` — so
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
    ) -> dict[str, int]:
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
        dict[str, int]
            Counts under at least the keys ``created``, ``updated``, and
            ``failed`` — the three every caller of :meth:`run` may rely
            on. A concrete implementation may add further protocol- or
            destination-specific keys beyond these three (e.g.
            ``lag_service_kit.runners.odata.BaseODataSyncRunner`` adds
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

        The final summary log always reports ``created``, ``updated``,
        and ``failed`` — the three keys :meth:`sync_records` must
        always return — plus, generically, whichever further keys a
        given implementation's result also carries (e.g.
        ``lag_service_kit.runners.odata.BaseODataSyncRunner`` adds
        ``skipped``), so the reported counts always sum to
        ``total_records`` regardless of which protocol-specific base
        produced them. This method still never assumes any particular
        extra key exists — it reports whatever ``result`` actually
        contains beyond the three required keys, without naming one.
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
            logger.error(
                "Configuration error: %s",
                exc,
                extra={"error_type": type(exc).__name__},
            )
            return 1
        except AuthenticationError as exc:
            logger.error(
                "Authentication error: %s",
                exc,
                extra={"error_type": type(exc).__name__},
            )
            return 1
        except FileNotFoundError as exc:
            logger.error(
                "Source error: %s",
                exc,
                extra={"error_type": type(exc).__name__},
            )
            return 1
        except RecordValidationError as exc:
            logger.error(
                "Data validation error: %s",
                exc,
                extra={"error_type": type(exc).__name__},
            )
            return 1
        except Exception as exc:
            logger.exception(
                "Unexpected error during sync.",
                extra={"error_type": type(exc).__name__},
            )
            return 1

        core_keys = ("created", "updated", "failed")
        extra_counts = {
            key: value
            for key, value in result.items()
            if key not in core_keys
        }

        message = "Sync complete: %d created, %d updated, %d failed"
        message_args: list[int] = [
            result["created"],
            result["updated"],
            result["failed"],
        ]
        for key, value in extra_counts.items():
            message += f", %d {key}"
            message_args.append(value)
        message += " (of %d records)."
        message_args.append(len(records))

        logger.info(
            message,
            *message_args,
            extra={
                # "created" alone collides with LogRecord's own
                # creation-timestamp attribute of the same name —
                # logging.Logger.makeRecord() raises KeyError on any
                # extra= key that shadows an existing LogRecord
                # attribute, so every field here is prefixed to stay
                # clear of the standard attribute set entirely.
                "records_created": result["created"],
                "records_updated": result["updated"],
                "records_failed": result["failed"],
                "total_records": len(records),
                **{
                    f"records_{key}": value
                    for key, value in extra_counts.items()
                },
            },
        )
        return 1 if result["failed"] else 0
