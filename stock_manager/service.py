"""Catalogue and stock business rules, independent of transport and database."""
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re
from uuid import uuid4
from .models import Actor, Category, Movement, MovementType, Product, StockStatus, WarehouseState
from .repository import WarehouseRepository


class ValidationError(ValueError):
    pass


class NotFoundError(LookupError):
    pass


def clean_text(value: str, label: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise ValidationError(f"{label} must be text.")
    value = " ".join(value.split())
    if not value or len(value) > maximum:
        raise ValidationError(f"{label} must contain 1 to {maximum} characters.")
    return value


def whole_number(value: int, label: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValidationError(f"{label} must be a whole number >= {minimum}.")
    # Keep quantities within a safe range for JSON-based storage and clients.
    if value > 2**53 - 1:
        raise ValidationError(f"{label} is too large.")
    return value


def price_to_centimes(value: str | Decimal) -> int:
    """Convert exact decimal input, rejecting fractions of a centime and floats."""
    if not isinstance(value, (str, Decimal)):
        raise ValidationError("Price must be decimal text or Decimal.")
    if isinstance(value, str) and not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value.strip()):
        raise ValidationError("Price must use ordinary decimal notation with up to two decimal places.")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0 or amount > Decimal("90071992547409.91"):
            raise ValidationError("Price is outside the supported range.")
        rounded = amount.quantize(Decimal("0.01"))
        if rounded != amount:
            raise ValidationError("Price cannot contain fractions of a centime.")
        return int(rounded * 100)
    except InvalidOperation as exc:
        raise ValidationError("Invalid price.") from exc


def _find_product(state: WarehouseState, product_id: str) -> Product:
    try:
        return state.products[product_id]
    except KeyError as exc:
        raise NotFoundError("Product not found.") from exc


def _category_ids(state: WarehouseState, ids: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(ids, (list, tuple)) or not ids or not all(isinstance(i, str) for i in ids):
        raise ValidationError("Select at least one valid category.")
    if len(set(ids)) != len(ids):
        raise ValidationError("Duplicate category selection.")
    if any(i not in state.categories for i in ids):
        raise ValidationError("Unknown category.")
    return tuple(ids)


def _check_actor(actor: Actor) -> None:
    if not isinstance(actor, Actor) or not isinstance(actor.id, str) or not actor.id.strip() or not isinstance(actor.username, str) or not actor.username.strip():
        raise ValidationError("A valid actor is required.")


class WarehouseService:
    def __init__(self, repository: WarehouseRepository):
        self.repository = repository

    def create_category(self, name: str) -> Category:
        name = clean_text(name, "Category name", 50)
        normalized = name.casefold()

        def operation(state):
            if any(c.normalized_name == normalized for c in state.categories.values()):
                raise ValidationError("Category already exists.")
            category = Category(str(uuid4()), f"C{state.next_category:03d}", name, normalized)
            state.next_category += 1
            state.categories[category.id] = category
            return category

        return self.repository.transact(operation)

    def rename_category(self, category_id: str, name: str) -> Category:
        name = clean_text(name, "Category name", 50)
        normalized = name.casefold()

        def operation(state):
            if category_id not in state.categories:
                raise NotFoundError("Category not found.")
            if any(c.id != category_id and c.normalized_name == normalized for c in state.categories.values()):
                raise ValidationError("Category already exists.")
            category = replace(state.categories[category_id], name=name, normalized_name=normalized)
            state.categories[category_id] = category
            return category

        return self.repository.transact(operation)

    def delete_category(self, category_id: str) -> None:
        def operation(state):
            if category_id not in state.categories:
                raise NotFoundError("Category not found.")
            if any(category_id in p.category_ids for p in state.products.values()):
                raise ValidationError("Category is assigned to a product, including archived products.")
            del state.categories[category_id]

        self.repository.transact(operation)

    def create_product(self, *, name: str, category_ids: list[str], quantity: int,
                       min_stock: int, price: str | Decimal, actor: Actor) -> Product:
        name = clean_text(name, "Product name", 100)
        quantity = whole_number(quantity, "Quantity")
        min_stock = whole_number(min_stock, "Minimum stock")
        cents = price_to_centimes(price)
        _check_actor(actor)

        def operation(state):
            ids = _category_ids(state, category_ids)
            now = datetime.now(timezone.utc)
            product = Product(str(uuid4()), f"P{state.next_product:03d}", name, ids,
                              quantity, min_stock, cents, now, now)
            state.next_product += 1
            movement = self._movement(product, MovementType.INITIAL, 0, quantity, actor, "Product creation", now)
            state.products[product.id] = product
            state.movements[movement.id] = movement
            return product

        return self.repository.transact(operation)

    def edit_product(self, product_id: str, *, name: str, category_ids: list[str],
                     min_stock: int, price: str | Decimal) -> Product:
        name = clean_text(name, "Product name", 100)
        min_stock = whole_number(min_stock, "Minimum stock")
        cents = price_to_centimes(price)

        def operation(state):
            product = _find_product(state, product_id)
            if product.archived:
                raise ValidationError("Restore the product before editing it.")
            result = replace(product, name=name, category_ids=_category_ids(state, category_ids),
                             min_stock=min_stock, price_centimes=cents, updated_at=datetime.now(timezone.utc))
            state.products[product_id] = result
            return result

        return self.repository.transact(operation)

    def set_archived(self, product_id: str, archived: bool) -> Product:
        if type(archived) is not bool:
            raise ValidationError("Invalid archive status.")

        def operation(state):
            product = _find_product(state, product_id)
            if archived and product.quantity != 0:
                raise ValidationError("Only products with zero stock can be archived.")
            result = replace(product, archived=archived, updated_at=datetime.now(timezone.utc))
            state.products[product_id] = result
            return result

        return self.repository.transact(operation)

    def record_movement(self, product_id: str, *, kind: MovementType, amount: int,
                        actor: Actor, reason: str = "", expected_quantity: int | None = None) -> Movement:
        _check_actor(actor)
        if not isinstance(kind, MovementType) or kind == MovementType.INITIAL:
            raise ValidationError("Invalid movement type.")
        amount = whole_number(amount, "Amount", 0 if kind == MovementType.ADJUSTMENT else 1)
        if not isinstance(reason, str):
            raise ValidationError("Reason must be text.")
        reason = reason.strip()
        if len(reason) > 500 or (kind == MovementType.ADJUSTMENT and not reason):
            raise ValidationError("An adjustment requires a reason; maximum length is 500 characters.")
        if kind == MovementType.ADJUSTMENT:
            # Avoid silently overwriting a stock change since the count was entered.
            whole_number(expected_quantity, "Expected stock")

        def operation(state):
            product = _find_product(state, product_id)
            if product.archived:
                raise ValidationError("Archived products cannot receive movements.")
            previous = product.quantity
            if kind == MovementType.ADJUSTMENT and previous != expected_quantity:
                raise ValidationError("Stock changed since counting; review the quantity again.")
            if kind == MovementType.ENTRY:
                resulting = previous + amount
            elif kind == MovementType.EXIT:
                resulting = previous - amount
            else:
                resulting = amount
            if resulting < 0:
                raise ValidationError("Insufficient stock.")
            whole_number(resulting, "Resulting stock")
            if resulting == previous:
                raise ValidationError("Movement does not change stock.")
            now = datetime.now(timezone.utc)
            movement = self._movement(product, kind, previous, resulting, actor, reason, now)
            state.products[product_id] = replace(product, quantity=resulting, updated_at=now)
            state.movements[movement.id] = movement
            return movement

        return self.repository.transact(operation)

    @staticmethod
    def _movement(product, kind, previous, resulting, actor, reason, now):
        return Movement(str(uuid4()), product.id, product.code, product.name, kind, previous,
                        resulting - previous, resulting, actor.id, actor.username, reason, now)

    def filter_products(self, *, search: str = "", category_ids: tuple[str, ...] = (),
                        mode: str = "any", status: StockStatus | None = None,
                        archived: bool = False) -> list[Product]:
        if mode not in ("any", "all") or (status is not None and not isinstance(status, StockStatus)):
            raise ValidationError("Invalid filter.")
        state = self.repository.read()
        if category_ids:
            _category_ids(state, category_ids)
        query = search.strip().casefold()
        chosen = set(category_ids)
        result = []
        for product in state.products.values():
            if product.archived != archived:
                continue
            if query and query not in product.name.casefold() and query not in product.code.casefold():
                continue
            if status is not None and product.status != status:
                continue
            assigned = set(product.category_ids)
            if chosen and not (bool(chosen & assigned) if mode == "any" else chosen <= assigned):
                continue
            result.append(product)
        return sorted(result, key=lambda p: (p.name.casefold(), p.code))

    def history(self, product_id: str) -> list[Movement]:
        state = self.repository.read()
        _find_product(state, product_id)
        return sorted((m for m in state.movements.values() if m.product_id == product_id),
                      key=lambda m: m.created_at)
