"""Flask catalogue compatibility adapter backed by WarehouseService.

Public P###/C### codes remain stable for URLs/forms. UUIDs are internal.
No product or category data lives in a separate mutable list anymore.
The local repository is process-memory only until Cosmos DB integration.
"""
from decimal import Decimal
import re

from stock_manager.models import Actor, StockStatus, MovementType
from stock_manager.repository import InMemoryRepository
from stock_manager.service import WarehouseService, ValidationError, NotFoundError


class CatalogueError(ValueError):
    """Validation error suitable for the existing HTTP error forms."""


SEED_ACTOR = Actor(id="system-seed", username="system-seed")
LOCAL_ACTOR = Actor(id="local-unit-test", username="local-unit-test")

_INITIAL_CATEGORIES = (
    "Electronics", "Accessories", "Stationery", "Office Supplies", "Computer Equipment",
)
_INITIAL_PRODUCTS = (
    ("Wireless Mouse", ("C001", "C002", "C005"), 45, 10, "129.99"),
    ("USB Cable", ("C001", "C002"), 8, 10, "39.99"),
    ("Notebook", ("C003", "C004"), 120, 20, "24.99"),
    ("Keyboard", ("C001", "C005"), 0, 5, "199.99"),
    ("Headphones", ("C001", "C002"), 4, 10, "249.99"),
    ("Desk Lamp", ("C001", "C004"), 26, 5, "149.99"),
)


def normalize_name(value):
    return " ".join(value.split()) if isinstance(value, str) else ""


def stock_status(product):
    if product["quantity"] == 0:
        return "out"
    if product["quantity"] <= product["min_stock"]:
        return "low"
    return "available"


def _parse_whole(value):
    """Use browser-compatible decimal integers; never silently truncate '1.5'."""
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+", text):
        raise CatalogueError("Enter valid non-negative whole quantities and a price with at most two decimal places.")
    number = int(text)
    if number > 2147483647:
        raise CatalogueError("Enter valid non-negative whole quantities and a price with at most two decimal places.")
    return number


def _parse_price(value):
    text = str(value).strip()
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", text):
        raise CatalogueError("Enter valid non-negative whole quantities and a price with at most two decimal places.")
    if Decimal(text) > Decimal("999999999.99"):
        raise CatalogueError("Enter valid non-negative whole quantities and a price with at most two decimal places.")
    return text


def _to_category(row):
    return {"id": row.code, "name": row.name}


def _to_product(row, categories):
    """Adapt a domain Product to the old Jinja-compatible view shape.

    Decimal is used only for presentation; repository stores integer centimes.
    """
    return {
        "id": row.code,
        "name": row.name,
        "category_ids": [categories[key].code for key in row.category_ids],
        "quantity": row.quantity,
        "min_stock": row.min_stock,
        "price": Decimal(row.price_centimes) / Decimal(100),
        "status": row.status.value,
        "archived": row.archived,
    }


