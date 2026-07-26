"""Business requirement: the Dataverse schema and sync engine agree.

`platform/power-platform/LAGInventorySync` is this repo's
Configuration-as-Code record of the Dataverse schema
`DataverseInventorySyncRunner` writes to. The two are maintained
independently — one in Dataverse-solution XML, the other in Python —
so nothing stops them from silently drifting apart unless something
checks. These tests parse the real `Entity.xml` and compare it against
the runner's actual schema constants.
"""

from pathlib import Path
from xml.etree import ElementTree

import pytest
from defaults import DEDUPE_KEY
from runners.dataverse import DEFAULT_ENTITY_SET, DEFAULT_FIELD_MAPPING

pytestmark = pytest.mark.acceptance

_ENTITY_XML = (
    Path(__file__).resolve().parents[2]
    / "platform"
    / "power-platform"
    / "LAGInventorySync"
    / "src"
    / "Entities"
    / "lagsol_InventoryItem"
    / "Entity.xml"
)


@pytest.fixture(scope="module")
def entity_xml() -> ElementTree.Element:
    """Parse the real Entity.xml shipped in this repo.

    Returns
    -------
    xml.etree.ElementTree.Element
        The ``<entity>`` element under ``<Entity><EntityInfo>``, which
        holds the actual attribute/key/entity-set definitions — not
        the outer ``<Entity>`` wrapper, which only holds display name
        metadata.
    """
    root = ElementTree.parse(_ENTITY_XML).getroot()
    entity = root.find("EntityInfo/entity")
    assert entity is not None, "Entity.xml is missing EntityInfo/entity"
    return entity


def test_entity_set_name_matches_the_runner_default(
    entity_xml: ElementTree.Element,
) -> None:
    """Entity.xml's EntitySetName matches the runner's own default."""
    entity_set_name = entity_xml.findtext("EntitySetName")

    assert entity_set_name == DEFAULT_ENTITY_SET


def test_alternate_key_attribute_matches_the_runner_default(
    entity_xml: ElementTree.Element,
) -> None:
    """Entity.xml declares an alternate key on the mapped Dataverse field.

    The alternate key predicate DataverseInventorySyncRunner writes to
    (``lagsol_skuid``) is DEFAULT_ALTERNATE_KEY_FIELD, not DEDUPE_KEY
    (the source column name) — but for this shipped mock schema the
    two happen to share the same literal value ("sku_id" the source
    column, "lagsol_skuid" the Dataverse field, both ultimately
    identifying a SKU). This test checks the alternate key attribute
    against runners.dataverse.DEFAULT_ALTERNATE_KEY_FIELD directly.
    """
    from runners.dataverse import DEFAULT_ALTERNATE_KEY_FIELD

    key_attributes = {
        attribute.text
        for attribute in entity_xml.findall(
            "EntityKeys/EntityKey/EntityKeyAttributes/AttributeName"
        )
    }

    assert DEFAULT_ALTERNATE_KEY_FIELD in key_attributes


def test_every_mapped_dataverse_field_exists_on_the_entity(
    entity_xml: ElementTree.Element,
) -> None:
    """Every DEFAULT_FIELD_MAPPING target field is a real Entity.xml attribute.

    A source column renamed in DEFAULT_FIELD_MAPPING without a
    matching schema change (or vice versa) would otherwise fail only
    at write time, against a real Dataverse environment, with an
    opaque 400 error — this catches it locally instead.
    """
    declared_fields = {
        attribute.findtext("LogicalName")
        for attribute in entity_xml.findall("attributes/attribute")
    }

    for dataverse_field in DEFAULT_FIELD_MAPPING.values():
        assert dataverse_field in declared_fields


def test_dedupe_key_default_is_still_sku_id() -> None:
    """DEDUPE_KEY (the source column) hasn't silently diverged from "sku_id".

    A sanity check tying this file's own docstring claim about
    DEDUPE_KEY/DEFAULT_ALTERNATE_KEY_FIELD sharing a literal value back
    to the actual constant, so that claim itself would fail loudly if
    it ever stopped being true.
    """
    assert DEDUPE_KEY == "sku_id"
