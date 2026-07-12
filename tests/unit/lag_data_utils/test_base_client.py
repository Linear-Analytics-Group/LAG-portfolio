"""Unit tests for lag_data_utils.clients.base: BaseClient, AuthenticationError."""

import pytest
from lag_data_utils.clients.base import AuthenticationError, BaseClient

pytestmark = pytest.mark.unit


def test_base_client_cannot_be_instantiated_directly() -> None:
    """BaseClient is abstract — it fixes only the authentication contract, no implementation."""
    with pytest.raises(TypeError):
        BaseClient()  # type: ignore[abstract]


def test_authentication_error_is_an_exception() -> None:
    """AuthenticationError is the root of the connector auth-failure hierarchy."""
    error = AuthenticationError("boom")
    assert isinstance(error, Exception)
    assert str(error) == "boom"
