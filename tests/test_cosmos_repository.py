"""Cosmos persistence contract tests, entirely offline using a faithful ETag fake."""
from copy import deepcopy
from datetime import datetime, timezone
import sys
import types

import pytest

from services.catalogue import Catalogue, CatalogueError
from stock_manager.cosmos_repository import (
    CosmosWarehouseRepository, deserialize_state, serialize_state, MAX_DOCUMENT_BYTES
)
from stock_manager.models import Actor, MovementType, WarehouseState
from stock_manager.service import WarehouseService, ValidationError


class FakeCosmosError(Exception):
    def __init__(self, status_code):
        self.status_code = status_code


class FakeContainer:
    """Versioned multi-partition fake for the Cosmos item API."""
    def __init__(self):
        self.documents = {}
        self.version = 0
        self.calls = 0
        self.conflict_once = False

    @property
    def item(self):
        # Expose the default partition for schema-tamper tests.
        return self.documents.get(("main", "warehouse-state"))

    def read_item(self, *, item, partition_key):
        try:
            return deepcopy(self.documents[(partition_key, item)])
        except KeyError:
            raise FakeCosmosError(404) from None

    def create_item(self, *, body):
        key = (body["warehouse_id"], body["id"])
        if key in self.documents:
            raise FakeCosmosError(409)
        self.version += 1
        self.documents[key] = dict(deepcopy(body), _etag=f'"{self.version}"')
        return deepcopy(self.documents[key])

    def replace_item(self, *, item, body, etag, match_condition):
        self.calls += 1
        key = (body["warehouse_id"], item)
        if key not in self.documents:
            raise FakeCosmosError(404)
        if self.conflict_once:
            self.conflict_once = False
            self.version += 1
            self.documents[key]["_etag"] = f'"{self.version}"'
            raise FakeCosmosError(412)
        if etag != self.documents[key]["_etag"]:
            raise FakeCosmosError(412)
        self.version += 1
        self.documents[key] = dict(deepcopy(body), _etag=f'"{self.version}"')
        return deepcopy(self.documents[key])


@pytest.fixture(autouse=True)
def fake_match_conditions(monkeypatch):
    # CI without azure-core: test the logic with the same enum symbol.
    # If the Azure SDK is installed, do not replace the real module.
    try:
        from azure.core import MatchConditions  # noqa: F401
    except ImportError:
        azure = types.ModuleType("azure")
        core = types.ModuleType("azure.core")
        core.MatchConditions = types.SimpleNamespace(IfNotModified="IfNotModified")
        azure.core = core
        monkeypatch.setitem(sys.modules, "azure", azure)
        monkeypatch.setitem(sys.modules, "azure.core", core)


def test_serialization_preserves_types_and_timestamps():
    repo = CosmosWarehouseRepository(FakeContainer())
    catalogue = Catalogue(repository=repo)
    state = repo.read()
    encoded = serialize_state(state)
    restored = deserialize_state(encoded)
    assert restored == state
    assert all(p.created_at.tzinfo is not None for p in restored.products.values())
    assert all(m.movement_type == MovementType.INITIAL for m in restored.movements.values())


def test_seed_once_and_restart_persists():
    fake = FakeContainer()
    one = Catalogue(repository=CosmosWarehouseRepository(fake))
    assert len(one.products) == 6
    one.add_category("Long-Term Storage")
    two = Catalogue(repository=CosmosWarehouseRepository(fake))
    assert len(two.categories) == 6
    assert two.categories[-1]["name"] == "Long-Term Storage"
    assert len(two.products) == 6
    assert len(two.movement_rows()) == 6


def test_stock_and_history_survive_restart():
    fake = FakeContainer()
    a = Catalogue(repository=CosmosWarehouseRepository(fake))
    a.record_stock_movement(product_code="P001", kind="entry", amount="5", reason="Delivery",
                            expected_quantity=None, actor=Actor("admin-id", "admin"))
    b = Catalogue(repository=CosmosWarehouseRepository(fake))
    assert b.get_product("P001")["quantity"] == 50
    assert len(b.history("P001")) == 2
    assert b.history("P001")[-1].actor_username == "admin"


def test_archived_stock_and_history_survive_restart():
    fake = FakeContainer()
    a = Catalogue(repository=CosmosWarehouseRepository(fake))
    a.set_product_archived("P004", archived=True)
    b = Catalogue(repository=CosmosWarehouseRepository(fake))
    assert b.get_product("P004") is None
    assert b.get_product("P004", include_archived=True)["archived"]
    assert len(b.history("P004")) == 1
    assert len(b.products) == 5
    b.set_product_archived("P004", archived=False)
    assert len(Catalogue(repository=CosmosWarehouseRepository(fake)).products) == 6


