import unittest

from inventory_management import AutonomousInventoryManager


class AutonomousInventoryManagerTests(unittest.TestCase):
    def test_auto_reorders_when_level_reached(self) -> None:
        manager = AutonomousInventoryManager()
        manager.add_item("widget", quantity=10, reorder_level=5, reorder_quantity=20)

        manager.consume("widget", 5)

        self.assertEqual(manager.get_quantity("widget"), 25)

    def test_no_reorder_above_threshold(self) -> None:
        manager = AutonomousInventoryManager()
        manager.add_item("widget", quantity=10, reorder_level=5, reorder_quantity=20)

        manager.consume("widget", 2)

        self.assertEqual(manager.get_quantity("widget"), 8)

    def test_prevents_overselling(self) -> None:
        manager = AutonomousInventoryManager()
        manager.add_item("widget", quantity=3, reorder_level=1, reorder_quantity=10)

        with self.assertRaisesRegex(ValueError, "Insufficient stock"):
            manager.consume("widget", 4)


if __name__ == "__main__":
    unittest.main()
