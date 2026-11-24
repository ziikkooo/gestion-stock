"""In-memory catalogue for the local development phase."""

from decimal import Decimal, InvalidOperation
from itertools import count
import re


class CatalogueError(ValueError):
    pass


def normalize_name(value):
    return " ".join(value.split())


def stock_status(product):
    if product["quantity"] == 0:
        return "out"
    if product["quantity"] <= product["min_stock"]:
        return "low"
    return "available"


class Catalogue:
    def __init__(self):
        self.categories = [
            {"id": "C001", "name": "Electronics"},
            {"id": "C002", "name": "Accessories"},
            {"id": "C003", "name": "Stationery"},
            {"id": "C004", "name": "Office Supplies"},
            {"id": "C005", "name": "Computer Equipment"},
        ]
        self.products = [
            {"id": "P001", "name": "Wireless Mouse", "category_ids": ["C001", "C002", "C005"], "quantity": 45, "min_stock": 10, "price": 129.99},
            {"id": "P002", "name": "USB Cable", "category_ids": ["C001", "C002"], "quantity": 8, "min_stock": 10, "price": 39.99},
            {"id": "P003", "name": "Notebook", "category_ids": ["C003", "C004"], "quantity": 120, "min_stock": 20, "price": 24.99},
            {"id": "P004", "name": "Keyboard", "category_ids": ["C001", "C005"], "quantity": 0, "min_stock": 5, "price": 199.99},
            {"id": "P005", "name": "Headphones", "category_ids": ["C001", "C002"], "quantity": 4, "min_stock": 10, "price": 249.99},
            {"id": "P006", "name": "Desk Lamp", "category_ids": ["C001", "C004"], "quantity": 26, "min_stock": 5, "price": 149.99},
        ]
        self.category_counter = count(6)
        self.product_counter = count(7)

    def get_category(self, category_id):
        return next((c for c in self.categories if c["id"] == category_id), None)

    def get_product(self, product_id):
        return next((p for p in self.products if p["id"] == product_id), None)

    def sorted_categories(self):
        # Alphabetical order for category selectors and filters.
        return sorted(self.categories, key=lambda c: c["name"].casefold())

    def category_rows(self):
        # Registration/ID order for the administrative category table.
        return [
            dict(
                category,
                product_count=sum(
                    category["id"] in product["category_ids"]
                    for product in self.products
                ),
            )
            for category in sorted(
                self.categories, key=lambda c: int(c["id"][1:])
            )
        ]

    def product_rows(self, products=None):
        names = {category["id"]: category["name"] for category in self.categories}
        source = self.products if products is None else products
        # Product ID order both in Administration and Inventory.
        return [
            dict(
                product,
                category_names=[names[c] for c in product["category_ids"]],
                status=stock_status(product),
            )
            for product in sorted(source, key=lambda p: int(p["id"][1:]))
        ]

    def validate_category(self, name, exclude_id=None):
        name = normalize_name(name)
        if not name or len(name) > 50:
            raise CatalogueError("Category name must contain 1 to 50 characters.")
        if "," in name:
            raise CatalogueError("Create one category at a time (without commas).")
        if any(
            category["id"] != exclude_id
            and category["name"].casefold() == name.casefold()
            for category in self.categories
        ):
            raise CatalogueError("This category already exists.")
        return name

    def add_category(self, name):
        name = self.validate_category(name)
        category = {"id": f"C{next(self.category_counter):03d}", "name": name}
        self.categories.append(category)
        return category

    def rename_category(self, category_id, name):
        category = self.get_category(category_id)
        if category is None:
            raise CatalogueError("Category not found.")
        category["name"] = self.validate_category(name, exclude_id=category_id)
        return category

    def delete_category(self, category_id):
        category = self.get_category(category_id)
        if category is None:
            raise CatalogueError("Category not found.")
        if any(category_id in p["category_ids"] for p in self.products):
            raise CatalogueError(
                "This category is assigned to products. Reassign them before deleting it."
            )
        self.categories.remove(category)

    def validate_product(self, name, category_ids, min_stock, price, quantity=None):
        name = normalize_name(name)
        if not name or len(name) > 100:
            raise CatalogueError("Product name must contain 1 to 100 characters.")

        category_ids = list(dict.fromkeys(category_ids))
        if not category_ids:
            raise CatalogueError("Select at least one category.")
        if any(self.get_category(category_id) is None for category_id in category_ids):
            raise CatalogueError("Select valid registered categories.")

        try:
            minimum = int(min_stock)
            initial = int(quantity) if quantity is not None else None

            # Reject scientific notation (1e3), signs, commas and >2 decimals.
            price_text = str(price).strip()
            if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", price_text):
                raise ValueError
            amount = Decimal(price_text)

            if not amount.is_finite() or amount < 0:
                raise ValueError
            if not 0 <= minimum <= 2147483647:
                raise ValueError
            if initial is not None and not 0 <= initial <= 2147483647:
                raise ValueError
            if amount > Decimal("999999999.99"):
                raise ValueError
        except (ValueError, InvalidOperation, TypeError, OverflowError):
            raise CatalogueError(
                "Enter valid non-negative whole quantities and a price with at most two decimal places."
            ) from None

        # Keep the old catalogue's price field compatible with current templates.
        data = {
            "name": name,
            "category_ids": category_ids,
            "min_stock": minimum,
            "price": float(amount),
        }
        if initial is not None:
            data["quantity"] = initial
        return data

    def add_product(self, name, category_ids, quantity, min_stock, price):
        data = self.validate_product(name, category_ids, min_stock, price, quantity=quantity)
        product = dict(data, id=f"P{next(self.product_counter):03d}")
        self.products.append(product)
        return product

    def edit_product(self, product_id, name, category_ids, min_stock, price):
        product = self.get_product(product_id)
        if product is None:
            raise CatalogueError("Product not found.")
        product.update(self.validate_product(name, category_ids, min_stock, price))
        return product

    def filter_products(self, search="", category_ids=(), mode="any", status=""):
        search = search.strip().casefold()
        selected = set(category_ids)
        output = []
        for product in self.products:
            if search and search not in product["name"].casefold() and search not in product["id"].casefold():
                continue
            assigned = set(product["category_ids"])
            if selected and not (selected <= assigned if mode == "all" else selected & assigned):
                continue
            if status and stock_status(product) != status:
                continue
            output.append(product)
        return output

    def statistics(self):
        return {
            "total_products": len(self.products),
            "low_stock": sum(stock_status(p) == "low" for p in self.products),
            "out_of_stock": sum(stock_status(p) == "out" for p in self.products),
        }
