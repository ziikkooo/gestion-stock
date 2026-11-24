"""Cosmos DB for NoSQL repository for the small, single-warehouse course demo.

One warehouse state document + conditional ETag replace offers all-or-none
changes to products and their immutable movement log with optimistic retries.

NOTE: the single-document model is intentionally limited to ~1.7 MiB. For a
large production warehouse, split the domain into per-product partitions and
use same-partition transactional batches and query projections.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from typing import Callable, TypeVar

from .models import Category, Movement, MovementType, Product, WarehouseState

T = TypeVar("T")
SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1_700_000  # Cosmos DB document limit is 2 MB, leave headroom.


def _time(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("Warehouse timestamps must be timezone aware.")
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Warehouse timestamp lacks timezone.")
    return parsed.astimezone(timezone.utc)


def serialize_state(state: WarehouseState) -> dict:
    """Encode dataclasses and UTC timestamps as plain Cosmos-compatible JSON."""
    return {
        "next_category": state.next_category,
        "next_product": state.next_product,
        "categories": [{"id": c.id, "code": c.code, "name": c.name,
                        "normalized_name": c.normalized_name}
                       for c in state.categories.values()],
        "products": [{"id": p.id, "code": p.code, "name": p.name,
                      "category_ids": list(p.category_ids), "quantity": p.quantity,
                      "min_stock": p.min_stock, "price_centimes": p.price_centimes,
                      "created_at": _time(p.created_at), "updated_at": _time(p.updated_at),
                      "archived": p.archived}
                     for p in state.products.values()],
        "movements": [{"id": m.id, "product_id": m.product_id, "product_code": m.product_code,
                       "product_name": m.product_name, "movement_type": m.movement_type.value,
                       "previous_quantity": m.previous_quantity, "quantity_delta": m.quantity_delta,
                       "resulting_quantity": m.resulting_quantity, "actor_id": m.actor_id,
                       "actor_username": m.actor_username, "reason": m.reason,
                       "created_at": _time(m.created_at)}
                      for m in state.movements.values()],
    }


def deserialize_state(data: dict) -> WarehouseState:
    """Validate versioned snapshot structure before using it in application logic."""
    if not isinstance(data, dict):
        raise ValueError("Invalid Cosmos warehouse state.")
    state = WarehouseState(next_category=int(data["next_category"]),
                           next_product=int(data["next_product"]))
    for row in data["categories"]:
        obj = Category(id=row["id"], code=row["code"], name=row["name"],
                       normalized_name=row["normalized_name"])
        if obj.id in state.categories:
            raise ValueError("Duplicate category ID in warehouse state.")
        state.categories[obj.id] = obj
    for row in data["products"]:
        obj = Product(id=row["id"], code=row["code"], name=row["name"],
                      category_ids=tuple(row["category_ids"]), quantity=int(row["quantity"]),
                      min_stock=int(row["min_stock"]), price_centimes=int(row["price_centimes"]),
                      created_at=_parse_time(row["created_at"]),
                      updated_at=_parse_time(row["updated_at"]),
                      archived=bool(row.get("archived", False)))
        if obj.id in state.products:
            raise ValueError("Duplicate product ID in warehouse state.")
        state.products[obj.id] = obj
    for row in data["movements"]:
        obj = Movement(id=row["id"], product_id=row["product_id"],
                       product_code=row["product_code"], product_name=row["product_name"],
                       movement_type=MovementType(row["movement_type"]),
                       previous_quantity=int(row["previous_quantity"]),
                       quantity_delta=int(row["quantity_delta"]),
                       resulting_quantity=int(row["resulting_quantity"]),
                       actor_id=row["actor_id"], actor_username=row["actor_username"],
                       reason=row["reason"], created_at=_parse_time(row["created_at"]))
        if obj.id in state.movements:
            raise ValueError("Duplicate movement ID in warehouse state.")
        state.movements[obj.id] = obj
    if state.next_category < 1 or state.next_product < 1:
        raise ValueError("Invalid sequence values in warehouse state.")
    return state


def _status(exc: Exception) -> int | None:
    return getattr(exc, "status_code", None)


class CosmosWarehouseRepository:
    """Repository using a versioned state item and ETag compare-and-swap."""

    def __init__(self, container, *, warehouse_id: str = "main", max_retries: int = 12):
        if not warehouse_id or len(warehouse_id) > 100:
            raise ValueError("Invalid warehouse ID.")
        if max_retries < 1:
            raise ValueError("max_retries must be positive.")
        self.container = container
        self.warehouse_id = warehouse_id
        self.max_retries = max_retries

    def _initial_document(self):
        return {"id": "warehouse-state", "warehouse_id": self.warehouse_id,
                "schema_version": SCHEMA_VERSION, "state": serialize_state(WarehouseState())}

    def _read_document(self) -> dict:
        try:
            doc = self.container.read_item(item="warehouse-state", partition_key=self.warehouse_id)
        except Exception as exc:
            if _status(exc) != 404:
                raise
            try:
                self.container.create_item(body=self._initial_document())
            except Exception as create_exc:
                # Another process may have won the first-create race.
                if _status(create_exc) != 409:
                    raise
            doc = self.container.read_item(item="warehouse-state", partition_key=self.warehouse_id)
        if doc.get("schema_version") != SCHEMA_VERSION:
            raise RuntimeError("Unsupported Cosmos warehouse document schema version.")
        if doc.get("warehouse_id") != self.warehouse_id:
            raise RuntimeError("Cosmos partition key mismatch.")
        if "_etag" not in doc:
            raise RuntimeError("Cosmos warehouse item has no _etag; cannot guarantee safe writes.")
        return doc

    def read(self) -> WarehouseState:
        return deserialize_state(self._read_document()["state"])

    def transact(self, operation: Callable[[WarehouseState], T]) -> T:
        # Import on write, allowing local unit tests and memory-mode startup
        # without the optional Azure dependency.
        try:
            from azure.core import MatchConditions
        except ImportError as exc:
            raise RuntimeError("Install azure-cosmos and azure-core before enabling Cosmos.") from exc
        for attempt in range(self.max_retries):
            doc = self._read_document()
            draft = deserialize_state(doc["state"])
            result = operation(draft)  # May raise ValidationError; do not commit.
            body = self._initial_document()
            body["state"] = serialize_state(draft)
            if len(json.dumps(body, ensure_ascii=False).encode("utf-8")) > MAX_DOCUMENT_BYTES:
                raise RuntimeError("Warehouse data exceeds the small-demo Cosmos document size limit.")
            try:
                self.container.replace_item(
                    item=doc["id"], body=body, etag=doc["_etag"],
                    match_condition=MatchConditions.IfNotModified,
                )
                return deepcopy(result)
            except Exception as exc:
                if _status(exc) != 412:
                    raise
                # Retry against the new state; operations contain no external side effects.
        raise RuntimeError("Cosmos document changed repeatedly; retry the request.")


def repository_from_environment():
    """Use memory by default; Cosmos only when explicitly configured."""
    from .repository import InMemoryRepository
    backend = os.environ.get("STOCK_BACKEND", "memory").strip().lower()
    if backend == "memory":
        return InMemoryRepository()
    if backend != "cosmos":
        raise RuntimeError("STOCK_BACKEND must be 'memory' or 'cosmos'.")
    endpoint = os.environ.get("COSMOS_ENDPOINT", "").strip()
    key = os.environ.get("COSMOS_KEY", "").strip()
    if not endpoint.startswith("https://") or not key:
        raise RuntimeError("Set COSMOS_ENDPOINT (https://...) and COSMOS_KEY for Cosmos mode.")
    if not endpoint.endswith("/"):
        endpoint += "/"
    try:
        from azure.cosmos import CosmosClient
    except ImportError as exc:
        raise RuntimeError("Install the optional azure-cosmos dependency to use Cosmos mode.") from exc
    # No silent fallback: wrong credentials or absent cloud resources must fail clearly.
    client = CosmosClient(url=endpoint, credential=key)
    database = client.get_database_client(os.environ.get("COSMOS_DATABASE", "stockmanager"))
    container = database.get_container_client(os.environ.get("COSMOS_CONTAINER", "warehouses"))
    repository = CosmosWarehouseRepository(
        container, warehouse_id=os.environ.get("STOCK_WAREHOUSE_ID", "main")
    )
    repository.read()  # Validate network, permissions, and document schema on startup.
    return repository
