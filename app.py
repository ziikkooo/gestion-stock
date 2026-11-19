from flask import Flask, render_template, request

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
