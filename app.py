from flask import Flask, render_template, request, redirect, url_for
from itertools import count
import math

app = Flask(__name__)

# Temporary product data
products = [
    {
        "id": "P001",
        "name": "Wireless Mouse",
        "category": "Electronics",
        "quantity": 45,
        "min_stock": 10,
        "price": 129.99
    },
    {
        "id": "P002",
        "name": "USB Cable",
        "category": "Accessories",
        "quantity": 8,
        "min_stock": 10,
        "price": 39.99
    },
    {
        "id": "P003",
        "name": "Notebook",
        "category": "Stationery",
        "quantity": 120,
        "min_stock": 20,
        "price": 24.99
    },
    {
        "id": "P004",
        "name": "Keyboard",
        "category": "Electronics",
        "quantity": 0,
        "min_stock": 5,
        "price": 199.99
    },
    {
        "id": "P005",
        "name": "Headphones",
        "category": "Electronics",
        "quantity": 4,
        "min_stock": 10,
        "price": 249.99
    },
    {
        "id": "P006",
        "name": "Desk Lamp",
        "category": "Office Supplies",
        "quantity": 26,
        "min_stock": 5,
        "price": 149.99
    }
]
# Automatic product identifier counter
product_counter = count(
    max(
        (int(product["id"][1:]) for product in products),
        default=0
    ) + 1
)

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/inventory")
def inventory():

    # Retrieve search and filter parameters
    search = request.args.get("search", "").strip().lower()
    category = request.args.get("category", "")
    status = request.args.get("status", "")

    # Retrieve all existing categories
    categories = sorted({
        product["category"] for product in products
    })

    # Calculate global inventory statistics
    total_products = len(products)

    low_stock = sum(
        1 for product in products
        if 0 < product["quantity"] <= product["min_stock"]
    )

    out_of_stock = sum(
        1 for product in products
        if product["quantity"] == 0
    )

    # Apply search and filters
    filtered_products = []

    for product in products:

        if search:
            if (
                search not in product["name"].lower()
                and search not in product["id"].lower()
            ):
                continue

        if category and product["category"] != category:
            continue

        if status == "available":
            if product["quantity"] <= product["min_stock"]:
                continue

        elif status == "low":
            if not 0 < product["quantity"] <= product["min_stock"]:
                continue

        elif status == "out":
            if product["quantity"] != 0:
                continue

        filtered_products.append(product)

    return render_template(
        "inventory.html",
        products=filtered_products,
        total_products=total_products,
        low_stock=low_stock,
        out_of_stock=out_of_stock,
        categories=categories,
        search=search,
        selected_category=category,
        selected_status=status
    )

@app.route("/admin")
def admin():
    return render_template(
        "admin.html",
        products=products
    )

@app.route("/admin/add", methods=["GET", "POST"])
def add_product():

    if request.method == "POST":

        # Retrieve form data
        name = request.form.get("name", "").strip()
        category = request.form.get("category", "").strip()

        # Validate text fields
        if not name or not category:
            return render_template(
                "add_product.html",
                error="Product name and category are required."
            ), 400

        if len(name) > 100 or len(category) > 50:
            return render_template(
                "add_product.html",
                error="Product name or category is too long."
            ), 400

        # Convert and validate numerical values
        try:
            quantity = int(request.form.get("quantity", ""))
            min_stock = int(request.form.get("min_stock", ""))
            price = float(request.form.get("price", ""))

        except ValueError:
            return render_template(
                "add_product.html",
                error="Please enter valid numerical values."
            ), 400

        if (
            quantity < 0
            or min_stock < 0
            or price < 0
            or not math.isfinite(price)
        ):
            return render_template(
                "add_product.html",
                error="Stock quantities and price must be valid non-negative values."
            ), 400

        # Generate product ID
        product_id = f"P{next(product_counter):03d}"

        # Create the product
        new_product = {
            "id": product_id,
            "name": name,
            "category": category,
            "quantity": quantity,
            "min_stock": min_stock,
            "price": round(price, 2)
        }

        # Add to the temporary inventory
        products.append(new_product)

        # Return to administration
        return redirect(url_for("admin"))

    return render_template("add_product.html")

