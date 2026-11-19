"""Domain records; no Flask or Azure dependencies."""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class StockStatus(str, Enum):
    AVAILABLE = "available"
    LOW = "low"
    OUT = "out"


class MovementType(str, Enum):
    INITIAL = "initial"
    ENTRY = "entry"
    EXIT = "exit"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True)
class Actor:
    id: str
    username: str


@dataclass(frozen=True)
class Category:
    id: str
    code: str
    name: str
    normalized_name: str


@dataclass(frozen=True)
class Product:
    id: str
    code: str
    name: str
    category_ids: tuple[str, ...]
    quantity: int
    min_stock: int
    price_centimes: int
    created_at: datetime
    updated_at: datetime
    archived: bool = False

    @property
    def status(self) -> StockStatus:
        if self.quantity == 0:
            return StockStatus.OUT
        if self.quantity <= self.min_stock:
            return StockStatus.LOW
        return StockStatus.AVAILABLE


@dataclass(frozen=True)
class Movement:
    id: str
    product_id: str
    product_code: str
    product_name: str
    movement_type: MovementType
    previous_quantity: int
    quantity_delta: int
    resulting_quantity: int
    actor_id: str
    actor_username: str
    reason: str
    created_at: datetime


@dataclass
class WarehouseState:
    categories: dict[str, Category] = field(default_factory=dict)
    products: dict[str, Product] = field(default_factory=dict)
    movements: dict[str, Movement] = field(default_factory=dict)
    next_category: int = 1
    next_product: int = 1
