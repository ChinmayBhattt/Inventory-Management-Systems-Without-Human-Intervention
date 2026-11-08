from __future__ import annotations

from dataclasses import dataclass


@dataclass
class InventoryItem:
    name: str
    quantity: int
    reorder_level: int
    reorder_quantity: int


class AutonomousInventoryManager:
    def __init__(self) -> None:
        self._items: dict[str, InventoryItem] = {}

    def add_item(
        self,
        name: str,
        quantity: int,
        reorder_level: int,
        reorder_quantity: int,
    ) -> None:
        if not name:
            raise ValueError("Item name must not be empty")
        if min(quantity, reorder_level, reorder_quantity) < 0:
            raise ValueError("Inventory values must be non-negative")
        self._items[name] = InventoryItem(
            name=name,
            quantity=quantity,
            reorder_level=reorder_level,
            reorder_quantity=reorder_quantity,
        )

    def get_quantity(self, name: str) -> int:
        return self._get_item(name).quantity

    def consume(self, name: str, amount: int) -> None:
        if amount <= 0:
            raise ValueError("Consume amount must be positive")

        item = self._get_item(name)
        if amount > item.quantity:
            raise ValueError("Insufficient stock")

        item.quantity -= amount
        self._auto_reorder(item)

    def _auto_reorder(self, item: InventoryItem) -> None:
        if item.quantity <= item.reorder_level:
            item.quantity += item.reorder_quantity

    def _get_item(self, name: str) -> InventoryItem:
        try:
            return self._items[name]
        except KeyError as exc:
            raise KeyError(f"Unknown item: {name}") from exc
