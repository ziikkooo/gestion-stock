"""Atomic repository contract for the initial single-warehouse model."""
from copy import deepcopy
from threading import RLock
from typing import Callable, Protocol, TypeVar
from .models import WarehouseState

T = TypeVar("T")


class WarehouseRepository(Protocol):
    def read(self) -> WarehouseState:
        """Return an isolated consistent snapshot."""
        ...

    def transact(self, operation: Callable[[WarehouseState], T]) -> T:
        """Commit all changes together, or none if an exception is raised.

        The operation may be replayed after a concurrency conflict by a future
        persistent implementation. It must not perform external side effects.
        """
        ...


class InMemoryRepository:
    def __init__(self) -> None:
        self._state = WarehouseState()
        self._lock = RLock()

    def read(self) -> WarehouseState:
        with self._lock:
            return deepcopy(self._state)

    def transact(self, operation: Callable[[WarehouseState], T]) -> T:
        with self._lock:
            draft = deepcopy(self._state)
            result = operation(draft)
            # Copy before publication so the caller cannot mutate stored state.
            detached = deepcopy(result)
            self._state = deepcopy(draft)
            return detached