class Catalogue:
    def __init__(self):
        self.repository = InMemoryRepository()
        self.service = WarehouseService(self.repository)
        for name in _INITIAL_CATEGORIES:
            self.service.create_category(name)
        for name, codes, qty, minimum, price in _INITIAL_PRODUCTS:
            self.service.create_product(
                name=name,
                category_ids=self._category_ids(codes),
                quantity=qty,
                min_stock=minimum,
                price=price,
                actor=SEED_ACTOR,
            )

    def _category_ids(self, codes):
        state = self.repository.read()
        by_code = {c.code: c.id for c in state.categories.values()}
        try:
            return [by_code[code] for code in codes]
        except KeyError as exc:
            raise CatalogueError("Select valid registered categories.") from exc

    def _category_uuid(self, code):
        return next((c.id for c in self.repository.read().categories.values() if c.code == code), None)

    def _product_uuid(self, code):
        return next((p.id for p in self.repository.read().products.values() if p.code == code), None)

    @property
    def categories(self):
        return [_to_category(c) for c in sorted(
            self.repository.read().categories.values(), key=lambda c: int(c.code[1:])
        )]

    @property
    def products(self):
        state = self.repository.read()
        return [_to_product(p, state.categories) for p in sorted(
            state.products.values(), key=lambda p: int(p.code[1:])
        ) if not p.archived]

    def get_category(self, category_id):
        category = next((c for c in self.repository.read().categories.values() if c.code == category_id), None)
        return _to_category(category) if category else None

    def get_product(self, product_id, *, include_archived=False):
        state = self.repository.read()
        product = next((p for p in state.products.values()
                        if p.code == product_id and (include_archived or not p.archived)), None)
        return _to_product(product, state.categories) if product else None

    def audit_product_rows(self):
        """All products, including archived ones, remain available as audit filters."""
        state = self.repository.read()
        return [_to_product(p, state.categories) for p in sorted(
            state.products.values(), key=lambda p: int(p.code[1:]))]

    def sorted_categories(self):
        return sorted(self.categories, key=lambda c: c["name"].casefold())

    def category_rows(self):
        state = self.repository.read()
        return [
            dict(_to_category(c), product_count=sum(c.id in p.category_ids for p in state.products.values()))
            for c in sorted(state.categories.values(), key=lambda c: int(c.code[1:]))
        ]

    def product_rows(self, products=None):
        categories = {c["id"]: c["name"] for c in self.categories}
        source = self.products if products is None else products
        return [dict(p, category_names=[categories[c] for c in p["category_ids"]])
                for p in sorted(source, key=lambda p: int(p["id"][1:]))]

    def validate_category(self, name, exclude_id=None):
        name = normalize_name(name)
        if not name or len(name) > 50:
            raise CatalogueError("Category name must contain 1 to 50 characters.")
        if "," in name:
            raise CatalogueError("Create one category at a time (without commas).")
        if any(c["id"] != exclude_id and c["name"].casefold() == name.casefold()
               for c in self.categories):
            raise CatalogueError("This category already exists.")
        return name

    def add_category(self, name):
        name = self.validate_category(name)
        try:
            return _to_category(self.service.create_category(name))
        except ValidationError as exc:
            raise CatalogueError(str(exc)) from exc

    def rename_category(self, category_id, name):
        uid = self._category_uuid(category_id)
        if uid is None:
            raise CatalogueError("Category not found.")
        name = self.validate_category(name, exclude_id=category_id)
        try:
            return _to_category(self.service.rename_category(uid, name))
        except (ValidationError, NotFoundError) as exc:
            raise CatalogueError(str(exc)) from exc

    def delete_category(self, category_id):
        uid = self._category_uuid(category_id)
        if uid is None:
            raise CatalogueError("Category not found.")
        try:
            self.service.delete_category(uid)
        except (ValidationError, NotFoundError) as exc:
            raise CatalogueError(str(exc)) from exc

    def validate_product(self, name, category_ids, min_stock, price, quantity=None):
        name = normalize_name(name)
        if not name or len(name) > 100:
            raise CatalogueError("Product name must contain 1 to 100 characters.")
        category_ids = list(dict.fromkeys(category_ids))
        if not category_ids:
            raise CatalogueError("Select at least one category.")
        self._category_ids(category_ids)
        data = {
            "name": name,
            "category_ids": category_ids,
            "min_stock": _parse_whole(min_stock),
            "price": _parse_price(price),
        }
        if quantity is not None:
            data["quantity"] = _parse_whole(quantity)
        return data

    def add_product(self, name, category_ids, quantity, min_stock, price, *, actor=None):
        data = self.validate_product(name, category_ids, min_stock, price, quantity=quantity)
        try:
            result = self.service.create_product(
                name=data["name"], category_ids=self._category_ids(data["category_ids"]),
                quantity=data["quantity"], min_stock=data["min_stock"], price=data["price"],
                actor=actor if actor is not None else LOCAL_ACTOR,
            )
        except (ValidationError, NotFoundError) as exc:
            raise CatalogueError(str(exc)) from exc
        return _to_product(result, self.repository.read().categories)

    def edit_product(self, product_id, name, category_ids, min_stock, price):
        uid = self._product_uuid(product_id)
        if uid is None:
            raise CatalogueError("Product not found.")
        data = self.validate_product(name, category_ids, min_stock, price)
        try:
            result = self.service.edit_product(
                uid, name=data["name"], category_ids=self._category_ids(data["category_ids"]),
                min_stock=data["min_stock"], price=data["price"],
            )
        except (ValidationError, NotFoundError) as exc:
            raise CatalogueError(str(exc)) from exc
        return _to_product(result, self.repository.read().categories)

    def filter_products(self, search="", category_ids=(), mode="any", status=""):
        state = self.repository.read()
        by_code = {c.code: c.id for c in state.categories.values()}
        if any(code not in by_code for code in category_ids):
            return []
        resolved = tuple(by_code[code] for code in dict.fromkeys(category_ids))
        try:
            matches = self.service.filter_products(
                search=search, category_ids=resolved, mode=mode,
                status=StockStatus(status) if status else None,
            )
        except (ValidationError, ValueError) as exc:
            raise CatalogueError(str(exc)) from exc
        return [_to_product(p, state.categories) for p in matches]

    def statistics(self):
        active = [p for p in self.repository.read().products.values() if not p.archived]
        return {
            "total_products": len(active),
            "low_stock": sum(p.status == StockStatus.LOW for p in active),
            "out_of_stock": sum(p.status == StockStatus.OUT for p in active),
        }

    def history(self, product_code):
        """Read immutable movement records; used for integration tests and later UI."""
        uid = self._product_uuid(product_code)
        if uid is None:
            raise CatalogueError("Product not found.")
        return self.service.history(uid)


    def record_stock_movement(self, *, product_code, kind, amount, reason,
                              expected_quantity, actor):
        """Validated public product-code adapter; server supplies trusted actor.

        No stock change is permitted through the product edit form. Only this
        entry point invokes the service's atomic movement transaction.
        """
        uid = self._product_uuid(product_code)
        if uid is None or self.get_product(product_code) is None:
            raise CatalogueError("Product not found.")
        try:
            movement_kind = MovementType(kind)
        except (ValueError, TypeError) as exc:
            raise CatalogueError("Select Entry, Exit or Adjustment.") from exc
        if movement_kind == MovementType.INITIAL:
            raise CatalogueError("Initial stock is recorded only when a product is created.")
        # Bound input length before converting maliciously huge decimal strings.
        if not isinstance(amount, str) or len(amount.strip()) > 10:
            raise CatalogueError("Quantity is outside the supported range.")
        count = _parse_whole(amount)
        expected = None
        if movement_kind == MovementType.ADJUSTMENT:
            if not isinstance(expected_quantity, str) or len(expected_quantity.strip()) > 10:
                raise CatalogueError("Expected stock is outside the supported range.")
            expected = _parse_whole(expected_quantity)
        if not isinstance(reason, str):
            raise CatalogueError("Reason must be text.")
        try:
            return self.service.record_movement(
                uid, kind=movement_kind, amount=count, actor=actor,
                reason=reason, expected_quantity=expected,
            )
        except (ValidationError, NotFoundError) as exc:
            raise CatalogueError(str(exc)) from exc

    def movement_rows(self, product_code=None):
        """Read-only audit projection; most recent first, UTC timestamps."""
        state = self.repository.read()
        if product_code is not None:
            uid = self._product_uuid(product_code)
            if uid is None:
                raise CatalogueError("Product not found.")
        else:
            uid = None
        rows = (m for m in state.movements.values() if uid is None or m.product_id == uid)
        ordered = sorted(rows, key=lambda m: (m.created_at, m.id), reverse=True)
        return [{
            "id": m.id,
            "product_code": m.product_code,
            "product_name": m.product_name,
            "kind": m.movement_type.value,
            "previous_quantity": m.previous_quantity,
            "delta": m.quantity_delta,
            "resulting_quantity": m.resulting_quantity,
            "actor": m.actor_username,
            "reason": m.reason,
            "timestamp": m.created_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        } for m in ordered]
