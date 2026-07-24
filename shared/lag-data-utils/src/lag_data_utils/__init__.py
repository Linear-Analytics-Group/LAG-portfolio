"""Protocol-agnostic transport clients for LAG destination-system connectors."""

from importlib.metadata import version

#: Sourced from the installed package's own metadata (see
#: pyproject.toml's ``[project] version``) rather than duplicated as a
#: literal here, so this can never drift out of sync with the version
#: actually declared and shipped.
__version__: str = version("lag-data-utils")
