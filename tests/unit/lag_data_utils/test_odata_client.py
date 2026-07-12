"""Unit tests for lag_data_utils.clients.odata.ODataClient.

Exercised through a minimal concrete subclass, since ``ODataClient``
itself is abstract (``base_url`` has no implementation).
"""

import pytest
import requests
import responses
from lag_data_utils.clients.odata import ODataClient

pytestmark = pytest.mark.unit

FAKE_BASE_URL = "https://fake.example.com/api/data/v9.2"


class _ConcreteODataClient(ODataClient):
    """The minimum needed to instantiate ``ODataClient`` for testing."""

    @property
    def base_url(self) -> str:
        return FAKE_BASE_URL

    def acquire_bearer_token(self) -> str:
        return "fake-bearer-token"


@pytest.fixture
def client() -> _ConcreteODataClient:
    """A concrete ODataClient test double with a fixed base_url/token."""
    return _ConcreteODataClient()


def test_build_entity_url_follows_odata_v4_alternate_key_convention(
    client: _ConcreteODataClient,
) -> None:
    """The alternate-key URL matches /{entity_set}({key_name}='{key_value}')."""
    url = client._build_entity_url(
        "lagsol_inventoryitems", "lagsol_skuid", "SKU-001"
    )
    expected = f"{FAKE_BASE_URL}/lagsol_inventoryitems(lagsol_skuid='SKU-001')"
    assert url == expected


def test_get_headers_includes_bearer_token_and_odata_headers(
    client: _ConcreteODataClient,
) -> None:
    """Standard OData v4 headers include the acquire_bearer_token() value."""
    headers = client._get_headers()
    assert headers["Authorization"] == "Bearer fake-bearer-token"
    assert headers["Content-Type"] == "application/json"
    assert headers["OData-MaxVersion"] == "4.0"
    assert headers["OData-Version"] == "4.0"
    assert headers["Accept"] == "application/json"


@responses.activate
def test_upsert_record_issues_a_patch_to_the_alternate_key_url(
    client: _ConcreteODataClient,
) -> None:
    """upsert_record() PATCHes the alternate-key URL with the JSON payload."""
    url = f"{FAKE_BASE_URL}/lagsol_inventoryitems(lagsol_skuid='SKU-001')"
    responses.add(responses.PATCH, url, status=201)

    response = client.upsert_record(
        entity_set="lagsol_inventoryitems",
        alternate_key_name="lagsol_skuid",
        key_value="SKU-001",
        payload={"lagsol_name": "Widget"},
    )

    assert response.status_code == 201
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "PATCH"
    assert responses.calls[0].request.url == url
    assert responses.calls[0].request.body == b'{"lagsol_name": "Widget"}'


@responses.activate
def test_upsert_record_raises_http_error_carrying_the_4xx_response(
    client: _ConcreteODataClient,
) -> None:
    """A 4xx response surfaces as requests.HTTPError with that response."""
    url = f"{FAKE_BASE_URL}/lagsol_inventoryitems(lagsol_skuid='SKU-001')"
    error_body = {"error": {"message": "bad request"}}
    responses.add(responses.PATCH, url, status=400, json=error_body)

    with pytest.raises(requests.HTTPError) as exc_info:
        client.upsert_record(
            entity_set="lagsol_inventoryitems",
            alternate_key_name="lagsol_skuid",
            key_value="SKU-001",
            payload={},
        )

    assert exc_info.value.response.status_code == 400
    assert exc_info.value.response.json() == error_body


@responses.activate
def test_get_record_applies_select_fields_as_odata_select(
    client: _ConcreteODataClient,
) -> None:
    """get_record() with select_fields sets $select and returns the body."""
    url = f"{FAKE_BASE_URL}/lagsol_inventoryitems(lagsol_skuid='SKU-001')"
    responses.add(
        responses.GET, url, json={"lagsol_name": "Widget"}, status=200
    )

    record = client.get_record(
        entity_set="lagsol_inventoryitems",
        alternate_key_name="lagsol_skuid",
        key_value="SKU-001",
        select_fields=["lagsol_name", "lagsol_unitprice"],
    )

    assert record == {"lagsol_name": "Widget"}
    # `responses` attaches `.params` to the mocked request at runtime;
    # requests' own PreparedRequest stub has no such attribute.
    params = responses.calls[0].request.params  # type: ignore[attr-defined]
    assert params["$select"] == "lagsol_name,lagsol_unitprice"


@responses.activate
def test_query_records_builds_all_system_query_options(
    client: _ConcreteODataClient,
) -> None:
    """query_records() maps every arg to its OData $ option, unwraps value."""
    url = f"{FAKE_BASE_URL}/lagsol_inventoryitems"
    responses.add(
        responses.GET,
        url,
        json={"value": [{"lagsol_skuid": "SKU-001"}]},
        status=200,
    )

    records = client.query_records(
        entity_set="lagsol_inventoryitems",
        odata_filter="lagsol_unitprice lt 10",
        select_fields=["lagsol_skuid"],
        top=5,
        skip=1,
        order_by="lagsol_skuid asc",
    )

    assert records == [{"lagsol_skuid": "SKU-001"}]
    # `responses` attaches `.params` to the mocked request at runtime;
    # requests' own PreparedRequest stub has no such attribute.
    params = responses.calls[0].request.params  # type: ignore[attr-defined]
    assert params["$filter"] == "lagsol_unitprice lt 10"
    assert params["$select"] == "lagsol_skuid"
    assert params["$top"] == "5"
    assert params["$skip"] == "1"
    assert params["$orderby"] == "lagsol_skuid asc"


@responses.activate
def test_query_records_returns_empty_list_when_no_value_key(
    client: _ConcreteODataClient,
) -> None:
    """An empty result set returns an empty list, not a KeyError."""
    url = f"{FAKE_BASE_URL}/lagsol_inventoryitems"
    responses.add(responses.GET, url, json={"value": []}, status=200)

    records = client.query_records(entity_set="lagsol_inventoryitems")

    assert records == []


@responses.activate
def test_delete_record_issues_a_delete_to_the_alternate_key_url(
    client: _ConcreteODataClient,
) -> None:
    """delete_record() DELETEs the alternate-key URL."""
    url = f"{FAKE_BASE_URL}/lagsol_inventoryitems(lagsol_skuid='SKU-001')"
    responses.add(responses.DELETE, url, status=204)

    response = client.delete_record(
        entity_set="lagsol_inventoryitems",
        alternate_key_name="lagsol_skuid",
        key_value="SKU-001",
    )

    assert response.status_code == 204
    assert responses.calls[0].request.method == "DELETE"
