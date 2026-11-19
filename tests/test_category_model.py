import unittest
from services.catalogue import Catalogue, CatalogueError


class CategoryModelTests(unittest.TestCase):
    def setUp(self):
        self.store = Catalogue()

    def test_initial_stats(self):
        self.assertEqual(self.store.statistics(), {"total_products": 6, "low_stock": 2, "out_of_stock": 1})

    def test_case_and_whitespace_duplicates(self):
        for name in ("electronics", " ELECTRONICS ", "office   supplies", ""):
            with self.subTest(name=name), self.assertRaises(CatalogueError):
                self.store.add_category(name)
        category = self.store.add_category("  Cleaning   Supplies  ")
        self.assertEqual(category["name"], "Cleaning Supplies")

    def test_rename_reflected_without_product_update(self):
        self.store.rename_category("C001", "Electronic Equipment")
        self.assertIn("Electronic Equipment", self.store.product_rows()[0]["category_names"])
        self.assertIn("C001", self.store.products[0]["category_ids"])
        with self.assertRaises(CatalogueError):
            self.store.rename_category("C001", "accessories")

    def test_delete_guard(self):
        with self.assertRaises(CatalogueError):
            self.store.delete_category("C001")
        category = self.store.add_category("Cleaning")
        self.store.delete_category(category["id"])
        self.assertIsNone(self.store.get_category(category["id"]))

    def test_multicategory_creation(self):
        p = self.store.add_product("Flash Drive", ["C001", "C002", "C001"], "20", "5", "89.99")
        self.assertEqual(p["id"], "P007")
        self.assertEqual(p["category_ids"], ["C001", "C002"])
        self.assertEqual(self.store.statistics()["total_products"], 7)

    def test_reject_invalid_creation(self):
        for cats, qty, price in [([], "1", "2"), (["C999"], "1", "2"), (["C001"], "-1", "2"), (["C001"], "1.5", "2"), (["C001"], "1", "nan"), (["C001"], "1", "0.001")]:
            with self.subTest(cats=cats, qty=qty, price=price), self.assertRaises(CatalogueError):
                self.store.add_product("Bad product", cats, qty, "0", price)
        self.assertEqual(len(self.store.products), 6)

    def test_edit_preserves_quantity_and_id(self):
        p = self.store.edit_product("P001", "Mouse Pro", ["C002"], "8", "19.99")
        self.assertEqual((p["id"], p["quantity"], p["category_ids"]), ("P001", 45, ["C002"]))

    def test_or_and_and_combined_filtering(self):
        self.assertEqual(len(self.store.filter_products(category_ids=["C001", "C002"], mode="any")), 5)
        self.assertEqual(len(self.store.filter_products(category_ids=["C001", "C002"], mode="all")), 3)
        self.assertEqual(len(self.store.filter_products(category_ids=["C001", "C002", "C005"], mode="all")), 1)
        matches = self.store.filter_products("HEAD", ["C001", "C002"], "all", "low")
        self.assertEqual([p["id"] for p in matches], ["P005"])
        self.assertEqual(len(self.store.filter_products()), 6)


if __name__ == "__main__":
    unittest.main()