def test_failed_movement_does_not_change_state_or_log():
    fake = FakeContainer()
    c = Catalogue(repository=CosmosWarehouseRepository(fake))
    before = c.repository.read()
    with pytest.raises(CatalogueError):
        c.record_stock_movement(product_code="P001", kind="exit", amount="9999", reason="",
                                expected_quantity=None, actor=Actor("admin-id", "admin"))
    assert c.repository.read() == before


def test_etag_conflict_retries_without_lost_stock():
    fake = FakeContainer()
    c = Catalogue(repository=CosmosWarehouseRepository(fake))
    fake.conflict_once = True
    before = fake.calls
    c.record_stock_movement(product_code="P001", kind="entry", amount="7", reason="",
                            expected_quantity=None, actor=Actor("x", "admin"))
    assert fake.calls == before + 2
    assert c.get_product("P001")["quantity"] == 52
    assert len(c.history("P001")) == 2


def test_separate_instances_see_latest_version():
    fake = FakeContainer()
    a = Catalogue(repository=CosmosWarehouseRepository(fake))
    b = Catalogue(repository=CosmosWarehouseRepository(fake))
    a.add_product("New Item", ["C001"], "3", "1", "8.30")
    assert b.get_product("P007")["quantity"] == 3
    b.record_stock_movement(product_code="P007", kind="exit", amount="2", reason="Sale",
                            expected_quantity=None, actor=Actor("a", "admin"))
    assert a.get_product("P007")["quantity"] == 1


def test_wrong_schema_is_rejected():
    fake = FakeContainer()
    repo = CosmosWarehouseRepository(fake)
    repo.read()
    fake.item["schema_version"] = 999
    with pytest.raises(RuntimeError, match="schema version"):
        repo.read()


def test_different_warehouse_partition_is_isolated():
    fake = FakeContainer()
    first = Catalogue(repository=CosmosWarehouseRepository(fake, warehouse_id="one"))
    second = Catalogue(repository=CosmosWarehouseRepository(fake, warehouse_id="two"))
    first.add_category("Only first")
    second.add_category("Only second")
    first_again = Catalogue(repository=CosmosWarehouseRepository(fake, warehouse_id="one"))
    second_again = Catalogue(repository=CosmosWarehouseRepository(fake, warehouse_id="two"))
    assert first_again.categories[-1]["name"] == "Only first"
    assert second_again.categories[-1]["name"] == "Only second"
    assert next(p.id for p in first_again.repository.read().products.values() if p.code == "P001") != next(p.id for p in second_again.repository.read().products.values() if p.code == "P001")


def test_invalid_warehouse_id_and_retry_count():
    with pytest.raises(ValueError):
        CosmosWarehouseRepository(FakeContainer(), warehouse_id="")
    with pytest.raises(ValueError):
        CosmosWarehouseRepository(FakeContainer(), max_retries=0)


def test_invalid_state_fails_closed():
    with pytest.raises((ValueError, KeyError)):
        deserialize_state({"next_category": 1, "next_product": 1, "categories": [],
                           "products": [{}], "movements": []})


def test_prices_are_centimes_after_reload():
    fake = FakeContainer()
    c = Catalogue(repository=CosmosWarehouseRepository(fake))
    c.add_product("Test", ["C001"], "1", "1", "0.01")
    state = CosmosWarehouseRepository(fake).read()
    p = next(p for p in state.products.values() if p.code == "P007")
    assert p.price_centimes == 1


def test_duplicate_categories_after_reload():
    fake = FakeContainer()
    c = Catalogue(repository=CosmosWarehouseRepository(fake))
    c.rename_category("C001", "Devices")
    other = Catalogue(repository=CosmosWarehouseRepository(fake))
    with pytest.raises(CatalogueError):
        other.add_category(" DEVICES ")


def test_no_accidental_reset_of_existing_document():
    fake = FakeContainer()
    repo = CosmosWarehouseRepository(fake)
    c = Catalogue(repository=repo)
    old_id = c.get_product("P001")["id"]
    Catalogue(repository=CosmosWarehouseRepository(fake))
    assert Catalogue(repository=CosmosWarehouseRepository(fake)).get_product("P001")["id"] == old_id


def test_multiple_doc_versions_are_monotonic():
    fake = FakeContainer()
    c = Catalogue(repository=CosmosWarehouseRepository(fake))
    before = fake.version
    c.add_category("ZZZ")
    assert fake.version == before + 1
